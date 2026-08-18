from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import ManagerError
from ..remnawave.client import RemnawaveClient
from .bundle import MobileBundle


READ_ONLY_KEYS = {
    "uuid", "id", "createdAt", "updatedAt", "viewPosition",
    "nodes", "hosts", "inboundsCount", "nodesCount",
}


def _unwrap_list(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = _unwrap_list(value, keys)
            if nested:
                return nested
    return []


def _strip_read_only(obj: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in obj.items() if k not in READ_ONLY_KEYS}


def _name(obj: dict[str, Any]) -> str:
    return str(obj.get("name") or obj.get("remark") or "")


@dataclass(slots=True)
class AdapterResult:
    kind: str
    action: str
    response: Any


class RemnawaveV32Adapter:
    """Compatibility adapter for the 3.2 API family.

    The adapter is intentionally conservative:
    - it can CREATE/UPDATE a Config Profile using the documented controller;
    - Hosts/Squads are only mutated after live inbound objects are available;
    - it refuses to invent inbound UUIDs.
    """

    def __init__(self, client: RemnawaveClient):
        self.client = client

    def apply_profile(
        self,
        bundle: MobileBundle,
        *,
        existing_profile: dict[str, Any] | None,
    ) -> AdapterResult:
        profile_name = str(bundle.client_metadata.get("profile") or "Mobile")

        # Remnawave Config Profile concept is a named full Xray-core configuration.
        # Current API request DTOs may carry additional optional fields; keep only
        # the core fields needed by the controller.
        payload = {
            "name": profile_name,
            "config": bundle.xray_config,
        }

        if existing_profile:
            uuid = existing_profile.get("uuid")
            if not uuid:
                raise ManagerError("У существующего Config Profile нет uuid")
            payload["uuid"] = uuid
            response = self.client.update_config_profile(payload)
            return AdapterResult("config-profile", "update", response)

        response = self.client.create_config_profile(payload)
        return AdapterResult("config-profile", "create", response)

    def resolve_inbounds(self, profile_uuid: str) -> dict[str, dict[str, Any]]:
        raw = self.client.get_config_profile_inbounds(profile_uuid)
        rows = _unwrap_list(raw, ("inbounds", "response", "data"))
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            tag = row.get("tag") or row.get("inboundTag")
            if isinstance(tag, str) and tag:
                result[tag] = row
        return result

    def build_host_payload(
        self,
        desired: dict[str, Any],
        inbound: dict[str, Any],
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        inbound_uuid = inbound.get("uuid")
        profile_uuid = inbound.get("profileUuid") or inbound.get("configProfileUuid")
        if not inbound_uuid or not profile_uuid:
            raise ManagerError(f"Inbound {desired.get('inbound_tag')} не содержит uuid")

        payload = _strip_read_only(existing or {})
        payload.update({
            "remark": desired.get("remark"),
            "address": desired.get("address"),
            "port": desired.get("port"),
            "inbound": {
                "configProfileUuid": profile_uuid,
                "configProfileInboundUuid": inbound_uuid,
            },
        })
        for key in (
            "path",
            "sni",
            "host",
            "alpn",
            "fingerprint",
            "securityLayer",
            "xhttpExtraParams",
        ):
            if key in desired:
                payload[key] = desired[key]
        if existing and existing.get("uuid"):
            payload["uuid"] = existing["uuid"]
        return payload

    def apply_host(
        self,
        desired: dict[str, Any],
        inbound: dict[str, Any],
        *,
        existing: dict[str, Any] | None,
    ) -> AdapterResult:
        payload = self.build_host_payload(desired, inbound, existing)
        if existing:
            return AdapterResult("host", "update", self.client.update_host(payload))
        return AdapterResult("host", "create", self.client.create_host(payload))

    def build_squad_payload(
        self,
        bundle: MobileBundle,
        inbounds: dict[str, dict[str, Any]],
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        desired_tags = list(bundle.squad_plan.get("inbound_tags", []))
        inbound_uuids: list[str] = []
        missing: list[str] = []

        for tag in desired_tags:
            row = inbounds.get(tag)
            if not row or not row.get("uuid"):
                missing.append(tag)
            else:
                inbound_uuids.append(str(row["uuid"]))

        if missing:
            raise ManagerError(
                "Не удалось разрешить inbound UUID для Squad: " + ", ".join(missing)
            )

        payload = _strip_read_only(existing or {})
        payload.update({
            "name": bundle.squad_plan.get("name"),
            "inbounds": inbound_uuids,
        })
        if existing and existing.get("uuid"):
            payload["uuid"] = existing["uuid"]
        return payload

    def apply_squad(
        self,
        bundle: MobileBundle,
        inbounds: dict[str, dict[str, Any]],
        *,
        existing: dict[str, Any] | None,
    ) -> AdapterResult:
        payload = self.build_squad_payload(bundle, inbounds, existing)
        if existing:
            return AdapterResult(
                "internal-squad",
                "update",
                self.client.update_internal_squad(payload),
            )
        return AdapterResult(
            "internal-squad",
            "create",
            self.client.create_internal_squad(payload),
        )
