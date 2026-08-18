from __future__ import annotations

import shutil
import socket
from pathlib import Path

from .config import AppConfig
from .models import CheckResult, DoctorReport
from .state import collect_host_state


def _check_root(cfg: AppConfig) -> CheckResult:
    st = collect_host_state()
    ok = st.is_root or not cfg.checks.require_root
    return CheckResult(
        "root",
        ok,
        "root доступен" if st.is_root else "запуск не от root",
        {"required": cfg.checks.require_root},
        critical=cfg.checks.require_root,
    )


def _check_systemd(cfg: AppConfig) -> CheckResult:
    st = collect_host_state()
    ok = st.systemd_present or not cfg.checks.require_systemd
    return CheckResult(
        "systemd",
        ok,
        "systemd обнаружен" if st.systemd_present else "systemd не обнаружен",
        critical=cfg.checks.require_systemd,
    )


def _check_docker(cfg: AppConfig) -> CheckResult:
    st = collect_host_state()
    ok = st.docker_present or not cfg.checks.require_docker
    return CheckResult(
        "docker",
        ok,
        "docker найден" if st.docker_present else "docker не найден",
        critical=cfg.checks.require_docker,
    )


def _check_disk(cfg: AppConfig) -> CheckResult:
    target = cfg.manager.data_dir
    probe = target
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    free_mb = usage.free // (1024 * 1024)
    need = cfg.checks.minimum_free_disk_mb
    return CheckResult(
        "disk",
        free_mb >= need,
        f"свободно {free_mb} MB, требуется минимум {need} MB",
        {"free_mb": free_mb, "minimum_mb": need},
    )


def _check_dns(name: str, domain: str) -> CheckResult:
    if not domain:
        return CheckResult(name, True, "не настроен — пропущено", critical=False)
    try:
        infos = socket.getaddrinfo(domain, None)
        ips = sorted({item[4][0] for item in infos})
        return CheckResult(name, True, f"{domain} → {', '.join(ips)}", {"ips": ips})
    except socket.gaierror as exc:
        return CheckResult(name, False, f"{domain}: DNS ошибка: {exc}")


def _check_tcp_port_free(port: int) -> CheckResult:
    # Проверяем локальный listen через bind. EADDRINUSE обычно означает,
    # что порт уже занят сервисом. Это не заменяет внешний health-check.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        return CheckResult(
            f"tcp:{port}",
            True,
            f"порт {port} свободен",
            {"state": "free"},
            critical=False,
        )
    except OSError as exc:
        return CheckResult(
            f"tcp:{port}",
            True,
            f"порт {port} занят/прослушивается: {exc}",
            {"state": "in_use"},
            critical=False,
        )
    finally:
        sock.close()


def _check_tcp_listener(port: int) -> CheckResult:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
        ok = result == 0
        return CheckResult(
            f"runtime-tcp:{port}",
            ok,
            f"TCP/{port} listener доступен"
            if ok
            else f"TCP/{port} listener отсутствует",
            {"state": "listening" if ok else "down", "connect_errno": result},
            critical=True,
        )
    finally:
        sock.close()


def _check_udp_listener(port: int) -> CheckResult:
    try:
        rows = Path("/proc/net/udp").read_text(encoding="ascii").splitlines()[1:]
        needle = f":{port:04X}"
        ok = any(needle in row.split()[1] for row in rows if len(row.split()) > 1)
    except OSError as exc:
        return CheckResult(f"runtime-udp:{port}", False, str(exc), critical=True)
    return CheckResult(
        f"runtime-udp:{port}",
        ok,
        f"UDP/{port} listener обнаружен" if ok else f"UDP/{port} listener отсутствует",
        {"state": "listening" if ok else "down"},
        critical=True,
    )


def run_doctor(cfg: AppConfig) -> DoctorReport:
    checks = [
        _check_root(cfg),
        _check_systemd(cfg),
        _check_docker(cfg),
        _check_disk(cfg),
        _check_dns("dns:panel", cfg.domains.panel),
        _check_dns("dns:subscription", cfg.domains.subscription),
    ]
    checks.extend(_check_tcp_port_free(p) for p in cfg.checks.tcp_ports)
    checks.extend(_check_tcp_listener(p) for p in cfg.watchdog.expected_tcp_ports)
    checks.extend(_check_udp_listener(p) for p in cfg.watchdog.expected_udp_ports)

    if cfg.remnawave.enabled:
        token_ok = bool(cfg.remnawave.token())
        checks.append(
            CheckResult(
                "remnawave:token",
                token_ok,
                f"токен найден в ${cfg.remnawave.token_env}"
                if token_ok
                else f"нет переменной ${cfg.remnawave.token_env}",
                critical=False,  # станет critical на Этапе 2 при API-операциях
            )
        )
        checks.append(
            CheckResult(
                "remnawave:url",
                bool(cfg.remnawave.base_url),
                cfg.remnawave.base_url or "base_url не задан",
                critical=False,
            )
        )

    return DoctorReport(checks)
