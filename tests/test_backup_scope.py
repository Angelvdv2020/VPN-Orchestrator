from pathlib import Path

import pytest

from hostfront_manager.backup import MANAGER_SYSTEMD_UNITS, _scoped_backup_paths
from hostfront_manager.errors import BackupError


def test_legacy_systemd_directory_is_replaced_with_manager_units():
    paths = _scoped_backup_paths(
        [Path("/etc/hostfront-manager"), Path("/etc/systemd/system")]
    )

    assert Path("/etc/systemd/system") not in paths
    assert paths == [Path("/etc/hostfront-manager"), *MANAGER_SYSTEMD_UNITS]


def test_filesystem_root_is_rejected():
    with pytest.raises(BackupError, match="Слишком широкий"):
        _scoped_backup_paths([Path("/")])
