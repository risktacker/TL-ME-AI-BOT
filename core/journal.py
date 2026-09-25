"""Atomic runtime state and append-only trade/event journal."""
from __future__ import annotations
from datetime import datetime, timezone
import csv
import json
import os
from pathlib import Path
from typing import Any


class RuntimeStore:
    def __init__(self, root: Path = Path("runtime")) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, name: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
        try: return json.loads((self.root / f"{name}.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError): return dict(fallback or {})

    def write(self, name: str, payload: dict[str, Any]) -> None:
        target = self.root / f"{name}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        os.replace(temporary, target)

    def event(self, kind: str, **fields: Any) -> None:
        target = self.root / "events.csv"
        exists = target.exists()
        row = {"time": datetime.now(timezone.utc).isoformat(), "kind": kind,
               "payload": json.dumps(fields, default=str, separators=(",", ":"))}
        with target.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=row)
            if not exists: writer.writeheader()
            writer.writerow(row)
