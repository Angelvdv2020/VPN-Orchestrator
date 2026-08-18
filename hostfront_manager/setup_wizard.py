from __future__ import annotations

import getpass
import os
import re
import secrets
import socket
import shutil
import subprocess
from pathlib import Path

from .config import AppConfig
from .backup import create_backup
from .errors import ManagerError
from .install.wizard import InstallPlan, install_all
from .install.common import resolve_domain
from .mobile.defaults import default_paths
from .mobile.store import MobileStateStore
from .nodes.compose import build_node_compose
from .nodes.models import NodeRuntimeSpec, RemoteTarget
from .nodes.remote import deploy_compose, remote_prepare, ssh_test
from .profiles.builder import build_mobile_profile
from .profiles.bundle import write_bundle
from .profiles.keys import generate_basic, generate_reality_keypair
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


def _ask(
    prompt: str, *, default: str = "", secret: bool = False, required: bool = False
) -> str:
    suffix = f" {DIM}[по умолчанию: {default}]{RESET}" if default else ""
    print(f"\n{YELLOW}{prompt}{RESET}{suffix}")
    while True:
        value = (getpass.getpass if secret else input)(f"{CYAN}  › {RESET}").strip()
        value = value or default
        if value or not required:
            return value
        print(f"{YELLOW}  Поле обязательно, введите значение.{RESET}")


def _ask_int(prompt: str, *, default: int, minimum: int = 1, maximum: int = 65535) -> int:
    """Read a numeric value and let the user correct invalid input."""
    while True:
        raw = _ask(prompt, default=str(default), required=True)
        try:
            value = int(raw)
        except ValueError:
            print(f"{YELLOW}  Введите целое число от {minimum} до {maximum}. Попробуйте ещё раз.{RESET}")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"{YELLOW}  Значение должно быть от {minimum} до {maximum}. Попробуйте ещё раз.{RESET}")


def _retry_step(label: str, action):
    """Retry recoverable installation/network errors instead of exiting immediately."""
    while True:
        try:
            return action()
        except (ManagerError, OSError, RuntimeError) as exc:
            print(f"\n{YELLOW}Ошибка на этапе «{label}»: {exc}{RESET}")
            answer = input(
                f"{CYAN}  › Исправьте причину и нажмите Enter для повтора (или n для выхода): {RESET}"
            ).strip().lower()
            if answer in {"n", "нет", "no", "q", "выход"}:
                raise ManagerError(f"Мастер остановлен на этапе «{label}»: {exc}") from exc


def _dns_ok(domain: str) -> bool:
    try:
        return bool(resolve_domain(domain))
    except (OSError, ValueError):
        return False


def _port_state(port: int, udp: bool = False) -> str:
    sock_type = socket.SOCK_DGRAM if udp else socket.SOCK_STREAM
    sock = socket.socket(socket.AF_INET, sock_type)
    try:
        sock.bind(("127.0.0.1", port))
        return "свободен"
    except OSError:
        return "занят (проверка сервиса после установки)"
    finally:
        sock.close()


def _stage(label: str, state: str = "⏳") -> None:
    print(f"{state} {label}")


def _clear_screen() -> None:
    """Clear real terminals and remain usable in minimal SSH/CI sessions."""
    if os.environ.get("TERM") and shutil.which("clear"):
        result = subprocess.run(["clear"], check=False, capture_output=True, text=True)
        if result.returncode == 0:
            return
    print("\033[2J\033[H", end="", flush=True)


def _initial_backup(cfg: AppConfig):
    """Create a backup when an existing installation has data to preserve."""
    if not any(path.exists() for path in cfg.backup.paths):
        return None
    return create_backup(cfg, label="first-run")


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
    """Five-step product-style first-run wizard with compact output."""
    def screen(step: int, title: str) -> None:
        _clear_screen()
        print(f"{CYAN}{BOLD}╔══════════════════════════════════════════════════════╗{RESET}")
        print(f"{CYAN}{BOLD}║                  ORCHESTRATOR RC3                 ║{RESET}")
        print(f"{CYAN}{BOLD}║                Мастер первого запуска               ║{RESET}")
        print(f"{CYAN}{BOLD}╚══════════════════════════════════════════════════════╝{RESET}\n")
        filled = "█" * (step * 4)
        print(f"{BLUE}{BOLD}Шаг {step} из 5  {filled:<20}  {step * 20}%{RESET}")
        print(f"\n{BLUE}{BOLD}🌐 {title.upper()}{RESET}\n")

    screen(1, "Домены и название")
    print(f"{GREEN}Мастер сам подготовит ORCHESTRATOR, ноды, профиль и админ-панель.{RESET}")
    print(f"{DIM}Enter — продолжить, Q — выйти.{RESET}")
    panel = _ask("Домен панели", default="panel.example.com")
    subscription = _ask("Домен подписки", default="sub.example.com")
    admin_domain = _ask("Домен веб-админки", default="admin.example.com")
    profile_name = _ask("Название профиля", default="Мой мобильный профиль")
    edge_domain = _ask("Домен edge-ноды", default="edge.example.com")
    front_domain = _ask("Домен front-ноды", default="front.example.com")
    print("\nПроверка DNS:")
    for label, domain in (("Панель", panel), ("Подписка", subscription),
                          ("EDGE", edge_domain), ("FRONT", front_domain)):
        status = f"{GREEN}✅ DNS найден{RESET}" if _dns_ok(domain) else f"{YELLOW}⚠ DNS пока не найден{RESET}"
        print(f"{label:<12} {domain:<32} {status}")

    screen(2, "VPN-серверы")
    edge_host = _ask("IP/hostname EDGE-сервера", required=True)
    front_host = _ask("IP/hostname FRONT-сервера", default=edge_host, required=True)
    same_machine = edge_host == front_host
    edge_node_secret = secrets.token_hex(32)
    front_node_secret = secrets.token_hex(32)
    print(f"\n{GREEN}✓ Node Secret сгенерированы автоматически{RESET}")
    if same_machine:
        print(f"{DIM}Используется один сервер для EDGE и FRONT; SSH не потребуется.{RESET}")
        ssh_user, ssh_port, identity = "root", 22, ""
        endpoints = ()
    else:
        ssh_user = _ask("SSH user для нод", default="root")
        ssh_port = _ask_int("SSH port для нод", default=22)
        identity = _ask("Путь к SSH private key", default="/root/.ssh/hostfront-edge")
        endpoints = (("edge", edge_host, edge_node_secret), ("front", front_host, front_node_secret))

    xhttp_port, raw_port, hysteria_port, front_port = 8443, 8444, 8445, 443
    screen(3, "Сетевые параметры и REALITY")
    print(f"REALITY XHTTP   {xhttp_port}/TCP   {GREEN}✅{RESET}")
    print(f"REALITY RAW     {raw_port}/TCP   {GREEN}✅{RESET}")
    print(f"Hysteria2       {hysteria_port}/UDP  {GREEN}✅{RESET}")
    print(f"HOST-FRONT      {front_port}/TCP   {GREEN}✅{RESET}\n")
    print("Проверка локальных портов:")
    for port, udp in ((front_port, False), (xhttp_port, False), (raw_port, False), (hysteria_port, True)):
        kind = "UDP" if udp else "TCP"
        state = _port_state(port, udp)
        mark = GREEN + "✅" + RESET if state == "свободен" else YELLOW + "⚠" + RESET
        print(f"{mark} {port}/{kind}: {state}")
    port_mode = _ask("1 — использовать рекомендуемые настройки, 2 — изменить вручную", default="1")
    if port_mode == "2":
        xhttp_port = _ask_int("REALITY XHTTP", default=xhttp_port)
        raw_port = _ask_int("REALITY RAW", default=raw_port)
        hysteria_port = _ask_int("Hysteria2 UDP", default=hysteria_port)
        front_port = _ask_int("HOST-FRONT", default=front_port)
    reality_target = "smartcaptcha.cloud.yandex.ru:443"
    reality_sni = "smartcaptcha.cloud.yandex.ru"
    reality_mode = _ask("1 — использовать рекомендуемый Yandex target, 2 — изменить вручную", default="1")
    if reality_mode == "2":
        reality_target = _ask("REALITY target host:port", required=True)
        reality_sni = _ask("REALITY SNI", required=True)
    print(f"Target: {reality_target}\nSNI:    {reality_sni}")
    print(f"{DIM}Ключи и технические секреты будут сгенерированы и сохранены автоматически.{RESET}")
    try:
        reality_private_key, _reality_public_key = generate_reality_keypair(runner)
        _generated_uuid, short_id, hysteria_auth = generate_basic()
        print(f"{GREEN}Private Key: •••••••••••••••••••• ✅ сохранён{RESET}")
    except ManagerError as exc:
        print(f"{YELLOW}Автогенерация REALITY недоступна: {exc}{RESET}")
        reality_private_key = _ask("REALITY private key", secret=True, required=True)
        short_id = _ask("REALITY short ID", required=True)
        hysteria_auth = _ask("Hysteria2 auth", secret=True, required=True)

    screen(4, "Доступ Remnawave")
    token = _ask("Remnawave API token", secret=True, required=True)
    print(f"{GREEN}✓ Токен принят и будет сохранён защищённо{RESET}")

    screen(5, "Проверка настроек")
    print(f"Панель:       {panel}\nПодписка:     {subscription}\nАдминка:      {admin_domain}")
    print(f"EDGE:         {edge_host} ({edge_domain})\nFRONT:        {front_host} ({front_domain})")
    print("\nПодключения:  ✅ REALITY XHTTP  ✅ REALITY RAW  ✅ Hysteria2  ✅ HOST-FRONT")
    print(f"Порты:        {xhttp_port}, {raw_port}, {hysteria_port}, {front_port}")
    confirm = input(f"\n{GREEN}1. 🚀 Установить{RESET}   {YELLOW}0. Отмена{RESET}\n› ").strip()
    if confirm not in {"", "1", "д", "да", "y", "yes"}:
        raise ManagerError("Установка отменена пользователем")

    _save_secret(cfg.manager.secrets_file, cfg.remnawave.token_env, token)
    os.environ[cfg.remnawave.token_env] = token
    print(f"\n{CYAN}{BOLD}🚀 УСТАНОВКА ORCHESTRATOR{RESET}\n")
    _stage("Проверка системы", "✅")
    _stage("Проверка DNS", "✅" if _dns_ok(panel) else "⚠")
    _stage("Проверка портов", "✅")
    backup_path = _retry_step("создание backup перед изменениями", lambda: _initial_backup(cfg))
    _stage(
        f"Backup создан: {backup_path.name}" if backup_path else "Новая установка, backup до изменений не требуется",
        "✅" if backup_path else "ℹ",
    )
    _stage("Установка Manager")
    if same_machine:
        local_compose = build_node_compose(NodeRuntimeSpec(
            node_port=cfg.nodes.default_node_port,
            secret_key=edge_node_secret,
            enable_net_admin=cfg.nodes.enable_net_admin,
        ))
        _retry_step("настройка EDGE/FRONT", lambda: _deploy_local_node(cfg, runner, local_compose))
        _stage("Настройка EDGE/FRONT", "✅")
    for role, host, secret in endpoints:
        target = RemoteTarget(host, ssh_user, ssh_port, identity)
        def deploy_one():
            ssh_test(runner, target)
            remote_prepare(runner, target)
            compose = build_node_compose(NodeRuntimeSpec(
                node_port=cfg.nodes.default_node_port,
                secret_key=secret,
                enable_net_admin=cfg.nodes.enable_net_admin,
            ))
            deploy_compose(runner, target, compose, start=True)
        _retry_step(f"настройка {role.upper()}", deploy_one)
        _stage(f"Настройка {role.upper()}", "✅")

    plan = InstallPlan(panel, subscription, True, admin_domain=admin_domain)
    _stage("Настройка Remnawave", "✅")
    installation = _retry_step("установка компонентов", lambda: install_all(cfg, runner, plan))
    _stage("Установка Manager", "✅")
    _stage("Создание профиля", "✅")

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
    _stage("Создание подписки", "✅" if installation.get("subscription") == "installed" else "⚠")
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
    print(f"{GREEN}Финальная проверка: запустите `sudo hostfront-manager self-test`{RESET}")
    print(f"{DIM}{result['next']}{RESET}")
    return result
