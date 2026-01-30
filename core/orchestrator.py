from typing import Dict, Any

class Orchestrator:
    def __init__(self, bus, state):
        self.bus = bus
        self.state = state
        self.mode = "IDLE"
        self.kp_index = 1.0
        self.next_pass_minutes = None

    def on_module_joined(self, e: dict):
        self._recompose(reason=f"module joined: {e['module_id']}")

    def on_space_weather(self, e: dict):
        self.kp_index = float(e["kp"])
        self._recompose(reason=f"space weather kp={self.kp_index}")

    def on_next_pass(self, e: dict):
        self.next_pass_minutes = int(e["minutes"])
        self._recompose(reason=f"next pass in {self.next_pass_minutes} min")

    def on_anomaly(self, e: dict):
        # very simple “learning”: record best action for this signature
        signature = e.get("signature", "unknown")
        self.bus.publish("LOG", {"msg": f"Anomaly detected: {signature}. Entering SAFE MODE."})
        self.mode = "SAFE"
        self.bus.publish("MODE_CHANGED", {"mode": self.mode, "why": "anomaly"})

    def _recompose(self, reason: str):
        # Rule 1: high space weather => SAFE
        if self.kp_index >= 6:
            new_mode = "SAFE"

        # Rule 2: if pass soon => DOWNLINK
        elif self.next_pass_minutes is not None and self.next_pass_minutes <= 10 and self._has_capability("comms"):
            new_mode = "DOWNLINK"

        # Rule 3: if imaging exists and safe => IMAGING
        elif self._has_capability("imaging"):
            new_mode = "IMAGING"

        else:
            new_mode = "IDLE"

        if new_mode != self.mode:
            self.mode = new_mode
            self.bus.publish("MODE_CHANGED", {"mode": self.mode, "why": reason})

    def _has_capability(self, cap_type: str) -> bool:
        for m in self.state.modules.values():
            for cap in m.get("capabilities", []):
                if cap.get("type") == cap_type:
                    return True
        return False
