from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY: dict[str, Any] = {
    "schema": 1,
    "mode": "manager-owned",
    "locations": [],
    "updated_at": None,
}


def _path(data_dir: Path) -> Path:
    return data_dir / "orchestrator-registry.json"


def load_registry(data_dir: Path) -> dict[str, Any]:
    path = _path(data_dir)
    if not path.exists():
        return dict(DEFAULT_REGISTRY)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_REGISTRY)
    if not isinstance(raw, dict):
        return dict(DEFAULT_REGISTRY)
    result = dict(DEFAULT_REGISTRY)
    result.update(raw)
    if result.get("mode") not in {"manager-owned", "safe-attach"}:
        result["mode"] = "manager-owned"
    if not isinstance(result.get("locations"), list):
        result["locations"] = []
    return result


def save_registry(data_dir: Path, value: dict[str, Any]) -> dict[str, Any]:
    mode = value.get("mode", "manager-owned")
    if mode not in {"manager-owned", "safe-attach"}:
        raise ValueError("mode must be manager-owned or safe-attach")
    locations = value.get("locations", [])
    if not isinstance(locations, list):
        raise ValueError("locations must be an array")
    cleaned: list[dict[str, Any]] = []
    for item in locations[:100]:
        if not isinstance(item, dict):
            continue
        location = {
            "id": str(item.get("id", ""))[:64],
            "name": str(item.get("name", ""))[:120],
            "country": str(item.get("country", ""))[:2].upper(),
            "flag": str(item.get("flag", ""))[:8],
            "mode": str(item.get("mode", mode)),
            "profile_uuid": str(item.get("profile_uuid", ""))[:64],
            "node_uuid": str(item.get("node_uuid", ""))[:64],
            "squad_uuid": str(item.get("squad_uuid", ""))[:64],
            "notes": str(item.get("notes", ""))[:500],
        }
        if location["id"]:
            cleaned.append(location)
    result = {
        "schema": 1,
        "mode": mode,
        "locations": cleaned,
        "updated_at": value.get("updated_at"),
    }
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="orchestrator-registry-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return result
