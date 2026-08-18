from __future__ import annotations

import json
from pathlib import Path

from ..errors import ManagerError


def load_json_payload(path: Path) -> dict:
    if not path.exists():
        raise ManagerError(f"JSON payload не найден: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ManagerError(f"Не удалось прочитать JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise ManagerError("Node payload должен быть JSON-объектом")
    return data
