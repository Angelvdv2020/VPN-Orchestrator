from __future__ import annotations

from typing import Any


SENSITIVE_KEYS = frozenset({
    "auth",
    "authorization",
    "hysteriaauth",
    "password",
    "privatekey",
    "realityprivatekey",
    "secret",
    "secretkey",
    "token",
})


def redact_sensitive(value: Any) -> Any:
    """Return a JSON-compatible copy with common secret-bearing fields redacted."""
    if isinstance(value, dict):
        return {
            key: "***" if key.replace("_", "").lower() in SENSITIVE_KEYS
            else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value
