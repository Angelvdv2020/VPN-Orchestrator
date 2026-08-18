from __future__ import annotations

import fcntl
import os
import stat
from pathlib import Path

from .errors import LockError


class ProcessLock:
    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def __enter__(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(
                self.path,
                os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                os.close(fd)
                raise LockError(f"Lock path не является обычным файлом: {self.path}")
            os.fchmod(fd, 0o600)
            self._fh = os.fdopen(fd, "r+", encoding="ascii")
        except (OSError, PermissionError) as exc:
            raise LockError(
                f"Не удалось безопасно создать lock {self.path}: {exc}"
            ) from exc

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
