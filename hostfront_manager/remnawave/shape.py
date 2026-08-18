from __future__ import annotations

from typing import Any


def unwrap_list(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = unwrap_list(value, keys)
            if nested:
                return nested
    return []


def first_uuid(payload: Any) -> str | None:
    if isinstance(payload, dict):
        value = payload.get("uuid")
        if isinstance(value, str) and value:
            return value
        for child in payload.values():
            result = first_uuid(child)
            if result:
                return result
    elif isinstance(payload, list):
        for child in payload:
            result = first_uuid(child)
            if result:
                return result
    return None


def obj_name(obj: dict[str, Any]) -> str:
    for key in ("name", "remark", "profileName", "nodeName"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def find_by_name(payload: Any, name: str, keys: tuple[str, ...]) -> dict[str, Any] | None:
    for row in unwrap_list(payload, keys):
        if obj_name(row) == name:
            return row
    return None
