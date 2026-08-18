from __future__ import annotations

import os
import re
import secrets
import socket
from pathlib import Path

from ..errors import ManagerError
from ..shell import ShellRunner


def require_root() -> None:
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise ManagerError("Установка должна запускаться от root")


def validate_domain(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if not value:
        raise ManagerError("Домен не задан")
    if value.startswith(("http://", "https://")):
        raise ManagerError("Укажи домен без http:// или https://")
    if "/" in value:
        raise ManagerError("В домене не должно быть пути")
    if len(value) > 253:
        raise ManagerError("Слишком длинный домен")
    labels = value.split(".")
    rx = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    if len(labels) < 2 or any(not rx.match(x) for x in labels):
        raise ManagerError(f"Некорректный домен: {value}")
    return value


def resolve_domain(domain: str) -> list[str]:
    try:
        return sorted({x[4][0] for x in socket.getaddrinfo(domain, None)})
    except socket.gaierror:
        return []


def token_hex(size: int = 32) -> str:
    return secrets.token_hex(size)


def replace_env_value(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    found = False
    result: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            result.append(f"{key}={value}")
            found = True
        else:
            result.append(line)
    if not found:
        result.append(f"{key}={value}")
    return "\n".join(result) + "\n"


def replace_database_password(text: str, password: str) -> str:
    text = replace_env_value(text, "POSTGRES_PASSWORD", password)
    lines = []
    for line in text.splitlines():
        if line.startswith("DATABASE_URL="):
            raw = line[len("DATABASE_URL="):]
            quote = '"' if raw.startswith('"') and raw.endswith('"') else ""
            body = raw.strip('"')
            body = re.sub(
                r"^(postgresql://postgres:)[^@]*(@)",
                lambda m: m.group(1) + password + m.group(2),
                body,
            )
            line = f'DATABASE_URL={quote}{body}{quote}'
        lines.append(line)
    return "\n".join(lines) + "\n"


def ensure_docker(runner: ShellRunner) -> None:
    try:
        probe = runner.run(["docker", "version"], check=False)
    except Exception:
        probe = None
    if probe is not None and probe.returncode == 0:
        compose = runner.run(["docker", "compose", "version"], check=False)
        if compose.returncode == 0:
            return

    runner.run(["apt-get", "update"])
    runner.run(["apt-get", "install", "-y", "ca-certificates", "curl"])
    script = "/tmp/get-docker.sh"
    runner.run(["curl", "-fsSL", "https://get.docker.com", "-o", script])
    runner.run(["sh", script])
    runner.run(["docker", "compose", "version"])


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.chmod(tmp, mode)
    tmp.replace(path)
