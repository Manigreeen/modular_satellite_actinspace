from __future__ import annotations
import json
from pathlib import Path

from core.event_bus import EventBus
from core.registry import SatelliteState, ModuleRegistry
from core.orchestrator import Orchestrator
from core.module_store import ModuleStore


def pretty_state(state: SatelliteState) -> str:
    lines = []
    lines.append(f"Modules joined: {len(state.modules)} | Quarantine: N/A (stored in registry)")
    lines.append(f"Used power: {state.used_power_w}W / {state.limits.power_budget_w}W")
    lines.append(f"Used thermal: {state.used_thermal_w}W / {state.limits.thermal_budget_w}W")
    lines.append(f"Tags present: {sorted(list(state.tags_present))}")
    lines.append("Joined module_ids: " + ", ".join(sorted(state.modules.keys())) if state.modules else "Joined module_ids: (none)")
    return "\n".join(lines)


def connect_module(bus: EventBus, reg: ModuleRegistry, desc: dict) -> None:
    ok, status, reasons = reg.discover_and_join(desc)
    if ok:
        bus.publish("MODULE_JOINED", {"module_id": desc["module_id"]})
    else:
        bus.publish("MODULE_QUARANTINED", {
            "module_id": desc.get("module_id", "UNKNOWN"),
            "status": status,
            "reasons": reasons,
        })


def main() -> None:
    root = Path(__file__).parent
    modules_dir = root / "spa_modules"

    bus = EventBus()
    state = SatelliteState()
    reg = ModuleRegistry(state)
    store = ModuleStore(modules_dir)
    orch = Orchestrator(bus, state)

    # ---- Subscribers (callbacks) ----
    bus.subscribe("LOG", lambda e: print("[LOG]", e.get("msg", e)))
    bus.subscribe("MODE_CHANGED", lambda e: print(f"[MODE] -> {e['mode']} (why: {e['why']})"))
    bus.subscribe("MODULE_JOINED", lambda e: print(f"[JOINED] {e['module_id']}"))
    bus.subscribe("MODULE_QUARANTINED", lambda e: print(f"[QUARANTINE] {e['module_id']} | {e['status']} | {e['reasons']}"))
    bus.subscribe("MODULE_REMOVED", lambda e: print(f"[REMOVED] {e['module_id']}"))

    bus.subscribe("MODULE_JOINED", orch.on_module_joined)
    bus.subscribe("SPACE_WEATHER", orch.on_space_weather)
    bus.subscribe("NEXT_PASS", orch.on_next_pass)
    bus.subscribe("ANOMALY", orch.on_anomaly)

    # ---- Boot: load all modules already on disk ----
    bus.publish("LOG", {"msg": "Booting interactive satellite orchestrator..."})
    for desc in store.load_all():
        connect_module(bus, reg, desc)

    print("\nType 'help' to see commands.\n")

    # ---- Interactive loop (REPL) ----
    while True:
        try:
            cmd = input("sat> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not cmd:
            continue

        parts = cmd.split()
        op = parts[0].lower()

        if op in ("quit", "exit"):
            print("Bye.")
            break

        elif op == "help":
            print(
                "\nCommands:\n"
                "  state                         Show current satellite state\n"
                "  kp <value>                    Publish SPACE_WEATHER (kp index)\n"
                "  pass <minutes>                Publish NEXT_PASS (minutes to next pass)\n"
                "  anomaly <signature>           Publish ANOMALY event\n"
                "  connect_file <path.json>      Load a descriptor from file and try to join\n"
                "  connect_json                  Paste JSON descriptor (ends with a blank line)\n"
                "  disconnect <module_id>        Remove a joined module\n"
                "  list_modules                  List descriptor files in ./modules\n"
                "  save_json                     Paste JSON descriptor and save to ./modules then join\n"
                "  quit / exit                   Stop the app\n"
            )

        elif op == "state":
            print(pretty_state(state))
            print("Quarantine IDs:", ", ".join(sorted(reg.quarantine.keys())) if reg.quarantine else "(none)")

        elif op == "kp" and len(parts) >= 2:
            bus.publish("SPACE_WEATHER", {"kp": float(parts[1])})

        elif op == "pass" and len(parts) >= 2:
            bus.publish("NEXT_PASS", {"minutes": int(parts[1])})

        elif op == "anomaly" and len(parts) >= 2:
            signature = " ".join(parts[1:])
            bus.publish("ANOMALY", {"signature": signature})

        elif op == "list_modules":
            files = store.list_files()
            if not files:
                print("(no module JSON files found)")
            else:
                for p in files:
                    print("-", p.name)

        elif op == "connect_file" and len(parts) >= 2:
            p = Path(parts[1]).expanduser()
            if not p.exists():
                print("File not found.")
                continue
            try:
                desc = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                print("Invalid JSON:", e)
                continue
            connect_module(bus, reg, desc)

        elif op == "disconnect" and len(parts) >= 2:
            module_id = parts[1]
            if reg.remove_module(module_id):
                bus.publish("MODULE_REMOVED", {"module_id": module_id})
                # recomposition after removal (force re-evaluate)
                orch._recompose(reason=f"module removed: {module_id}")
            else:
                print("Module not joined:", module_id)

        elif op in ("connect_json", "save_json"):
            print("Paste JSON (end with an empty line):")
            lines = []
            while True:
                line = input()
                if line.strip() == "":
                    break
                lines.append(line)
            raw = "\n".join(lines)
            try:
                desc = json.loads(raw)
            except Exception as e:
                print("Invalid JSON:", e)
                continue

            if op == "save_json":
                path = store.save_descriptor(desc)
                print(f"Saved to {path}")
            connect_module(bus, reg, desc)

        else:
            print("Unknown command. Type 'help'.")

if __name__ == "__main__":
    main()
