from __future__ import annotations

import ipaddress
import re
import shlex
from dataclasses import dataclass

from ..errors import RemoteDeployError
from ..shell import ShellRunner
from .models import RemoteTarget


_HOST_RX = re.compile(r"^[A-Za-z0-9.-]+$")
_USER_RX = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,31}$")


def validate_target(target: RemoteTarget) -> None:
    if not (1 <= target.ssh_port <= 65535):
        raise RemoteDeployError("Некорректный SSH-порт")
    if not _USER_RX.fullmatch(target.user):
        raise RemoteDeployError("Некорректный SSH user")

    try:
        ipaddress.ip_address(target.host)
    except ValueError:
        if not _HOST_RX.fullmatch(target.host) or "." not in target.host:
            raise RemoteDeployError("Некорректный SSH host")


def ssh_argv(target: RemoteTarget) -> list[str]:
    validate_target(target)
    argv = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-p", str(target.ssh_port),
    ]
    if target.identity_file:
        argv.extend(["-i", target.identity_file])
    argv.append(f"{target.user}@{target.host}")
    return argv


def ssh_test(runner: ShellRunner, target: RemoteTarget) -> None:
    argv = ssh_argv(target) + ["printf 'ssh-ok'"]
    result = runner.run(argv)
    if "ssh-ok" not in result.stdout:
        raise RemoteDeployError("SSH подключение установлено, но тест не прошёл")


def remote_prepare(runner: ShellRunner, target: RemoteTarget) -> None:
    command = (
        "set -eu; "
        "command -v docker >/dev/null 2>&1 || "
        "(curl -fsSL https://get.docker.com -o /tmp/get-docker.sh && sh /tmp/get-docker.sh); "
        "docker compose version >/dev/null; "
        "mkdir -p /opt/remnanode"
    )
    runner.run(ssh_argv(target) + [command])


def deploy_compose(
    runner: ShellRunner,
    target: RemoteTarget,
    compose_text: str,
    *,
    start: bool = True,
) -> None:
    # User-controlled values are not interpolated into the remote shell command.
    # Compose content goes through stdin.
    write_cmd = (
        "set -eu; "
        "mkdir -p /opt/remnanode; "
        "umask 077; "
        "cat > /opt/remnanode/docker-compose.yml.tmp; "
        "docker compose -f /opt/remnanode/docker-compose.yml.tmp config -q; "
        "mv /opt/remnanode/docker-compose.yml.tmp /opt/remnanode/docker-compose.yml"
    )
    runner.run(
        ssh_argv(target) + [write_cmd],
        input_text=compose_text,
        timeout=max(runner.timeout, 60),
    )

    if start:
        start_cmd = (
            "set -eu; "
            "cd /opt/remnanode; "
            "docker compose up -d; "
            "docker compose ps"
        )
        runner.run(ssh_argv(target) + [start_cmd], timeout=max(runner.timeout, 120))


def remote_node_logs(runner: ShellRunner, target: RemoteTarget, tail: int = 100) -> str:
    tail = max(1, min(int(tail), 1000))
    command = f"cd /opt/remnanode && docker compose logs --tail={tail} remnanode"
    return runner.run(ssh_argv(target) + [command], check=False).stdout


def remote_health(runner: ShellRunner, target: RemoteTarget) -> dict:
    command = (
        "set -eu; "
        "cd /opt/remnanode; "
        "printf 'container='; "
        "docker inspect -f '{{.State.Status}}' remnanode 2>/dev/null || printf 'missing'; "
        "printf '\\ncompose='; "
        "docker compose ps --status running --services 2>/dev/null | tr '\\n' ','"
    )
    result = runner.run(ssh_argv(target) + [command], check=False)
    return {
        "ok": result.returncode == 0 and "container=running" in result.stdout,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode,
    }
