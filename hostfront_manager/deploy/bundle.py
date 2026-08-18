from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ManagerError


@dataclass(slots=True)
class MobileBundle:
    root: Path
    xray_config: dict[str, Any]
    inbound_map: dict[str, Any]
    host_plan: list[dict[str, Any]]
    squad_plan: dict[str, Any]
    node_roles: dict[str, Any]
    client_metadata: dict[str, Any]


def _read_json(path: Path, expected_type):
    if not path.exists():
        raise ManagerError(f"Bundle file отсутствует: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ManagerError(f"Ошибка JSON {path}: {exc}") from exc
    if not isinstance(value, expected_type):
        raise ManagerError(f"Неверный тип данных в {path}")
    return value


def load_mobile_bundle(root: Path) -> MobileBundle:
    return MobileBundle(
        root=root,
        xray_config=_read_json(root / "xray-config.json", dict),
        inbound_map=_read_json(root / "inbound-map.json", dict),
        host_plan=_read_json(root / "host-plan.json", list),
        squad_plan=_read_json(root / "squad-plan.json", dict),
        node_roles=_read_json(root / "node-roles.json", dict),
        client_metadata=_read_json(root / "client-metadata.json", dict),
    )
