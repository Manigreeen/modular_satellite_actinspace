from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, List

REQUIRED_TOP_KEYS = {"module_id", "name", "vendor", "version", "certified", "interfaces", "capabilities", "constraints"}

@dataclass
class SatelliteLimits:
    power_bus_v: int = 28
    power_budget_w: int = 60
    thermal_budget_w: int = 30
    data_protocol: str = "SpaceWire"

@dataclass
class SatelliteState:
    limits: SatelliteLimits = field(default_factory=SatelliteLimits)
    # active/known modules
    modules: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tags_present: set = field(default_factory=set)  # e.g., {"COMPUTE"}

    used_power_w: int = 0
    used_thermal_w: int = 0

class ModuleRegistry:
    def __init__(self, state: SatelliteState):
        self.state = state
        self.quarantine: Dict[str, Dict[str, Any]] = {}

    def _basic_schema_check(self, desc: Dict[str, Any]) -> Tuple[bool, str]:
        missing = REQUIRED_TOP_KEYS - set(desc.keys())
        if missing:
            return False, f"Missing keys: {sorted(missing)}"
        if "power" not in desc["interfaces"] or "data" not in desc["interfaces"]:
            return False, "interfaces must include power and data"
        return True, "OK"

    def _compatibility_check(self, desc: Dict[str, Any]) -> Tuple[bool, List[str]]:
        reasons = []
        lim = self.state.limits

        # trust/certification gate (simple but hackathon-friendly)
        if not desc.get("certified", False):
            reasons.append("Module not certified (zero-trust policy).")

        # power bus compatibility
        bus_v = desc["interfaces"]["power"].get("bus_v")
        if bus_v != lim.power_bus_v:
            reasons.append(f"Power bus mismatch: sat {lim.power_bus_v}V vs module {bus_v}V")

        # data protocol compatibility
        protocol = desc["interfaces"]["data"].get("protocol")
        if protocol != lim.data_protocol:
            reasons.append(f"Data protocol mismatch: sat {lim.data_protocol} vs module {protocol}")

        # resource budgets
        max_w = int(desc["interfaces"]["power"].get("max_w", 0))
        thermal_w = int(desc["constraints"].get("thermal_w", 0))

        if self.state.used_power_w + max_w > lim.power_budget_w:
            reasons.append(f"Power budget exceeded: used {self.state.used_power_w}W + {max_w}W > {lim.power_budget_w}W")

        if self.state.used_thermal_w + thermal_w > lim.thermal_budget_w:
            reasons.append(f"Thermal budget exceeded: used {self.state.used_thermal_w}W + {thermal_w}W > {lim.thermal_budget_w}W")

        # dependency tags
        requires = set(desc["constraints"].get("requires", []))
        if not requires.issubset(self.state.tags_present):
            missing = sorted(list(requires - self.state.tags_present))
            if missing:
                reasons.append(f"Missing required capabilities/tags: {missing}")

        # conflicts
        conflicts = set(desc["constraints"].get("conflicts", []))
        if conflicts & self.state.tags_present:
            reasons.append(f"Conflicts with present tags: {sorted(list(conflicts & self.state.tags_present))}")

        return (len(reasons) == 0), reasons

    def discover_and_join(self, desc: Dict[str, Any]) -> Tuple[bool, str, List[str]]:
        ok, msg = self._basic_schema_check(desc)
        if not ok:
            # malformed = quarantine
            mid = desc.get("module_id", "UNKNOWN")
            self.quarantine[mid] = desc
            return False, "QUARANTINED_SCHEMA", [msg]

        compatible, reasons = self._compatibility_check(desc)
        mid = desc["module_id"]

        if not compatible:
            self.quarantine[mid] = desc
            return False, "QUARANTINED_COMPAT", reasons

        # join: register + consume budgets + add tags
        self.state.modules[mid] = desc
        max_w = int(desc["interfaces"]["power"].get("max_w", 0))
        thermal_w = int(desc["constraints"].get("thermal_w", 0))
        self.state.used_power_w += max_w
        self.state.used_thermal_w += thermal_w

        # tags: from compute capability or explicit tag field
        for cap in desc.get("capabilities", []):
            if cap.get("type") == "compute":
                self.state.tags_present.add("COMPUTE")
            if "tag" in cap:
                self.state.tags_present.add(cap["tag"])

        return True, "JOINED", []
    
    def remove_module(self, module_id: str) -> bool:
        """
        Remove a joined module from satellite state and recompute budgets/tags.
        Returns True if removed, False if not present.
        """
        if module_id not in self.state.modules:
            return False

        # Remove it
        self.state.modules.pop(module_id)

        # Recompute budgets + tags from scratch (simple & safe for hackathon)
        self.state.used_power_w = 0
        self.state.used_thermal_w = 0
        self.state.tags_present = set()

        for desc in self.state.modules.values():
            max_w = int(desc["interfaces"]["power"].get("max_w", 0))
            thermal_w = int(desc["constraints"].get("thermal_w", 0))
            self.state.used_power_w += max_w
            self.state.used_thermal_w += thermal_w

            for cap in desc.get("capabilities", []):
                if cap.get("type") == "compute":
                    self.state.tags_present.add("COMPUTE")
                if "tag" in cap:
                    self.state.tags_present.add(cap["tag"])

        return True

