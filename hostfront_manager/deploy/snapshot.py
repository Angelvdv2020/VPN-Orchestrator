from __future__ import annotations

from typing import Any

from ..remnawave.client import RemnawaveClient
from .journal import Transaction, TransactionJournal


def capture_panel_snapshot(
    client: RemnawaveClient,
    journal: TransactionJournal,
    tx: Transaction,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}

    getters = {
        "system_configuration": client.get_system_configuration,
        "config_profiles": client.get_config_profiles,
        "hosts": client.get_hosts,
        "internal_squads": client.get_internal_squads,
        "nodes": client.get_nodes,
    }

    for name, fn in getters.items():
        try:
            snapshot[name] = fn()
        except Exception as exc:
            snapshot[name] = {"snapshot_error": str(exc)}

    journal.write_json(tx.path / "before.json", snapshot)
    return snapshot
