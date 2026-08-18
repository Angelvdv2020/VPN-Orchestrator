import pytest

from hostfront_manager.errors import LockError
from hostfront_manager.lock import ProcessLock


def test_lock_rejects_symlink(tmp_path):
    target = tmp_path / "target"
    target.write_text("do-not-touch")
    lock = tmp_path / "lock"
    lock.symlink_to(target)
    with pytest.raises(LockError), ProcessLock(lock):
        pass
    assert target.read_text() == "do-not-touch"


def test_lock_is_private_and_exclusive(tmp_path):
    path = tmp_path / "lock"
    with ProcessLock(path):
        assert path.stat().st_mode & 0o777 == 0o600
        with pytest.raises(LockError), ProcessLock(path):
            pass
