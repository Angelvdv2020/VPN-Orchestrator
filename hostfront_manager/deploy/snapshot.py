from __future__ import annotations

from typing import Any

from ..errors import ManagerError
from ..remnawave.client import RemnawaveClient
from .journal import Transaction, TransactionJournal


class SnapshotError(ManagerError):
    """Raised when a deploy snapshot is incomplete and rollback is unsafe."""


def capture_panel_snapshot(
    client: RemnawaveClient,
    journal: TransactionJournal,
    tx: Transaction,
    *,
    force_without_rollback: bool = False,
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
        except Exception as exc:  # noqa: BLE001 - preserve partial snapshot diagnostics
            snapshot[name] = {"snapshot_error": str(exc)}

    journal.write_json(tx.path / "before.json", snapshot)
    failed = {
        name: value.get("snapshot_error")
        for name, value in snapshot.items()
        if isinstance(value, dict) and value.get("snapshot_error")
    }
    if failed and not force_without_rollback:
        journal.update_status(tx, "blocked", {"snapshot_errors": failed})
        raise SnapshotError(
            "Snapshot панели неполный; deploy заблокирован без гарантированного "
            "rollback. Для осознанного обхода используй --force-without-rollback: "
            + ", ".join(failed)
        )
    return snapshot
