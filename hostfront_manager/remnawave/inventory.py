from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from .client import RemnawaveClient


def _count(payload: Any, likely_keys: tuple[str, ...]) -> int | None:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return None

    for key in ("total", "count"):
        if isinstance(payload.get(key), int):
            return payload[key]

    for key in likely_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            nested = _count(value, likely_keys)
            if nested is not None:
                return nested
    return None


@dataclass(slots=True)
class InventorySummary:
    nodes: int | None
    hosts: int | None
    users: int | None
    config_profiles: int | None
    internal_squads: int | None

    def to_dict(self):
        return asdict(self)


def fetch_inventory(client: RemnawaveClient) -> tuple[InventorySummary, dict[str, Any]]:
    getters = {
        "nodes": client.get_nodes,
        "hosts": client.get_hosts,
        "users": client.get_users,
        "config_profiles": client.get_config_profiles,
        "internal_squads": client.get_internal_squads,
    }
    raw: dict[str, Any] = {}
    with ThreadPoolExecutor(
        max_workers=len(getters), thread_name_prefix="inventory"
    ) as pool:
        futures = {name: pool.submit(getter) for name, getter in getters.items()}
        for name, future in futures.items():
            raw[name] = future.result()

    summary = InventorySummary(
        nodes=_count(raw["nodes"], ("nodes", "response")),
        hosts=_count(raw["hosts"], ("hosts", "response")),
        users=_count(raw["users"], ("users", "response")),
        config_profiles=_count(
            raw["config_profiles"], ("configProfiles", "config_profiles", "response")
        ),
        internal_squads=_count(
            raw["internal_squads"], ("internalSquads", "internal_squads", "response")
        ),
    )
    return summary, raw
