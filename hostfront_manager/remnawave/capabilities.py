from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Callable

from ..errors import ManagerError
from .client import RemnawaveClient


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk(value)


def _extract_version(*payloads: Any) -> str | None:
    candidates = (
        "version",
        "panelVersion",
        "panel_version",
        "backendVersion",
        "backend_version",
        "remnawaveVersion",
        "remnawave_version",
    )
    for payload in payloads:
        for obj in _walk(payload):
            for key in candidates:
                value = obj.get(key)
                if isinstance(value, str) and re.search(r"\d+\.\d+(?:\.\d+)?", value):
                    match = re.search(r"\d+\.\d+(?:\.\d+)?", value)
                    if match:
                        return match.group(0)
    return None


@dataclass(slots=True)
class Capabilities:
    api_version: str | None
    system_configuration: bool
    system_health: bool
    system_recap: bool
    config_profiles: bool
    profile_inbounds: bool
    hosts: bool
    internal_squads: bool
    nodes: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_capabilities(client: RemnawaveClient) -> tuple[Capabilities, dict[str, Any]]:
    raw: dict[str, Any] = {}
    notes: list[str] = []

    def safe(name: str, fn: Callable[[], Any]) -> bool:
        try:
            raw[name] = fn()
            return True
        except ManagerError as exc:
            raw[name] = {"error": str(exc)}
            notes.append(f"{name}: {exc}")
            return False

    metadata_ok = safe("system_metadata", client.get_system_metadata)
    config_ok = safe("system_configuration", client.get_system_configuration)
    health_ok = safe("system_health", client.get_system_health)
    recap_ok = safe("system_recap", client.get_system_stats_recap)
    profiles_ok = safe("config_profiles", client.get_config_profiles)
    hosts_ok = safe("hosts", client.get_hosts)
    squads_ok = safe("internal_squads", client.get_internal_squads)
    nodes_ok = safe("nodes", client.get_nodes)

    profile_inbounds_ok = False
    if profiles_ok:
        # We do not require a profile to exist. Endpoint availability is inferred
        # from current API family + successful Config Profiles controller.
        profile_inbounds_ok = True

    version = _extract_version(
        raw.get("system_metadata"),
        raw.get("system_configuration"),
        raw.get("system_recap"),
        raw.get("system_health"),
    )

    caps = Capabilities(
        api_version=version,
        system_configuration=config_ok,
        system_health=health_ok,
        system_recap=recap_ok,
        config_profiles=profiles_ok,
        profile_inbounds=profile_inbounds_ok,
        hosts=hosts_ok,
        internal_squads=squads_ok,
        nodes=nodes_ok,
        notes=notes,
    )
    return caps, raw
