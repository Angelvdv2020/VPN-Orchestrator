from __future__ import annotations

from typing import Any

from ..remnawave.client import RemnawaveClient
from ..remnawave.shape import find_by_name
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
) -> dict[str, Any]:
    health = None
    health_error = None
    try:
        health = client.get_system_health()
    except Exception as exc:
        health_error = str(exc)

    profiles = client.get_config_profiles()
    hosts = client.get_hosts()
    squads = client.get_internal_squads()
    nodes = client.get_nodes()

    # Presence checks are intentionally generic because response wrapping
    # changed between Remnawave releases.
    serialized = repr({
        "profiles": profiles,
        "hosts": hosts,
        "squads": squads,
    })

    missing_tags = [tag for tag in expected_inbound_tags if tag not in serialized]

    ok = health_error is None and not missing_tags
    return {
        "ok": ok,
        "system_health": health,
        "health_error": health_error,
        "missing_inbound_tags": missing_tags,
        "nodes_present": bool(nodes),
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
    except Exception as exc:
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
            mismatches.append({
                "kind": kind,
                "name": name,
                "reason": "created object still exists",
            })
        elif action == "update":
            if before is None or current is None:
                mismatches.append({
                    "kind": kind,
                    "name": name,
                    "reason": "snapshot or restored object is missing",
                })
            elif sanitize_update_object(current) != sanitize_update_object(before):
                mismatches.append({
                    "kind": kind,
                    "name": name,
                    "reason": "restored object differs from snapshot",
                })

    return {
        "ok": health_error is None and not mismatches,
        "system_health": health,
        "health_error": health_error,
        "mismatches": mismatches,
    }
