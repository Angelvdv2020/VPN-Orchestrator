from __future__ import annotations

from ..errors import ManagerError
from ..shell import ShellRunner


def restart_services(runner: ShellRunner, services: list[str], allowed: list[str]) -> list[dict]:
    denied = sorted(set(services) - set(allowed))
    if denied:
        raise ManagerError("Repair запрещён для services: " + ", ".join(denied))
    results = []
    for service in services:
        cp = runner.run(["systemctl", "restart", service])
        results.append({"service": service, "returncode": cp.returncode})
    return results
