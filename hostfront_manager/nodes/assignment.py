from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, asdict
from typing import Any

from ..errors import ManagerError


@dataclass(slots=True)
class AssignmentShape:
    container_key: str
    profile_key: str
    inbounds_key: str
    verified: bool

    def to_dict(self):
        return asdict(self)


@dataclass(slots=True)
class AssignmentPlan:
    node_uuid: str
    role: str
    profile_uuid: str
    inbound_uuids: list[str]
    desired_tags: list[str]
    shape: AssignmentShape
    patch_payload: dict[str, Any]

    def to_dict(self):
        return {
            "node_uuid": self.node_uuid,
            "role": self.role,
            "profile_uuid": self.profile_uuid,
            "inbound_uuids": self.inbound_uuids,
            "desired_tags": self.desired_tags,
            "shape": self.shape.to_dict(),
            "patch_payload": self.patch_payload,
        }


def _unwrap_one(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        if isinstance(payload.get("response"), dict):
            return payload["response"]
        if isinstance(payload.get("data"), dict):
            return payload["data"]
        return payload
    raise ManagerError("Node API response не object")


def discover_assignment_shape(node_payload: Any) -> AssignmentShape:
    node = _unwrap_one(node_payload)

    # Runtime schema discovery: find a nested dict that already describes
    # the node's core/profile configuration. No undocumented key is invented.
    for container_key, value in node.items():
        if not isinstance(value, dict):
            continue

        profile_keys = [
            k for k in value
            if "profile" in k.lower() and ("uuid" in k.lower() or "id" in k.lower())
        ]
        inbound_keys = [
            k for k in value
            if "inbound" in k.lower() and isinstance(value.get(k), list)
        ]

        if profile_keys and inbound_keys:
            return AssignmentShape(
                container_key=container_key,
                profile_key=profile_keys[0],
                inbounds_key=inbound_keys[0],
                verified=True,
            )

    raise ManagerError(
        "Manager не смог безопасно определить поля назначения Config Profile/Inbounds "
        "в ответе текущей версии Remnawave. Ничего не изменено."
    )


def build_assignment_plan(
    node_payload: Any,
    *,
    node_uuid: str,
    role: str,
    profile_uuid: str,
    role_tags: list[str],
    inbounds_by_tag: dict[str, dict[str, Any]],
) -> AssignmentPlan:
    shape = discover_assignment_shape(node_payload)

    missing = [tag for tag in role_tags if tag not in inbounds_by_tag]
    if missing:
        raise ManagerError("Не найдены inbound tags: " + ", ".join(missing))

    inbound_uuids: list[str] = []
    for tag in role_tags:
        uuid = inbounds_by_tag[tag].get("uuid")
        if not uuid:
            raise ManagerError(f"Inbound {tag} не содержит uuid")
        inbound_uuids.append(str(uuid))

    node = _unwrap_one(node_payload)
    patch = {"uuid": node_uuid}
    container = deepcopy(node.get(shape.container_key, {}))
    container[shape.profile_key] = profile_uuid
    container[shape.inbounds_key] = inbound_uuids
    patch[shape.container_key] = container

    return AssignmentPlan(
        node_uuid=node_uuid,
        role=role,
        profile_uuid=profile_uuid,
        inbound_uuids=inbound_uuids,
        desired_tags=role_tags,
        shape=shape,
        patch_payload=patch,
    )
