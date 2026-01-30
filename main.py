import json
from core.event_bus import EventBus
from core.registry import SatelliteState, ModuleRegistry
from core.orchestrator import Orchestrator

def log_handler(e): 
    print("[LOG]", e)

def mode_handler(e):
    print(f"[MODE] -> {e['mode']} (why: {e['why']})")

def module_quarantine_handler(e):
    print(f"[QUARANTINE] {e['module_id']} because: {e['reasons']}")

def module_joined_handler(e):
    print(f"[JOINED] {e['module_id']}")

def connect_module(bus, reg, desc):
    ok, status, reasons = reg.discover_and_join(desc)
    if ok:
        bus.publish("MODULE_JOINED", {"module_id": desc["module_id"]})
    else:
        bus.publish("MODULE_QUARANTINED", {"module_id": desc.get("module_id","UNKNOWN"), "reasons": reasons, "status": status})

if __name__ == "__main__":
    bus = EventBus()
    state = SatelliteState()
    reg = ModuleRegistry(state)
    orch = Orchestrator(bus, state)

    # subscriptions (SPA-ish: data-centric, decoupled)
    bus.subscribe("LOG", log_handler)
    bus.subscribe("MODE_CHANGED", mode_handler)
    bus.subscribe("MODULE_QUARANTINED", module_quarantine_handler)
    bus.subscribe("MODULE_JOINED", module_joined_handler)

    bus.subscribe("MODULE_JOINED", orch.on_module_joined)
    bus.subscribe("SPACE_WEATHER", orch.on_space_weather)
    bus.subscribe("NEXT_PASS", orch.on_next_pass)
    bus.subscribe("ANOMALY", orch.on_anomaly)

    # ---- Demo sequence ----
    cpu = json.loads(open("spa_modules/cpu.json").read())      # or inline dict
    com = json.loads(open("spa_modules/comms.json").read())
    mystery = json.loads(open("spa_modules/mystery.json").read())

    bus.publish("LOG", {"msg": "Booting satellite OS..."})

    connect_module(bus, reg, cpu)      # should JOIN
    connect_module(bus, reg, com)      # should JOIN (requires COMPUTE)
    connect_module(bus, reg, mystery)  # should QUARANTINE

    # show it reacts to space data
    bus.publish("SPACE_WEATHER", {"kp": 2})
    bus.publish("NEXT_PASS", {"minutes": 7})  # should move to DOWNLINK if comms present

    # simulate worsening space weather -> SAFE
    bus.publish("SPACE_WEATHER", {"kp": 7})

    # simulate unknown anomaly
    bus.publish("ANOMALY", {"signature": "spike_power_draw_module_COM-001"})
