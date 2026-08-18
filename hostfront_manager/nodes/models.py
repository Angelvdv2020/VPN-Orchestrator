from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import StrEnum
from typing import Any


class PlanAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    ENABLE = "enable"
    DISABLE = "disable"
    DELETE = "delete"
    NOOP = "noop"


@dataclass(slots=True)
class RemoteTarget:
    host: str
    user: str = "root"
    ssh_port: int = 22
    identity_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NodeRuntimeSpec:
    node_port: int
    secret_key: str
    image: str = "remnawave/node:latest"
    enable_net_admin: bool = True
    mount_letsencrypt: bool = False
    nofile: int = 1048576

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["secret_key"] = "***"
        return data


@dataclass(slots=True)
class NodePlan:
    action: PlanAction
    name: str
    reason: str
    current_uuid: str | None = None
    desired_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "name": self.name,
            "reason": self.reason,
            "current_uuid": self.current_uuid,
            "desired_payload": self.desired_payload,
        }
