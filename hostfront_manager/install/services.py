from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ServiceFiles:
    watchdog: str
    web: str


def render_services(
    executable: str, config_path: Path, environment_file: Path
) -> ServiceFiles:
    common = f"""[Unit]
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
EnvironmentFile=-{environment_file}
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/hostfront-manager /var/log/hostfront-manager /var/backups/hostfront-manager /run/lock
Restart=on-failure
RestartSec=10s
"""
    watchdog = (
        "[Unit]\nDescription=HostFront Manager Watchdog\n"
        + common.split("[Unit]\n", 1)[1]
        + (
            f"ExecStart={executable} --config {config_path} watchdog-run\n\n[Install]\nWantedBy=multi-user.target\n"
        )
    )
    web_common = common.replace("User=root", "User=hostfront-manager")
    web = (
        "[Unit]\nDescription=HostFront Manager Web API\n"
        + web_common.split("[Unit]\n", 1)[1]
        + (
            f"ExecStart={executable} --config {config_path} web-serve\n\n[Install]\nWantedBy=multi-user.target\n"
        )
    )
    return ServiceFiles(watchdog=watchdog, web=web)


def write_services(files: ServiceFiles, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for name, content in (
        ("hostfront-manager-watchdog.service", files.watchdog),
        ("hostfront-manager-web.service", files.web),
    ):
        path = output_dir / name
        path.write_text(content, encoding="utf-8")
        created.append(path)
    return created
