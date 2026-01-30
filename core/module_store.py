from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List
import json
import time

@dataclass
class ModuleStore:
    modules_dir: Path

    def __post_init__(self) -> None:
        self.modules_dir.mkdir(parents=True, exist_ok=True)

    def list_files(self) -> List[Path]:
        return sorted(self.modules_dir.glob("*.json"))

    def load_all(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for p in self.list_files():
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception as e:
                # Bad JSON shouldn't crash the whole app
                print(f"[WARN] Could not load {p.name}: {e}")
        return out

    def save_descriptor(self, desc: Dict[str, Any], filename: str | None = None) -> Path:
        """
        Save descriptor as a JSON file. If filename is None, make one using module_id + timestamp.
        Uses atomic write to avoid partially-written files.
        """
        module_id = desc.get("module_id", "UNKNOWN")
        safe_id = "".join(c for c in module_id if c.isalnum() or c in ("-", "_"))
        ts = int(time.time())
        name = filename or f"{safe_id}_{ts}.json"
        if not name.endswith(".json"):
            name += ".json"

        path = self.modules_dir / name
        tmp = self.modules_dir / (name + ".tmp")

        tmp.write_text(json.dumps(desc, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)  # atomic on most OSes

        return path
