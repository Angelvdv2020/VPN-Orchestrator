from __future__ import annotations

import getpass
import os
import re
import socket
from pathlib import Path

from .config import AppConfig
from .errors import ManagerError
from .install.wizard import InstallPlan, install_all
from .mobile.defaults import default_paths
from .mobile.store import MobileStateStore
from .nodes.compose import build_node_compose
from .nodes.models import NodeRuntimeSpec, RemoteTarget
from .nodes.remote import deploy_compose, remote_prepare, ssh_test
from .profiles.builder import build_mobile_profile
from .profiles.bundle import write_bundle
from .profiles.models import MobileProfileSettings, RealitySettings
from .shell import ShellRunner

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
BLUE = "\033[34m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"


def _banner() -> None:
    # Очистка терминала без запуска shell: баннер всегда начинается со строки 1.
    print("\033[2J\033[H", end="")
    print(f"{CYAN}{BOLD}")
    print(
        "  ██╗  ██╗ ██████╗ ███████╗████████╗███████╗██████╗  ██████╗ ███╗   ██╗████████╗"
    )
    print(
        "  ██║  ██║██╔═══██╗██╔════╝╚══██╔══╝██╔════╝██╔══██╗██╔═══██╗████╗  ██║╚══██╔══╝"
    )
    print(
        "  ███████║██║   ██║███████╗   ██║   █████╗  ██████╔╝██║   ██║██╔██╗ ██║   ██║   "
    )
    print(
        "  ██╔══██║██║   ██║╚════██║   ██║   ██╔══╝  ██╔══██╗██║   ██║██║╚██╗██║   ██║   "
    )
    print(
        "  ██║  ██║╚██████╔╝███████║   ██║   ███████╗██║  ██║╚██████╔╝██║ ╚████║   ██║   "
    )
    print(
        "  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   "
    )
    print(f"{RESET}")
    print(f"{BLUE}{BOLD}                 МАСТЕР ПЕРВОГО ЗАПУСКА · RC3{RESET}")
    print(
        f"{DIM}  Чистая установка · ваши домены · ваши названия · ваши секреты{RESET}"
    )


def _section(number: int, title: str) -> None:
    print(f"\n{BLUE}{BOLD}━━ {number}. {title} ━━{RESET}")


def _ask(prompt: str, *, default: str = "", secret: bool = False) -> str:
    suffix = f" {DIM}[по умолчанию: {default}]{RESET}" if default else ""
    print(f"\n{YELLOW}{prompt}{RESET}{suffix}")
    value = (getpass.getpass if secret else input)(f"{CYAN}  › {RESET}").strip()
    return value or default


def _save_secret(path: Path, name: str, value: str) -> None:
    if not value or any(x in value for x in "\r\n"):
        raise ManagerError(f"Пустой или небезопасный секрет: {name}")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    result = [line for line in lines if not line.startswith(name + "=")]
    result.append(f"{name}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    from .install.common import atomic_write

    atomic_write(path, "\n".join(result) + "\n", 0o600)


def _deploy_local_node(cfg: AppConfig, runner: ShellRunner, compose: str) -> None:
    node_dir = cfg.install.node_dir
    node_dir.mkdir(parents=True, exist_ok=True)
    compose_path = node_dir / "docker-compose.yml"
    from .install.common import atomic_write

    atomic_write(compose_path, compose, 0o600)
    runner.run(["docker", "compose", "-f", str(compose_path), "up", "-d"])


def run_first_run(cfg: AppConfig, runner: ShellRunner) -> dict:
    """Interactive setup that gathers user data once and runs supported steps."""
    _banner()
    print(f"{GREEN}Мастер сам подготовит Manager, ноды, профиль и подписку.{RESET}")
    print(f"{DIM}Нажмите Enter, чтобы принять значение по умолчанию.{RESET}")
    _section(1, "Домены и название")
    panel = _ask("Домен панели", default="panel.example.com")
    subscription = _ask("Домен подписки", default="sub.example.com")
    profile_name = _ask("Название профиля и подписки", default="Мой мобильный профиль")
    edge_domain = _ask("Домен edge-ноды", default="edge.example.com")
    front_domain = _ask("Домен front-ноды", default="front.example.com")
    xhttp_port = int(_ask("Порт REALITY XHTTP", default="8443"))
    raw_port = int(_ask("Порт REALITY RAW", default="8444"))
    hysteria_port = int(_ask("Порт Hysteria2 UDP", default="8445"))
    front_port = int(_ask("Публичный порт front", default="443"))
    _section(2, "Доступ к нодам")
    edge_host = _ask("IP/hostname edge-сервера", default="203.0.113.11")
    front_host = _ask("IP/hostname front-сервера", default="203.0.113.12")
    edge_node_secret = _ask("Node Secret edge", secret=True)
    front_node_secret = _ask("Node Secret front", secret=True)

    local_ips = {"127.0.0.1", socket.gethostbyname(socket.gethostname())}
    same_machine = edge_host in local_ips and front_host in local_ips
    endpoints = (
        ("edge", edge_host, edge_node_secret),
        ("front", front_host, front_node_secret),
    )
    if same_machine:
        print(
            f"{YELLOW}Edge и front находятся на этом же сервере; SSH не нужен, "
            "нода будет запущена локально.{RESET}"
        )
        local_compose = build_node_compose(
            NodeRuntimeSpec(
                node_port=cfg.nodes.default_node_port,
                secret_key=edge_node_secret,
                enable_net_admin=cfg.nodes.enable_net_admin,
            )
        )
        _deploy_local_node(cfg, runner, local_compose)
        endpoints = ()
    else:
        ssh_user = _ask("SSH user для нод", default="root")
        ssh_port = int(_ask("SSH port для нод", default="22"))
        identity = _ask("Путь к SSH private key", default="/root/.ssh/hostfront-edge")
    if not same_machine and edge_host == front_host:
        print(
            f"{YELLOW}Одна машина указана для edge и front; SSH-развёртывание "
            "ноды выполняется один раз после настройки портов.{RESET}"
        )
        endpoints = (endpoints[0],)
    for role, host, secret in endpoints:
        target = RemoteTarget(host, ssh_user, ssh_port, identity)
        ssh_test(runner, target)
        remote_prepare(runner, target)
        compose = build_node_compose(
            NodeRuntimeSpec(
                node_port=cfg.nodes.default_node_port,
                secret_key=secret,
                enable_net_admin=cfg.nodes.enable_net_admin,
            )
        )
        deploy_compose(runner, target, compose, start=True)
        print(f"Нода {role} подготовлена: {host}")

    _section(3, "Ключи транспортов")
    print(f"{DIM}Секретные поля вводятся вслепую и не попадают в журнал.{RESET}")
    reality_target = _ask("REALITY target host:port", default="target.example:443")
    reality_sni = _ask("REALITY SNI", default="target.example")
    reality_private_key = _ask("REALITY private key", secret=True)
    short_id = _ask("REALITY short ID")
    hysteria_auth = _ask("Hysteria2 auth", secret=True)

    plan = InstallPlan(panel, subscription, True)
    installation = install_all(cfg, runner, plan)

    _section(4, "Remnawave")
    token = _ask("Remnawave API token", secret=True)
    _save_secret(cfg.manager.secrets_file, cfg.remnawave.token_env, token)
    os.environ[cfg.remnawave.token_env] = token
    installation = install_all(cfg, runner, plan)

    _section(5, "Сборка профиля")
    settings = MobileProfileSettings(
        name=profile_name,
        edge_domain=edge_domain,
        front_domain=front_domain,
        reality=RealitySettings(
            target=reality_target,
            server_name=reality_sni,
            private_key=reality_private_key,
            short_id=short_id,
        ),
        reality_xhttp_port=xhttp_port,
        reality_raw_port=raw_port,
        hysteria_port=hysteria_port,
        host_front_external_port=front_port,
        hysteria_auth=hysteria_auth,
    )
    profile = build_mobile_profile(settings)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", profile_name).strip(".-") or "mobile"
    output_dir = cfg.manager.data_dir / "bundles" / safe_name
    files = write_bundle(profile, output_dir)
    MobileStateStore(cfg.mobile.state_file).set_paths(
        default_paths(edge_domain, front_domain)
    )
    result = {
        "installation": installation,
        "profile_name": profile_name,
        "bundle_dir": str(output_dir),
        "files": [str(x) for x in files],
        "next": "Проверьте bundle и выполните deploy-mobile-plan перед apply.",
    }
    print(f"\n{GREEN}{BOLD}✓ ГОТОВО{RESET}")
    print(f"{GREEN}Профиль: {profile_name}{RESET}")
    print(f"{GREEN}Bundle:  {output_dir}{RESET}")
    print(f"{DIM}{result['next']}{RESET}")
    return result
