from __future__ import annotations

from pathlib import Path

from ..errors import ManagerError
from ..shell import ShellRunner


def restart_services(
    runner: ShellRunner,
    services: list[str],
    allowed: list[str],
    *,
    panel_dir: Path = Path("/opt/remnawave"),
) -> list[dict]:
    denied = sorted(set(services) - set(allowed))
    if denied:
        raise ManagerError("Repair запрещён для services: " + ", ".join(denied))
    results = []
    for service in services:
        if service == "remnawave":
            compose = panel_dir / "docker-compose.yml"
            if not compose.exists() and not runner.dry_run:
                raise ManagerError(f"Remnawave compose не найден: {compose}")
            cp = runner.run(
                ["docker", "compose", "-f", str(compose), "restart", "remnawave"]
            )
        else:
            cp = runner.run(["systemctl", "restart", service])
        results.append({"service": service, "returncode": cp.returncode})
    return results
