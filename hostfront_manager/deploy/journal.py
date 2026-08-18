from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Transaction:
    id: str
    path: Path


class TransactionJournal:
    def __init__(self, root: Path):
        self.root = root

    def _write_root(self) -> Path:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".probe"
            probe.write_text("1", encoding="utf-8")
            probe.unlink()
            return self.root
        except PermissionError:
            fallback = Path("./transactions")
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def begin(self, operation: str, metadata: dict[str, Any] | None = None) -> Transaction:
        root = self._write_root()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        tx_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
        path = root / tx_id
        path.mkdir(parents=True, exist_ok=False)

        manifest = {
            "id": tx_id,
            "operation": operation,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "started",
            "metadata": metadata or {},
        }
        self.write_json(path / "manifest.json", manifest)
        return Transaction(tx_id, path)

    @staticmethod
    def write_json(path: Path, data: Any, mode: int = 0o600) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(path, mode)
        except OSError:
            pass

    def update_status(self, tx: Transaction, status: str, extra: dict[str, Any] | None = None) -> None:
        manifest_path = tx.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = status
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        if extra:
            manifest.update(extra)
        self.write_json(manifest_path, manifest)

    def list_transactions(self) -> list[Path]:
        root = self._write_root()
        return sorted(
            [p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").exists()],
            reverse=True,
        )
