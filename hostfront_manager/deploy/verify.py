from __future__ import annotations

from typing import Any

from ..remnawave.client import RemnawaveClient


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
