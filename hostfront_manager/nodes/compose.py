from __future__ import annotations

import re

from ..errors import ManagerError
from .models import NodeRuntimeSpec


def _safe_scalar(value: str) -> str:
    if not value:
        raise ManagerError("Пустое значение в NodeRuntimeSpec")
    if "\n" in value or "\r" in value:
        raise ManagerError("Переносы строк в значениях ноды запрещены")
    # Quote YAML scalar if it contains anything outside a conservative set.
    if re.fullmatch(r"[A-Za-z0-9._:/+\-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_node_compose(spec: NodeRuntimeSpec) -> str:
    if not 1 <= spec.node_port <= 65535:
        raise ManagerError("NODE_PORT должен быть 1..65535")
    if spec.nofile < 1024:
        raise ManagerError("nofile слишком мал")

    lines = [
        "services:",
        "  remnanode:",
        "    container_name: remnanode",
        "    hostname: remnanode",
        f"    image: {_safe_scalar(spec.image)}",
        "    network_mode: host",
        "    restart: always",
    ]

    if spec.enable_net_admin:
        lines.extend([
            "    cap_add:",
            "      - NET_ADMIN",
        ])

    lines.extend([
        "    ulimits:",
        "      nofile:",
        f"        soft: {spec.nofile}",
        f"        hard: {spec.nofile}",
        "    environment:",
        f"      - NODE_PORT={spec.node_port}",
        f"      - SECRET_KEY={_safe_scalar(spec.secret_key)}",
        "",
    ])
    return "\n".join(lines)
