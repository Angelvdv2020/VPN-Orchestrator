from __future__ import annotations

from typing import Any


# Fields commonly returned by Remnawave responses but not normally accepted
# as editable DTO fields. The rollback engine preserves unknown editable fields
# and removes only strongly read-only/derived values.
READ_ONLY_KEYS = {
    "createdAt",
    "updatedAt",
    "lastStatusChange",
    "lastStatusMessage",
    "xrayVersion",
    "nodeVersion",
    "isConnected",
    "isDisabled",
    "usersOnline",
    "trafficUsedBytes",
    "uptime",
    "lastTrafficResetAt",
    "inboundsCount",
    "nodesCount",
    "hostsCount",
    "accessibleNodes",
}


def sanitize_update_object(obj: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in obj.items():
        if key in READ_ONLY_KEYS:
            continue
        if isinstance(value, dict):
            result[key] = sanitize_update_object(value)
        elif isinstance(value, list):
            result[key] = [
                sanitize_update_object(x) if isinstance(x, dict) else x
                for x in value
            ]
        else:
            result[key] = value
    return result
