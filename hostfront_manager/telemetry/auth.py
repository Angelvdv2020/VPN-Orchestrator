from __future__ import annotations

import hashlib
import hmac
import os
import re
import time

from ..errors import ManagerError

DEVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def device_env_name(prefix: str, device_id: str) -> str:
    if not DEVICE_RE.fullmatch(device_id):
        raise ManagerError("Некорректный device id")
    # Encode the complete ID; punctuation must not collapse (phone-1 != phone_1).
    encoded = device_id.encode("utf-8").hex().upper()
    return f"{prefix}ID_{encoded}"


def device_secret(prefix: str, device_id: str) -> str | None:
    return os.getenv(device_env_name(prefix, device_id))


def signing_message(timestamp: str, nonce: str, body: bytes) -> bytes:
    return timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body


def sign(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    return hmac.new(
        secret.encode(), signing_message(timestamp, nonce, body), hashlib.sha256
    ).hexdigest()


def verify(
    secret: str,
    timestamp: str,
    nonce: str,
    body: bytes,
    signature: str,
    *,
    max_skew: int,
    now: int | None = None,
) -> None:
    if not NONCE_RE.fullmatch(nonce):
        raise ManagerError("Некорректный nonce")
    try:
        sent = int(timestamp)
    except ValueError as exc:
        raise ManagerError("Некорректный timestamp") from exc
    current = int(time.time()) if now is None else now
    if abs(current - sent) > max_skew:
        raise ManagerError("Telemetry timestamp вне допустимого окна")
    expected = sign(secret, timestamp, nonce, body)
    if not hmac.compare_digest(expected, signature.lower()):
        raise ManagerError("Неверная telemetry signature")
