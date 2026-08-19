from __future__ import annotations

from typing import Any

from ..remnawave.client import RemnawaveClient
from ..remnawave.shape import find_by_name, unwrap_list
from ..rollback.sanitize import sanitize_update_object

ROLLBACK_KINDS = {
    "config-profile": (
        "config_profiles",
        ("configProfiles", "config_profiles", "response", "data"),
        "get_config_profiles",
    ),
    "host": (
        "hosts",
        ("hosts", "response", "data"),
        "get_hosts",
    ),
    "internal-squad": (
        "internal_squads",
        ("internalSquads", "internal_squads", "response", "data"),
        "get_internal_squads",
    ),
}


def verify_panel_after_apply(
    client: RemnawaveClient,
    expected_inbound_tags: list[str],
    *,
    expected_role_nodes: dict[str, str] | None = None,
    role_inbound_tags: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    health = None
    health_error = None
    try:
        health = client.get_system_health()
    except Exception as exc:  # noqa: BLE001
        health_error = str(exc)

    profiles = client.get_config_profiles()
    hosts = client.get_hosts()
    squads = client.get_internal_squads()
    nodes = client.get_nodes()

    expected = set(expected_inbound_tags)
    profile_rows = unwrap_list(
        profiles, ("configProfiles", "config_profiles", "response", "data")
    )

    def inbound_rows(obj: dict[str, Any]) -> list[dict[str, Any]]:
        rows = obj.get("inbounds")
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]
        config = obj.get("config")
        if isinstance(config, dict) and isinstance(config.get("inbounds"), list):
            return [x for x in config["inbounds"] if isinstance(x, dict)]
        return []

    selected = None
    tag_to_uuid: dict[str, str] = {}
    for profile in profile_rows:
        rows = inbound_rows(profile)
        tags = {str(x.get("tag")) for x in rows if x.get("tag")}
        if expected.issubset(tags):
            selected = profile
            tag_to_uuid = {
                str(x["tag"]): str(x["uuid"])
                for x in rows
                if x.get("tag") in expected and x.get("uuid")
            }
            break

    missing_tags = sorted(expected - set(tag_to_uuid))
    expected_uuids = set(tag_to_uuid.values())

    host_rows = unwrap_list(hosts, ("hosts", "response", "data"))
    bound_uuids = {
        str(row.get("inbound", {}).get("configProfileInboundUuid"))
        for row in host_rows
        if isinstance(row.get("inbound"), dict)
        and row["inbound"].get("configProfileInboundUuid")
    }
    missing_host_bindings = sorted(
        tag for tag, uuid in tag_to_uuid.items() if uuid not in bound_uuids
    )

    squad_rows = unwrap_list(
        squads, ("internalSquads", "internal_squads", "response", "data")
    )
    squad_complete = any(
        expected_uuids.issubset(
            {str(x.get("uuid")) for x in row.get("inbounds", []) if isinstance(x, dict)}
        )
        for row in squad_rows
        if isinstance(row.get("inbounds"), list)
    )

    node_rows = unwrap_list(nodes, ("nodes", "response", "data"))
    connected = [
        row
        for row in node_rows
        if row.get("isConnected") is True and row.get("isDisabled") is not True
    ]
    covered: set[str] = set()
    for node in connected:
        profile = node.get("configProfile")
        if not isinstance(profile, dict):
            continue
        for inbound in profile.get("activeInbounds", []):
            if isinstance(inbound, dict):
                if inbound.get("uuid"):
                    covered.add(str(inbound["uuid"]))
            elif isinstance(inbound, str):
                covered.add(inbound)
    missing_node_coverage = sorted(
        tag for tag, uuid in tag_to_uuid.items() if uuid not in covered
    )

    role_results: dict[str, Any] = {}
    role_ok = True
    for role, node_uuid in (expected_role_nodes or {}).items():
        wanted_tags = set((role_inbound_tags or {}).get(role, []))
        node = next(
            (row for row in node_rows if str(row.get("uuid")) == str(node_uuid)),
            None,
        )
        active = set()
        if isinstance(node, dict):
            profile = node.get("configProfile")
            if isinstance(profile, dict):
                active = {
                    str(x.get("uuid")) if isinstance(x, dict) else str(x)
                    for x in profile.get("activeInbounds", [])
                }
        expected_uuids_for_role = {
            tag_to_uuid[tag] for tag in wanted_tags if tag in tag_to_uuid
        }
        unexpected = active - expected_uuids_for_role
        missing = expected_uuids_for_role - active
        role_results[role] = {
            "node_uuid": node_uuid,
            "missing_tags": sorted(
                tag for tag in wanted_tags if tag_to_uuid.get(tag) in missing
            ),
            "unexpected_inbound_uuids": sorted(unexpected),
            "node_found": node is not None,
        }
        role_ok = role_ok and node is not None and not missing and not unexpected

    # A profile/host/squad deployment may intentionally omit node role UUIDs;
    # role assignment is a separate explicit operation. Do not report a false
    # post-check failure merely because that optional phase was not requested.
    node_coverage_ok = True if not expected_role_nodes else not missing_node_coverage

    ok = (
        health_error is None
        and selected is not None
        and not missing_tags
        and not missing_host_bindings
        and squad_complete
        and bool(connected)
        and node_coverage_ok
        and role_ok
    )
    return {
        "ok": ok,
        "system_health": health,
        "health_error": health_error,
        "missing_inbound_tags": missing_tags,
        "profile_found": selected is not None,
        "missing_host_bindings": missing_host_bindings,
        "squad_complete": squad_complete,
        "connected_nodes": len(connected),
        "missing_node_coverage": missing_node_coverage,
        "role_checks": role_results,
        "nodes_present": bool(node_rows),
    }


def verify_rollback_after_apply(
    client: RemnawaveClient,
    before_snapshot: dict[str, Any],
    applied: dict[str, Any],
) -> dict[str, Any]:
    """Verify API health and that every reversible mutation matches its snapshot."""
    health = None
    health_error = None
    try:
        health = client.get_system_health()
    except Exception as exc:  # noqa: BLE001
        health_error = str(exc)

    live: dict[str, Any] = {}
    mismatches: list[dict[str, str]] = []
    for row in applied.get("results", []):
        kind = str(row.get("kind") or "")
        action = str(row.get("action") or "")
        name = str(row.get("name") or "")
        if kind not in ROLLBACK_KINDS or action not in {"create", "update"}:
            continue

        snapshot_key, keys, getter_name = ROLLBACK_KINDS[kind]
        if kind not in live:
            live[kind] = getattr(client, getter_name)()
        current = find_by_name(live[kind], name, keys)
        before = find_by_name(before_snapshot.get(snapshot_key), name, keys)

        if action == "create" and current is not None:
            mismatches.append(
                {
                    "kind": kind,
                    "name": name,
                    "reason": "created object still exists",
                }
            )
        elif action == "update":
            if before is None or current is None:
                mismatches.append(
                    {
                        "kind": kind,
                        "name": name,
                        "reason": "snapshot or restored object is missing",
                    }
                )
            elif sanitize_update_object(current) != sanitize_update_object(before):
                mismatches.append(
                    {
                        "kind": kind,
                        "name": name,
                        "reason": "restored object differs from snapshot",
                    }
                )

    return {
        "ok": health_error is None and not mismatches,
        "system_health": health,
        "health_error": health_error,
        "mismatches": mismatches,
    }
