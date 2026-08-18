from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TERMINAL_STATUSES = frozenset(
    {
        "cancelled",
        "blocked",
        "committed",
        "verification_failed",
        "rolled_back",
        "rollback_verification_failed",
        "rollback_failed",
    }
)


@dataclass(slots=True)
class Transaction:
    id: str
    path: Path


class TransactionJournal:
    def __init__(self, root: Path):
        self.root = root

    def _write_root(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        return self.root

    def begin(
        self, operation: str, metadata: dict[str, Any] | None = None
    ) -> Transaction:
        root = self._write_root()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        tx_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
        path = root / tx_id
        path.mkdir(parents=True, exist_ok=False)

        manifest = {
            "id": tx_id,
            "operation": operation,
            "started_at": datetime.now(UTC).isoformat(),
            "status": "started",
            "metadata": metadata or {},
        }
        self.write_json(path / "manifest.json", manifest)
        return Transaction(tx_id, path)

    @staticmethod
    def write_json(path: Path, data: Any, mode: int = 0o600) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
            os.chmod(path, mode)
            dir_fd = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def update_status(
        self, tx: Transaction, status: str, extra: dict[str, Any] | None = None
    ) -> None:
        manifest_path = tx.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = status
        manifest["updated_at"] = datetime.now(UTC).isoformat()
        if extra:
            manifest.update(extra)
        self.write_json(manifest_path, manifest)

    def update_failure(self, tx: Transaction, error: Exception | str) -> bool:
        """Record an unexpected failure without erasing a more precise terminal state."""
        manifest_path = tx.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") in TERMINAL_STATUSES:
            return False
        self.update_status(tx, "failed", {"error": str(error)})
        return True

    def status(self, tx: Transaction) -> str:
        manifest = json.loads((tx.path / "manifest.json").read_text(encoding="utf-8"))
        return str(manifest.get("status") or "")

    def list_transactions(self) -> list[Path]:
        root = self._write_root()
        return sorted(
            [
                p
                for p in root.iterdir()
                if p.is_dir() and (p / "manifest.json").exists()
            ],
            reverse=True,
        )
