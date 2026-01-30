import serial
import time

# ---------- CRC16-CCITT (FALSE) ----------
def crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) & 0xFFFF) ^ poly
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF

def verificar_crc(cmd: int, length: int, payload: bytes, crc_rx: int) -> bool:
    header = bytes([cmd]) + length.to_bytes(2, "little")
    calc = crc16_ccitt(header + payload)
    return calc == crc_rx

# ---------- Armar frame (cmd + len + payload + crc) ----------
def armar_frame(cmd: int, payload: bytes = b"") -> bytes:
    """
    Frame: [cmd:1][len:2 little][payload][crc:2 little]
    CRC sobre (cmd + len + payload)
    """
    length = len(payload)
    header = bytes([cmd]) + length.to_bytes(2, "little")
    crc = crc16_ccitt(header + payload)
    return header + payload + crc.to_bytes(2, "little")

# ---------- Lectura exacta ----------
def read_exact(ser: serial.Serial, n: int) -> bytes:
    """
    Lee exactamente n bytes del serial (o lanza TimeoutError).
    Usa el timeout configurado en ser.timeout.
    """
    buf = bytearray()
    while len(buf) < n:
        chunk = ser.read(n - len(buf))
        if not chunk:
            raise TimeoutError(f"No llegaron {n} bytes a tiempo (llegaron {len(buf)}).")
        buf.extend(chunk)
    return bytes(buf)

# ---------- Recibir frame ----------
def recibir_senal(ser: serial.Serial):
    """
    Lee un frame:
      [cmd:1][len:2 little][payload:len][crc:2 little]
    Retorna (cmd:int, payload:bytes) si CRC OK.
    """
    header = read_exact(ser, 3)
    cmd = header[0]
    length = int.from_bytes(header[1:3], "little")

    payload = read_exact(ser, length) if length > 0 else b""
    crc_bytes = read_exact(ser, 2)
    crc_rx = int.from_bytes(crc_bytes, "little")

    if not verificar_crc(cmd, length, payload, crc_rx):
        raise ValueError(
            f"CRC inválido. cmd=0x{cmd:02X} len={length} crc_rx=0x{crc_rx:04X}"
        )

    return cmd, payload

# ---------- Enviar frame ----------
def enviar_senal(ser: serial.Serial, cmd: int, payload: bytes = b""):
    frame = armar_frame(cmd, payload)
    ser.write(frame)

# ---------- Fetch: manda cmd y espera respuesta ----------
def fetch(ser: serial.Serial, cmd: int, payload: bytes = b"", retries: int = 3):
    """
    1) Envía un cmd (frame)
    2) Espera UNA respuesta válida
    3) Reintenta si hay timeout o CRC inválido
    """
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            # Limpia basura antes del intento (útil si quedaste desfasado)
            ser.reset_input_buffer()

            enviar_senal(ser, cmd, payload)
            rcmd, rpayload = recibir_senal(ser)

            # Opcional: exigir que el cmd de respuesta coincida
            if rcmd != cmd and rcmd != 0xFF:
                raise ValueError(f"Respuesta cmd inesperado: 0x{rcmd:02X} (esperaba 0x{cmd:02X})")

            return rcmd, rpayload

        except (TimeoutError, ValueError) as e:
            last_err = e
            # micro-pausa antes de reintentar
            time.sleep(0.05)

    raise RuntimeError(f"Fetch falló tras {retries} intentos. Último error: {last_err}")

# ---------- Ejemplo de uso ----------
if __name__ == "__main__":
    PORT = "COM5"
    BAUD = 115200

    # Comandos mínimos (deben coincidir con Arduino)
    CMD_READ_DESC = 0x01
    CMD_PING      = 0x02

    with serial.Serial(PORT, BAUD, timeout=0.3) as ser:
        print(f"Conectado a {PORT} @ {BAUD}")

        # Arduino suele resetear al abrir el puerto => espera
        time.sleep(1.8)
        ser.reset_input_buffer()

        # Handshake inicial (esto es lo que te faltaba)
        rcmd, pong = fetch(ser, CMD_PING, b"", retries=3)
        print(f"PING -> resp cmd=0x{rcmd:02X} payload(hex)={pong.hex(' ')}")

        rcmd, desc = fetch(ser, CMD_READ_DESC, b"", retries=3)
        print(f"DESC -> resp cmd=0x{rcmd:02X} payload(hex)={desc.hex(' ')}")

        # Loop (opcional): si no tienes más cmds, no hay nada que hacer.
        # Si luego implementan GET_STATUS, aquí lo pones cada X ms.
        while True:
            time.sleep(1)
