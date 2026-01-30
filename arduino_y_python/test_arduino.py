import serial # Lectura y escritura en serial -> Bridge entre Python (lógica) y Arduino (físico)
import threading # Permite correr la lógica SPA y leer serial simultáneamente -> 2 Threads
import queue # Permite armar queues de mensajes -> Thread serial hace "enqueue" mensajes y Thread lógica hace "dequeue" (leer)
import jsonschema # Identificar JSONs de módulos válidos
import time

'''
def recibir_serial(port: str, baud:int = 115200, timeout:float = 0.1):
    """
    Abre el puerto serial y va imprimiendo TODO lo que llega como bytes y como texto (si aplica).
    Detén con Ctrl+C.
    """
    ser = serial.Serial(port, baudrate=baud, timeout=timeout)
    print(f"✅ Conectado a {ser.port} @ {baud} baud")

    try:
        while True:
            data = ser.read(256)  # lee hasta 256 bytes (no bloquea mucho por el timeout)
            if data:
                print("BYTES:", data)
                try:
                    print("TXT  :", data.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            time.sleep(0.01)  # evita usar 100% CPU
            
    except KeyboardInterrupt:
        print("\n🛑 Detenido por el usuario.")
        
    finally:
        ser.close()
        print("🔌 Puerto cerrado.")
'''

# ---------- CRC16-CCITT (FALSE) ----------
def crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    """
    CRC-16/CCITT-FALSE:
    poly=0x1021, init=0xFFFF, refin=False, refout=False, xorout=0x0000
    """
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
    """
    Verifica CRC usando: CRC(cmd + len_little + payload)
    cmd: int 0..255
    length: int 0..65535
    payload: bytes de tamaño length
    crc_rx: CRC recibido (int)
    """
    header = bytes([cmd]) + length.to_bytes(2, "little")
    calc = crc16_ccitt(header + payload)
    return calc == crc_rx


# ---------- Lectura exacta ----------
def read_exact(ser: serial.Serial, n: int) -> bytes:
    """
    Lee exactamente n bytes del serial (o lanza TimeoutError).
    """
    buf = bytearray()
    while len(buf) < n:
        chunk = ser.read(n - len(buf))
        if not chunk: # El chunk está vacío -> b''
            # timeout (o desconectado)
            print(f"[DEBUG] Timeout esperando {n} bytes; llevo {len(buf)} bytes.")
            raise TimeoutError(f"No llegaron {n} bytes a tiempo (llegaron {len(buf)}).")
        buf.extend(chunk)
    return bytes(buf)


# ---------- Recibir frame ----------
def recibir_senal(ser: serial.Serial):
    """
    Lee un frame con formato:
      [cmd:1][len:2 little][payload:len][crc:2 little]
    Verifica CRC y retorna:
      (cmd:int, payload:bytes)  si OK
    Lanza ValueError si CRC falla.
    Lanza TimeoutError si no llegan bytes.
    """
    # 1) Header: 3 bytes
    header = read_exact(ser, 3)
    cmd = header[0]
    length = int.from_bytes(header[1:3], "little")
    print(f"[DEBUG] Header cmd=0x{cmd:02X} len={length}")

    # 2) Payload
    payload = read_exact(ser, length) if length > 0 else b""

    # 3) CRC (2 bytes little)
    crc_bytes = read_exact(ser, 2)
    crc_rx = int.from_bytes(crc_bytes, "little")

    # 4) Verificación
    if not verificar_crc(cmd, length, payload, crc_rx):
        raise ValueError(
            f"CRC inválido. cmd=0x{cmd:02X} len={length} "
            f"crc_rx=0x{crc_rx:04X}"
        )

    return cmd, payload


# ---------- Ejemplo de uso ----------
if __name__ == "__main__":
    PORT = "COM5"          # cambia esto
    BAUD = 115200

    with serial.Serial(PORT, BAUD, timeout=0.2) as ser:
        print(f"Conectado a {PORT} @ {BAUD}")
        while True:
            try:
                cmd, payload = recibir_senal(ser)
                print(f"\nFRAME OK -> cmd=0x{cmd:02X} len={len(payload)}")
                # si payload es texto/JSON:
                try:
                    print("payload(txt):", payload.decode("utf-8", errors="replace"))
                except Exception:
                    print("payload(raw):", payload)

            except TimeoutError:
                # no llegó nada en el periodo; no es error fatal, seguimos
                continue
            except ValueError as e:
                print("⚠️", e)
                # en protocolos sin SYNC, tras un error puedes quedar desfasado
                # (para pruebas puedes seguir intentando, o luego agregamos un SYNC)
                continue