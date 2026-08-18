from __future__ import annotations

import re
import secrets
import shutil
import uuid
import base64
from dataclasses import dataclass, asdict
from typing import Any

from ..errors import ManagerError
from ..shell import ShellRunner


@dataclass(slots=True)
class GeneratedSecrets:
    vless_uuid: str
    short_id: str
    hysteria_auth: str
    reality_private_key: str | None
    reality_password: str | None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "vless_uuid": self.vless_uuid,
            "short_id": self.short_id,
            "hysteria_auth": "***",
            "reality_private_key": "***" if self.reality_private_key else None,
            "reality_password": self.reality_password,
        }


def generate_basic() -> tuple[str, str, str]:
    return (
        str(uuid.uuid4()),
        secrets.token_hex(8),  # 16 hex chars = 8 bytes
        secrets.token_urlsafe(32),
    )


def generate_reality_keypair(runner: ShellRunner, xray_binary: str = "xray") -> tuple[str, str]:
    binary = shutil.which(xray_binary)
    if not binary:
        # Xray stores X25519 keys as unpadded URL-safe base64.  Generate the
        # same raw 32-byte representation without forcing users to install a
        # separate CLI binary just to complete first-run setup.
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        except ImportError as exc:
            raise ManagerError(
                "Для автоматической генерации REALITY нужен пакет cryptography. "
                "Повторите установку Manager или передайте существующий private key."
            ) from exc
        private = X25519PrivateKey.generate()
        encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
        private_raw = private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        public_raw = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return encode(private_raw), encode(public_raw)
    result = runner.run([binary, "x25519"])
    text = result.stdout + "\n" + result.stderr

    private_patterns = [
        r"Private key:\s*(\S+)",
        r"PrivateKey:\s*(\S+)",
        r"Private:\s*(\S+)",
    ]
    public_patterns = [
        r"Password:\s*(\S+)",
        r"Public key:\s*(\S+)",
        r"PublicKey:\s*(\S+)",
        r"Public:\s*(\S+)",
    ]

    private_key = next(
        (m.group(1) for p in private_patterns if (m := re.search(p, text, re.I))),
        None,
    )
    public_key = next(
        (m.group(1) for p in public_patterns if (m := re.search(p, text, re.I))),
        None,
    )

    if not private_key or not public_key:
        raise ManagerError("Не удалось распознать вывод `xray x25519`")
    return private_key, public_key
