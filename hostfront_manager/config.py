from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError


@dataclass(slots=True)
class ManagerSection:
    data_dir: Path = Path("/var/lib/hostfront-manager")
    log_dir: Path = Path("/var/log/hostfront-manager")
    backup_dir: Path = Path("/var/backups/hostfront-manager")
    lock_file: Path = Path("/run/lock/hostfront-manager.lock")
    command_timeout_seconds: int = 30
    backup_keep: int = 10
    secrets_file: Path = Path("/etc/hostfront-manager/secrets.env")


@dataclass(slots=True)
class RemnawaveSection:
    enabled: bool = True
    base_url: str = ""
    token_env: str = "REMNAWAVE_TOKEN"

    def token(self) -> str | None:
        return os.getenv(self.token_env)


@dataclass(slots=True)
class DomainsSection:
    panel: str = ""
    subscription: str = ""


@dataclass(slots=True)
class ChecksSection:
    require_root: bool = True
    require_systemd: bool = True
    require_docker: bool = True
    minimum_free_disk_mb: int = 2048
    tcp_ports: list[int] = field(default_factory=lambda: [22, 80, 443])


@dataclass(slots=True)
class BackupSection:
    paths: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class InstallSection:
    panel_dir: Path = Path("/opt/remnawave")
    node_dir: Path = Path("/opt/remnanode")
    reverse_proxy: str = "caddy"
    subscription_bundled: bool = True


@dataclass(slots=True)
class MobileSection:
    enabled: bool = True
    state_file: Path = Path("/var/lib/hostfront-manager/mobile-state.json")
    probe_timeout_seconds: float = 3.0
    failure_penalty: int = 18
    stale_after_seconds: int = 900
    prefer_tcp_on_unknown_network: bool = True


@dataclass(slots=True)
class NodesSection:
    ssh_user: str = "root"
    ssh_port: int = 22
    identity_file: Path | None = None
    default_node_port: int = 2222
    enable_net_admin: bool = True


@dataclass(slots=True)
class DeploySection:
    transaction_dir: Path = Path("/var/lib/hostfront-manager/transactions")
    require_api_version_prefix: str = "3.2."
    allow_mutations: bool = False
    health_timeout_seconds: int = 20
    automatic_rollback: bool = False
    require_verified_rollback_shape: bool = True


@dataclass(slots=True)
class WatchdogSection:
    enabled: bool = False
    state_file: Path = Path("/var/lib/hostfront-manager/watchdog-state.json")
    interval_seconds: int = 60
    failure_threshold: int = 3
    recovery_threshold: int = 2
    cooldown_seconds: int = 300
    repair_window_seconds: int = 3600
    max_repairs_per_window: int = 3
    auto_repair: bool = False
    unattended_repair: bool = False
    allowed_services: list[str] = field(default_factory=lambda: ["docker", "remnawave"])


@dataclass(slots=True)
class WebSection:
    enabled: bool = False
    bind: str = "127.0.0.1"
    port: int = 8765
    admin_token_env: str = "HOSTFRONT_ADMIN_TOKEN"
    telemetry_db: Path = Path("/var/lib/hostfront-manager/telemetry.sqlite3")
    telemetry_key_prefix: str = "HOSTFRONT_TELEMETRY_KEY_"
    telemetry_max_clock_skew_seconds: int = 300
    telemetry_retention_days: int = 30
    trusted_proxy: bool = False

    def admin_token(self) -> str | None:
        return os.getenv(self.admin_token_env)


@dataclass(slots=True)
class AppConfig:
    manager: ManagerSection = field(default_factory=ManagerSection)
    remnawave: RemnawaveSection = field(default_factory=RemnawaveSection)
    domains: DomainsSection = field(default_factory=DomainsSection)
    checks: ChecksSection = field(default_factory=ChecksSection)
    backup: BackupSection = field(default_factory=BackupSection)
    install: InstallSection = field(default_factory=InstallSection)
    mobile: MobileSection = field(default_factory=MobileSection)
    nodes: NodesSection = field(default_factory=NodesSection)
    deploy: DeploySection = field(default_factory=DeploySection)
    watchdog: WatchdogSection = field(default_factory=WatchdogSection)
    web: WebSection = field(default_factory=WebSection)


def _path(value: str | Path) -> Path:
    return Path(value).expanduser()


def load_config(path: Path | None) -> AppConfig:
    cfg = AppConfig()
    if path is None:
        candidates = [
            Path("./config.toml"),
            Path("/etc/hostfront-manager/config.toml"),
        ]
        path = next((p for p in candidates if p.exists()), None)

    if path is None:
        return cfg

    if not path.exists():
        raise ConfigError(f"Файл конфигурации не найден: {path}")

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ConfigError(f"Не удалось прочитать TOML {path}: {exc}") from exc

    m = raw.get("manager", {})
    cfg.manager = ManagerSection(
        data_dir=_path(m.get("data_dir", cfg.manager.data_dir)),
        log_dir=_path(m.get("log_dir", cfg.manager.log_dir)),
        backup_dir=_path(m.get("backup_dir", cfg.manager.backup_dir)),
        lock_file=_path(m.get("lock_file", cfg.manager.lock_file)),
        command_timeout_seconds=int(m.get("command_timeout_seconds", 30)),
        backup_keep=int(m.get("backup_keep", 10)),
        secrets_file=_path(m.get("secrets_file", "/etc/hostfront-manager/secrets.env")),
    )

    r = raw.get("remnawave", {})
    cfg.remnawave = RemnawaveSection(
        enabled=bool(r.get("enabled", True)),
        base_url=str(r.get("base_url", "")),
        token_env=str(r.get("token_env", "REMNAWAVE_TOKEN")),
    )

    d = raw.get("domains", {})
    cfg.domains = DomainsSection(
        panel=str(d.get("panel", "")),
        subscription=str(d.get("subscription", "")),
    )

    c = raw.get("checks", {})
    ports = [int(x) for x in c.get("tcp_ports", [22, 80, 443])]
    if any(p < 1 or p > 65535 for p in ports):
        raise ConfigError("tcp_ports содержит недопустимый порт")
    cfg.checks = ChecksSection(
        require_root=bool(c.get("require_root", True)),
        require_systemd=bool(c.get("require_systemd", True)),
        require_docker=bool(c.get("require_docker", True)),
        minimum_free_disk_mb=int(c.get("minimum_free_disk_mb", 2048)),
        tcp_ports=ports,
    )

    b = raw.get("backup", {})
    cfg.backup = BackupSection(paths=[_path(x) for x in b.get("paths", [])])

    i = raw.get("install", {})
    cfg.install = InstallSection(
        panel_dir=_path(i.get("panel_dir", "/opt/remnawave")),
        node_dir=_path(i.get("node_dir", "/opt/remnanode")),
        reverse_proxy=str(i.get("reverse_proxy", "caddy")).lower(),
        subscription_bundled=bool(i.get("subscription_bundled", True)),
    )
    if cfg.install.reverse_proxy not in {"caddy"}:
        raise ConfigError("Поддерживается reverse_proxy = 'caddy'")

    mo = raw.get("mobile", {})
    cfg.mobile = MobileSection(
        enabled=bool(mo.get("enabled", True)),
        state_file=_path(mo.get("state_file", "/var/lib/hostfront-manager/mobile-state.json")),
        probe_timeout_seconds=float(mo.get("probe_timeout_seconds", 3.0)),
        failure_penalty=int(mo.get("failure_penalty", 18)),
        stale_after_seconds=int(mo.get("stale_after_seconds", 900)),
        prefer_tcp_on_unknown_network=bool(mo.get("prefer_tcp_on_unknown_network", True)),
    )
    if cfg.mobile.probe_timeout_seconds <= 0:
        raise ConfigError("mobile.probe_timeout_seconds должен быть > 0")
    if cfg.mobile.failure_penalty < 0:
        raise ConfigError("mobile.failure_penalty должен быть >= 0")

    no = raw.get("nodes", {})
    identity_raw = no.get("identity_file")
    cfg.nodes = NodesSection(
        ssh_user=str(no.get("ssh_user", "root")),
        ssh_port=int(no.get("ssh_port", 22)),
        identity_file=_path(identity_raw) if identity_raw else None,
        default_node_port=int(no.get("default_node_port", 2222)),
        enable_net_admin=bool(no.get("enable_net_admin", True)),
    )
    if not 1 <= cfg.nodes.ssh_port <= 65535:
        raise ConfigError("nodes.ssh_port должен быть 1..65535")
    if not 1 <= cfg.nodes.default_node_port <= 65535:
        raise ConfigError("nodes.default_node_port должен быть 1..65535")

    de = raw.get("deploy", {})
    cfg.deploy = DeploySection(
        transaction_dir=_path(de.get("transaction_dir", "/var/lib/hostfront-manager/transactions")),
        require_api_version_prefix=str(de.get("require_api_version_prefix", "3.2.")),
        allow_mutations=bool(de.get("allow_mutations", False)),
        health_timeout_seconds=int(de.get("health_timeout_seconds", 20)),
        automatic_rollback=bool(de.get("automatic_rollback", False)),
        require_verified_rollback_shape=bool(de.get("require_verified_rollback_shape", True)),
    )
    if cfg.deploy.health_timeout_seconds < 1:
        raise ConfigError("deploy.health_timeout_seconds должен быть >= 1")

    wa = raw.get("watchdog", {})
    cfg.watchdog = WatchdogSection(
        enabled=bool(wa.get("enabled", False)),
        state_file=_path(wa.get("state_file", "/var/lib/hostfront-manager/watchdog-state.json")),
        interval_seconds=int(wa.get("interval_seconds", 60)),
        failure_threshold=int(wa.get("failure_threshold", 3)),
        recovery_threshold=int(wa.get("recovery_threshold", 2)),
        cooldown_seconds=int(wa.get("cooldown_seconds", 300)),
        repair_window_seconds=int(wa.get("repair_window_seconds", 3600)),
        max_repairs_per_window=int(wa.get("max_repairs_per_window", 3)),
        auto_repair=bool(wa.get("auto_repair", False)),
        unattended_repair=bool(wa.get("unattended_repair", False)),
        allowed_services=[str(x) for x in wa.get("allowed_services", ["docker", "remnawave"])],
    )
    if min(cfg.watchdog.interval_seconds, cfg.watchdog.failure_threshold,
           cfg.watchdog.recovery_threshold, cfg.watchdog.repair_window_seconds,
           cfg.watchdog.max_repairs_per_window) < 1:
        raise ConfigError("Положительные watchdog-параметры должны быть >= 1")
    if cfg.watchdog.cooldown_seconds < 0:
        raise ConfigError("watchdog.cooldown_seconds должен быть >= 0")
    if any(not x or "/" in x or "\\" in x for x in cfg.watchdog.allowed_services):
        raise ConfigError("watchdog.allowed_services содержит недопустимое имя")

    we = raw.get("web", {})
    cfg.web = WebSection(
        enabled=bool(we.get("enabled", False)),
        bind=str(we.get("bind", "127.0.0.1")),
        port=int(we.get("port", 8765)),
        admin_token_env=str(we.get("admin_token_env", "HOSTFRONT_ADMIN_TOKEN")),
        telemetry_db=_path(we.get("telemetry_db", "/var/lib/hostfront-manager/telemetry.sqlite3")),
        telemetry_key_prefix=str(we.get("telemetry_key_prefix", "HOSTFRONT_TELEMETRY_KEY_")),
        telemetry_max_clock_skew_seconds=int(we.get("telemetry_max_clock_skew_seconds", 300)),
        telemetry_retention_days=int(we.get("telemetry_retention_days", 30)),
        trusted_proxy=bool(we.get("trusted_proxy", False)),
    )
    if not 1 <= cfg.web.port <= 65535:
        raise ConfigError("web.port должен быть 1..65535")
    if cfg.web.telemetry_max_clock_skew_seconds < 30:
        raise ConfigError("web.telemetry_max_clock_skew_seconds должен быть >= 30")
    if cfg.web.telemetry_retention_days < 1:
        raise ConfigError("web.telemetry_retention_days должен быть >= 1")

    return cfg


def load_secrets_environment(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigError(f"Не удалось прочитать secrets file {path}: {exc}") from exc
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Некорректная строка secrets file {path}:{number}")
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key):
            raise ConfigError(f"Некорректное имя переменной {path}:{number}")
        os.environ.setdefault(key, value)
