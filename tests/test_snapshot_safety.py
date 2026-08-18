import pytest

from hostfront_manager.deploy.journal import TransactionJournal
from hostfront_manager.deploy.snapshot import SnapshotError, capture_panel_snapshot


class PartialClient:
    def get_system_configuration(self):
        return {"ok": True}

    def get_config_profiles(self):
        raise TimeoutError("profiles timeout")

    def get_hosts(self):
        return {"response": []}

    def get_internal_squads(self):
        return {"response": []}

    def get_nodes(self):
        return {"response": []}


def test_incomplete_snapshot_blocks_by_default(tmp_path):
    journal = TransactionJournal(tmp_path)
    tx = journal.begin("deploy")
    with pytest.raises(SnapshotError):
        capture_panel_snapshot(PartialClient(), journal, tx)
    assert journal.status(tx) == "blocked"


def test_force_snapshot_is_explicit(tmp_path):
    journal = TransactionJournal(tmp_path)
    tx = journal.begin("deploy")
    snapshot = capture_panel_snapshot(
        PartialClient(), journal, tx, force_without_rollback=True
    )
    assert "snapshot_error" in snapshot["config_profiles"]
