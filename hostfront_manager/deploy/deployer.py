from __future__ import annotations

from typing import Any

from ..errors import ManagerError
from ..remnawave.capabilities import Capabilities
from ..remnawave.client import RemnawaveClient
from .adapter_v32 import RemnawaveV32Adapter
from .bundle import MobileBundle
from .journal import Transaction, TransactionJournal


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


def _name(obj: dict[str, Any]) -> str:
    return str(obj.get("name") or obj.get("remark") or "")


def _uuid_from_response(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("uuid",):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        for value in payload.values():
            found = _uuid_from_response(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _uuid_from_response(value)
            if found:
                return found
    return None


def apply_mobile_bundle_v32(
    client: RemnawaveClient,
    caps: Capabilities,
    bundle: MobileBundle,
    journal: TransactionJournal,
    tx: Transaction,
    *,
    required_version_prefix: str,
) -> dict[str, Any]:
    if caps.api_version and required_version_prefix:
        if not caps.api_version.startswith(required_version_prefix):
            raise ManagerError(
                f"API version {caps.api_version} не соответствует "
                f"разрешённому префиксу {required_version_prefix}"
            )

    required = {
        "config_profiles": caps.config_profiles,
        "hosts": caps.hosts,
        "internal_squads": caps.internal_squads,
        "nodes": caps.nodes,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise ManagerError("Нет обязательных API capabilities: " + ", ".join(missing))

    adapter = RemnawaveV32Adapter(client)
    results: list[dict[str, Any]] = []

    # Phase 1: profile.
    profiles_raw = client.get_config_profiles()
    profiles = _unwrap_list(
        profiles_raw,
        ("configProfiles", "config_profiles", "response", "data"),
    )
    profile_name = str(bundle.client_metadata.get("profile") or "Mobile")
    existing_profile = next((x for x in profiles if _name(x) == profile_name), None)

    profile_result = adapter.apply_profile(bundle, existing_profile=existing_profile)
    results.append({
        "phase": 1,
        "kind": profile_result.kind,
        "action": profile_result.action,
        "response": profile_result.response,
    })
    journal.write_json(tx.path / "phase1-profile.json", results[-1])

    profile_uuid = (
        str(existing_profile.get("uuid")) if existing_profile and existing_profile.get("uuid")
        else _uuid_from_response(profile_result.response)
    )
    if not profile_uuid:
        # Re-read list because create responses may be wrapped differently.
        profiles = _unwrap_list(
            client.get_config_profiles(),
            ("configProfiles", "config_profiles", "response", "data"),
        )
        live = next((x for x in profiles if _name(x) == profile_name), None)
        profile_uuid = str(live.get("uuid")) if live and live.get("uuid") else None

    if not profile_uuid:
        raise ManagerError("После apply Config Profile не удалось определить его uuid")

    # Phase 2: resolve real inbounds produced by Remnawave.
    inbounds = adapter.resolve_inbounds(profile_uuid)
    missing_tags = [tag for tag in bundle.inbound_map if tag not in inbounds]
    if missing_tags:
        raise ManagerError(
            "После создания профиля Remnawave не вернул ожидаемые Inbounds: "
            + ", ".join(missing_tags)
        )
    journal.write_json(tx.path / "phase2-inbounds.json", inbounds)

    # Phase 3: Hosts.
    hosts_raw = client.get_hosts()
    hosts = _unwrap_list(hosts_raw, ("hosts", "response", "data"))
    for desired in bundle.host_plan:
        name = str(desired.get("remark") or "")
        existing = next((x for x in hosts if _name(x) == name), None)
        tag = str(desired.get("inbound_tag") or "")
        result = adapter.apply_host(desired, inbounds[tag], existing=existing)
        row = {
            "phase": 3,
            "kind": result.kind,
            "action": result.action,
            "name": name,
            "response": result.response,
        }
        results.append(row)

    journal.write_json(tx.path / "phase3-hosts.json", results)

    # Phase 4: Internal Squad.
    squads = _unwrap_list(
        client.get_internal_squads(),
        ("internalSquads", "internal_squads", "response", "data"),
    )
    squad_name = str(bundle.squad_plan.get("name") or f"{profile_name}-Mobile")
    existing_squad = next((x for x in squads if _name(x) == squad_name), None)
    squad_result = adapter.apply_squad(
        bundle,
        inbounds,
        existing=existing_squad,
    )
    results.append({
        "phase": 4,
        "kind": squad_result.kind,
        "action": squad_result.action,
        "name": squad_name,
        "response": squad_result.response,
    })
    journal.write_json(tx.path / "phase4-squad.json", results[-1])

    return {
        "profile_uuid": profile_uuid,
        "inbound_tags": sorted(inbounds),
        "results": results,
    }
