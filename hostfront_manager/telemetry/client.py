from __future__ import annotations

import json
import secrets
import time
import urllib.error
import urllib.request
from typing import Any

from ..errors import ManagerError
from .auth import sign


def submit(endpoint: str, device_id: str, secret: str, payload: dict[str, Any], *, timeout: int = 15) -> dict[str, Any]:
    if not endpoint.startswith("https://"):
        raise ManagerError("Telemetry endpoint должен использовать HTTPS")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/api/v1/telemetry",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Device-ID": device_id,
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": sign(secret, timestamp, nonce, body),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise ManagerError(f"Telemetry HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ManagerError(f"Telemetry endpoint недоступен: {exc}") from exc
