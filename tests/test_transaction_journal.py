import json

from hostfront_manager.deploy.journal import TransactionJournal


def test_failure_does_not_overwrite_rolled_back_status(tmp_path):
    journal = TransactionJournal(tmp_path)
    tx = journal.begin("deploy")
    journal.update_status(tx, "rolled_back", {"rollback_verification": {"ok": True}})

    assert not journal.update_failure(tx, RuntimeError("post-check failed"))

    manifest = json.loads((tx.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "rolled_back"
    assert manifest["rollback_verification"] == {"ok": True}
    assert "error" not in manifest


def test_failure_is_recorded_for_active_transaction(tmp_path):
    journal = TransactionJournal(tmp_path)
    tx = journal.begin("deploy")

    assert journal.update_failure(tx, RuntimeError("network error"))

    manifest = json.loads((tx.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["error"] == "network error"


def test_journal_uses_private_atomic_files(tmp_path):
    journal = TransactionJournal(tmp_path)
    tx = journal.begin("deploy")
    assert tmp_path.stat().st_mode & 0o777 == 0o700
    assert (tx.path / "manifest.json").stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".*manifest.json.*"))
