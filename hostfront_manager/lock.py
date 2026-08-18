from __future__ import annotations

import fcntl
from pathlib import Path

from .errors import LockError


class ProcessLock:
    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def __enter__(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.path.open("w")
        except PermissionError:
            fallback = Path("/tmp/hostfront-manager.lock")
            self._fh = fallback.open("w")

        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LockError("HostFront Manager уже запущен в другом процессе") from exc

        self._fh.write(str(__import__("os").getpid()))
        self._fh.flush()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._fh:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()
