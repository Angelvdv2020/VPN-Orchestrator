from __future__ import annotations

import os
import platform
import shutil
import socket
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(slots=True)
class HostState:
    hostname: str
    os_name: str
    kernel: str
    architecture: str
    is_root: bool
    systemd_present: bool
    docker_present: bool
    python: str

    def to_dict(self):
        return asdict(self)


def collect_host_state() -> HostState:
    return HostState(
        hostname=socket.gethostname(),
        os_name=platform.platform(),
        kernel=platform.release(),
        architecture=platform.machine(),
        is_root=(os.geteuid() == 0) if hasattr(os, "geteuid") else False,
        systemd_present=Path("/run/systemd/system").exists(),
        docker_present=shutil.which("docker") is not None,
        python=platform.python_version(),
    )
