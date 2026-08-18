from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_STATE = {
    "state": "unknown",
    "failure_streak": 0,
    "recovery_streak": 0,
    "repair_timestamps": [],
    "last_repair_at": None,
    "last_check_at": None,
    "last_signals": [],
    "history": [],
}


class WatchdogStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_STATE)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_STATE)
        result = dict(DEFAULT_STATE)
        if isinstance(data, dict):
            result.update(data)
        return result

    def save(self, state: dict[str, Any]) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self.path)
        return self.path
