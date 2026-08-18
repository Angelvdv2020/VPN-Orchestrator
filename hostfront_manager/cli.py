from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import secrets
import sys
import time
import traceback
from pathlib import Path

from . import __version__
from .backup import create_backup, list_backups, rollback
from .config import AppConfig, load_config, load_secrets_environment
from .deploy.bundle import load_mobile_bundle
from .deploy.deployer import apply_mobile_bundle_v32
from .deploy.journal import TransactionJournal
from .deploy.planner import build_deploy_plan
from .deploy.snapshot import capture_panel_snapshot
from .deploy.verify import verify_panel_after_apply, verify_rollback_after_apply
from .diagnostics import run_doctor
from .errors import ConfigError, LockError, ManagerError
from .install.common import atomic_write
from .install.services import render_services, write_services
from .install.wizard import InstallPlan, install_all, interactive_plan
from .lock import ProcessLock
from .logging_utils import setup_logging
from .mobile.defaults import default_paths
from .mobile.engine import recommend
from .mobile.models import NetworkKind, ProbeSample, ProbeStatus
from .mobile.policy import decide_failover
from .mobile.probes import probe_path
from .mobile.store import MobileStateStore
from .models import ExitCode
from .nodes.assignment import build_assignment_plan
from .nodes.compose import build_node_compose
from .nodes.lifecycle import apply_node_plan
from .nodes.models import NodeRuntimeSpec, RemoteTarget
from .nodes.payload import load_json_payload
from .nodes.remote import (
    deploy_compose,
    remote_health,
    remote_node_logs,
    remote_prepare,
    ssh_test,
)
from .profiles.builder import build_mobile_profile
from .profiles.bundle import write_bundle
from .profiles.keys import generate_basic, generate_reality_keypair
from .profiles.models import MobileProfileSettings, RealitySettings
from .profiles.validate import validate_with_xray
from .remnawave.capabilities import discover_capabilities
from .remnawave.client import RemnawaveClient
from .remnawave.inventory import fetch_inventory
from .remnawave.shape import unwrap_list
from .render import print_json, render_doctor, render_status
from .rollback.engine import apply_inverse_plan
from .rollback.planner import build_inverse_plan
from .security import redact_sensitive
from .setup_wizard import run_first_run
from .shell import ShellRunner
from .state import collect_host_state
from .telemetry.client import submit as submit_telemetry
from .watchdog.checks import collect_signals
from .watchdog.engine import evaluate, record_repair
from .watchdog.repair import restart_services
from .watchdog.store import WatchdogStore


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hostfront-manager")
    p.add_argument("--config", type=Path)
    p.add_argument("--debug", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    sub = p.add_subparsers(dest="command")
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("self-test")
    fr = sub.add_parser("first-run")
    fr.add_argument("--no-prompt", action="store_true")
    sub.add_parser("backup")
    sub.add_parser("backups")
    rb = sub.add_parser("rollback")
    rb.add_argument("backup_id")
    sub.add_parser("config-show")
    sub.add_parser("version")
    ia = sub.add_parser("install-all")
    ia.add_argument("--panel-domain")
    ia.add_argument("--subscription-domain")
    ia.add_argument("--with-subscription", action="store_true")

    mi = sub.add_parser("mobile-init")
    mi.add_argument("--host", required=True)
    mi.add_argument("--front-host")

    mp = sub.add_parser("mobile-probe")
    mp.add_argument(
        "--network", choices=["unknown", "mobile", "wifi"], default="unknown"
    )

    ms = sub.add_parser("mobile-status")
    ms.add_argument(
        "--network", choices=["unknown", "mobile", "wifi"], default="unknown"
    )

    mr = sub.add_parser("mobile-record")
    mr.add_argument("path_id")
    mr.add_argument("--status", choices=["up", "down", "unknown"], required=True)
    mr.add_argument("--latency-ms", type=float)
    mr.add_argument(
        "--network", choices=["unknown", "mobile", "wifi"], default="mobile"
    )
    mr.add_argument("--detail", default="")
    mr.add_argument("--source", default="client")

    ri = sub.add_parser("remnawave-inventory")
    ri.add_argument("--raw", action="store_true")

    np = sub.add_parser("node-plan")
    np.add_argument("--payload", type=Path, required=True)
    np.add_argument("--apply", action="store_true")

    ne = sub.add_parser("node-enable")
    ne.add_argument("uuid")

    nd = sub.add_parser("node-disable")
    nd.add_argument("uuid")

    nx = sub.add_parser("node-delete")
    nx.add_argument("uuid")
    nx.add_argument("--yes", action="store_true")

    nc = sub.add_parser("node-compose")
    nc.add_argument("--node-port", type=int)
    nc.add_argument("--secret-key", required=True)
    nc.add_argument("--mount-letsencrypt", action="store_true")
    nc.add_argument("--output", type=Path)

    nr = sub.add_parser("node-remote-deploy")
    nr.add_argument("--host", required=True)
    nr.add_argument("--user")
    nr.add_argument("--ssh-port", type=int)
    nr.add_argument("--identity-file")
    nr.add_argument("--node-port", type=int)
    nr.add_argument("--secret-key", required=True)
    nr.add_argument("--mount-letsencrypt", action="store_true")
    nr.add_argument("--prepare", action="store_true")
    nr.add_argument("--no-start", action="store_true")

    nh = sub.add_parser("node-remote-health")
    nh.add_argument("--host", required=True)
    nh.add_argument("--user")
    nh.add_argument("--ssh-port", type=int)
    nh.add_argument("--identity-file")
    nh.add_argument("--logs", action="store_true")

    pg = sub.add_parser("profile-generate-secrets")
    pg.add_argument("--with-reality", action="store_true")

    pb = sub.add_parser("mobile-profile-build")
    pb.add_argument("--name", default="Mobile")
    pb.add_argument("--edge-domain", required=True)
    pb.add_argument("--front-domain", required=True)
    pb.add_argument("--reality-target", required=True)
    pb.add_argument("--reality-server-name", required=True)
    pb.add_argument("--reality-private-key", required=True)
    pb.add_argument("--short-id", required=True)
    pb.add_argument("--hysteria-auth", required=True)
    pb.add_argument("--output-dir", type=Path, required=True)
    pb.add_argument("--xhttp-path", default="/mobile")
    pb.add_argument("--front-path", default="/edge")
    pb.add_argument("--reality-xhttp-port", type=int, default=443)
    pb.add_argument("--reality-raw-port", type=int, default=8443)
    pb.add_argument("--hysteria-port", type=int, default=443)
    pb.add_argument("--front-local-port", type=int, default=9443)
    pb.add_argument("--front-listen", default="172.18.0.1")
    pb.add_argument("--front-external-port", type=int, default=443)
    pb.add_argument("--validate", action="store_true")

    pv = sub.add_parser("mobile-profile-validate")
    pv.add_argument("config", type=Path)

    rc = sub.add_parser("remnawave-capabilities")
    rc.add_argument("--raw", action="store_true")

    dp = sub.add_parser("deploy-mobile-plan")
    dp.add_argument("bundle", type=Path)

    da = sub.add_parser("deploy-mobile-apply")
    da.add_argument("bundle", type=Path)
    da.add_argument("--yes", action="store_true")
    da.add_argument(
        "--force-without-rollback",
        action="store_true",
        help="разрешить apply при неполном snapshot (опасно)",
    )
    da.add_argument("--edge-node-uuid")
    da.add_argument("--front-node-uuid")

    sub.add_parser("transactions")

    rb = sub.add_parser("transaction-rollback")
    rb.add_argument("transaction_id")
    rb.add_argument("--yes", action="store_true")

    nap = sub.add_parser("node-role-plan")
    nap.add_argument("--bundle", type=Path, required=True)
    nap.add_argument("--node-uuid", required=True)
    nap.add_argument("--profile-uuid", required=True)
    nap.add_argument("--role", choices=["edge", "front"], required=True)

    naa = sub.add_parser("node-role-apply")
    naa.add_argument("--bundle", type=Path, required=True)
    naa.add_argument("--node-uuid", required=True)
    naa.add_argument("--profile-uuid", required=True)
    naa.add_argument("--role", choices=["edge", "front"], required=True)
    naa.add_argument("--yes", action="store_true")

    fo = sub.add_parser("mobile-failover")
    fo.add_argument(
        "--network", choices=["unknown", "mobile", "wifi"], default="mobile"
    )
    fo.add_argument("--current-path")
    fo.add_argument("--minimum-score-gain", type=float, default=15.0)

    sub.add_parser("watchdog-status")
    wo = sub.add_parser("watchdog-once")
    wo.add_argument("--repair", action="store_true")
    wo.add_argument("--yes", action="store_true")
    wr = sub.add_parser("watchdog-run")
    wr.add_argument("--iterations", type=int, default=0, help="0 = работать постоянно")

    sub.add_parser("web-serve")
    sub.add_parser("admin-token-generate")
    sub.add_parser("telemetry-key-generate")
    si = sub.add_parser("secrets-init")
    si.add_argument(
        "--path", type=Path, default=Path("/etc/hostfront-manager/secrets.env")
    )
    si.add_argument("--device-id", default="phone-1")
    si.add_argument("--yes", action="store_true")
    ss = sub.add_parser("secret-set")
    ss.add_argument("name", choices=["REMNAWAVE_TOKEN"])
    ss.add_argument(
        "--path", type=Path, default=Path("/etc/hostfront-manager/secrets.env")
    )
    ts = sub.add_parser("telemetry-submit")
    ts.add_argument("--endpoint", required=True)
    ts.add_argument("--device-id", required=True)
    ts.add_argument("--key-env", default="HOSTFRONT_DEVICE_KEY")
    ts.add_argument("--path-id", required=True)
    ts.add_argument("--status", choices=["up", "down", "unknown"], required=True)
    ts.add_argument(
        "--network", choices=["mobile", "wifi", "unknown"], default="mobile"
    )
    ts.add_argument("--operator", default="")
    ts.add_argument("--country", default="")
    ts.add_argument("--latency-ms", type=float)
    ts.add_argument("--detail", default="")
    sr = sub.add_parser("systemd-render")
    sr.add_argument("--output-dir", type=Path, required=True)
    sr.add_argument(
        "--executable", default="/opt/hostfront-manager/.venv/bin/hostfront-manager"
    )
    sr.add_argument(
        "--config-path", type=Path, default=Path("/etc/hostfront-manager/config.toml")
    )

    return p


def _menu() -> str:
    print()
    print("=== VPN Orchestrator ===")
    print("Консольная панель управления VPN-инфраструктурой")
    print("1. Состояние сервера")
    print("2. Полная диагностика")
    print("3. Самопроверка Manager")
    print("4. Создать резервную копию")
    print("5. Показать резервные копии")
    print("6. Показать безопасную конфигурацию")
    print("7. Установка и обновление компонентов")
    print("8. Устойчивость мобильных подключений")
    print("9. Ноды и объекты Remnawave")
    print("10. Управление нодами")
    print("11. Конструктор мобильного профиля")
    print("12. Применение и история транзакций")
    print("13. Откат, роли нод и переключение транспорта")
    print("14. Состояние watchdog и Auto Repair")
    print("0. Выход")
    print()
    value = input("Выбери пункт: ").strip()
    return {
        "1": "status",
        "2": "doctor",
        "3": "self-test",
        "4": "backup",
        "5": "backups",
        "6": "config-show",
        "7": "install-menu",
        "8": "mobile-status",
        "9": "remnawave-inventory",
        "10": "node-menu",
        "11": "profile-menu",
        "12": "deploy-menu",
        "13": "resilience-menu",
        "14": "watchdog-status",
        "0": "exit",
    }.get(value, "")


def _config_public(cfg: AppConfig) -> dict:
    return {
        "manager": {
            "data_dir": str(cfg.manager.data_dir),
            "log_dir": str(cfg.manager.log_dir),
            "backup_dir": str(cfg.manager.backup_dir),
            "lock_file": str(cfg.manager.lock_file),
            "command_timeout_seconds": cfg.manager.command_timeout_seconds,
            "backup_keep": cfg.manager.backup_keep,
            "secrets_file": str(cfg.manager.secrets_file),
        },
        "remnawave": {
            "enabled": cfg.remnawave.enabled,
            "base_url": cfg.remnawave.base_url,
            "token_env": cfg.remnawave.token_env,
            "token_present": bool(cfg.remnawave.token()),
        },
        "domains": {
            "panel": cfg.domains.panel,
            "subscription": cfg.domains.subscription,
        },
        "checks": {
            "require_root": cfg.checks.require_root,
            "require_systemd": cfg.checks.require_systemd,
            "require_docker": cfg.checks.require_docker,
            "minimum_free_disk_mb": cfg.checks.minimum_free_disk_mb,
            "tcp_ports": cfg.checks.tcp_ports,
        },
        "backup": {"paths": [str(x) for x in cfg.backup.paths]},
        "watchdog": {
            "enabled": cfg.watchdog.enabled,
            "state_file": str(cfg.watchdog.state_file),
            "interval_seconds": cfg.watchdog.interval_seconds,
            "failure_threshold": cfg.watchdog.failure_threshold,
            "recovery_threshold": cfg.watchdog.recovery_threshold,
            "cooldown_seconds": cfg.watchdog.cooldown_seconds,
            "max_repairs_per_window": cfg.watchdog.max_repairs_per_window,
            "auto_repair": cfg.watchdog.auto_repair,
            "unattended_repair": cfg.watchdog.unattended_repair,
            "allowed_services": cfg.watchdog.allowed_services,
        },
    }


def _dispatch(args, cfg: AppConfig, logger: logging.Logger) -> int:
    cmd = args.command

    if not cmd:
        cmd = _menu()
        if cmd == "exit":
            return ExitCode.OK
        if not cmd:
            print("Неизвестный пункт")
            return ExitCode.ERROR

    if cmd == "resilience-menu":
        print("=== УСТОЙЧИВОСТЬ И ОТКАТ ===")
        print("Команды:")
        print("  transaction-rollback <transaction-id>")
        print(
            "  node-role-plan --bundle ... --node-uuid ... --profile-uuid ... --role edge"
        )
        print("  node-role-apply ... --yes")
        print("  mobile-failover --network mobile --current-path reality-xhttp")
        return ExitCode.OK

    if cmd == "deploy-menu":
        print("=== ПРИМЕНЕНИЕ И ТРАНЗАКЦИИ ===")
        print("Команды:")
        print("  remnawave-capabilities")
        print("  deploy-mobile-plan ./mobile-bundle")
        print("  deploy-mobile-apply ./mobile-bundle --yes")
        print("  transactions")
        return ExitCode.OK

    if cmd == "profile-menu":
        print("=== КОНСТРУКТОР МОБИЛЬНОГО ПРОФИЛЯ ===")
        print("Используй команды:")
        print("  profile-generate-secrets --with-reality")
        print("  mobile-profile-build ... --output-dir ./bundle --validate")
        print("  mobile-profile-validate ./bundle/xray-config.json")
        return ExitCode.OK

    if cmd == "node-menu":
        print("=== УПРАВЛЕНИЕ НОДАМИ ===")
        print("Используй CLI-команды:")
        print("  node-plan --payload node.json")
        print("  node-plan --payload node.json --apply")
        print("  node-compose --secret-key ...")
        print("  node-remote-deploy --host ... --secret-key ...")
        print("  node-remote-health --host ...")
        return ExitCode.OK

    if cmd == "install-menu":
        print("=== УСТАНОВКА И ОБНОВЛЕНИЕ ===")
        print("Безопасные команды запускаются с явными доменами:")
        print(
            "  hostfront-manager install-all --panel-domain ... --subscription-domain ..."
        )
        print("  sudo bash install.sh --panel-domain ... --subscription-domain ...")
        return ExitCode.OK

    if cmd == "version":
        print(__version__)
        return ExitCode.OK

    if cmd == "admin-token-generate":
        print(secrets.token_urlsafe(48))
        return ExitCode.OK

    if cmd == "telemetry-key-generate":
        print(secrets.token_urlsafe(48))
        return ExitCode.OK

    if cmd == "secrets-init":
        if not args.yes:
            raise ManagerError("Для secrets-init добавь --yes")
        if args.path.exists():
            raise ManagerError(
                f"Файл уже существует, перезапись запрещена: {args.path}"
            )
        from .telemetry.auth import device_env_name

        device_name = device_env_name(cfg.web.telemetry_key_prefix, args.device_id)
        content = (
            f"{cfg.web.admin_token_env}={secrets.token_urlsafe(48)}\n"
            f"{device_name}={secrets.token_urlsafe(48)}\n"
            f"REMNAWAVE_TOKEN=\n"
        )
        atomic_write(args.path, content, 0o600)
        data = {
            "path": str(args.path),
            "mode": "0600",
            "device_id": args.device_id,
            "environment_names": [
                cfg.web.admin_token_env,
                device_name,
                "REMNAWAVE_TOKEN",
            ],
        }
        print_json(data) if args.json else print(
            json.dumps(data, ensure_ascii=False, indent=2)
        )
        return ExitCode.OK

    if cmd == "secret-set":
        if not args.path.exists():
            raise ManagerError(f"Файл не найден: {args.path}")
        value = getpass.getpass(f"{args.name}: ")
        if not value or "\n" in value or "\r" in value:
            raise ManagerError("Секрет пустой или содержит перевод строки")
        lines = args.path.read_text(encoding="utf-8").splitlines()
        updated = []
        found = False
        for line in lines:
            if line.startswith(args.name + "="):
                updated.append(args.name + "=" + value)
                found = True
            else:
                updated.append(line)
        if not found:
            updated.append(args.name + "=" + value)
        atomic_write(args.path, "\n".join(updated) + "\n", 0o600)
        print(f"{args.name} сохранён в {args.path}")
        return ExitCode.OK

    if cmd == "telemetry-submit":
        key = os.getenv(args.key_env)
        if not key:
            raise ManagerError(f"Не задан ${args.key_env}")
        payload = {
            "observed_at": int(time.time()),
            "path_id": args.path_id,
            "status": args.status,
            "network": args.network,
            "operator": args.operator,
            "country": args.country.upper(),
            "latency_ms": args.latency_ms,
            "detail": args.detail,
        }
        result = submit_telemetry(
            args.endpoint,
            args.device_id,
            key,
            payload,
            timeout=cfg.manager.command_timeout_seconds,
        )
        print_json(result) if args.json else print(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        return ExitCode.OK

    if cmd == "systemd-render":
        files = render_services(
            args.executable,
            args.config_path,
            Path("/etc/hostfront-manager/secrets.env"),
        )
        paths = write_services(files, args.output_dir)
        data = {"files": [str(x) for x in paths]}
        print_json(data) if args.json else print("\n".join(data["files"]))
        return ExitCode.OK

    if cmd == "web-serve":
        if not cfg.web.enabled:
            raise ManagerError("web.enabled=false")
        if not cfg.web.admin_token():
            raise ManagerError(f"Не задан ${cfg.web.admin_token_env}")
        try:
            import uvicorn

            from .web.app import create_app
        except ImportError as exc:
            raise ManagerError(
                "Web dependencies не установлены: pip install -e ."
            ) from exc
        uvicorn.run(
            create_app(cfg),
            host=cfg.web.bind,
            port=cfg.web.port,
            proxy_headers=cfg.web.trusted_proxy,
            forwarded_allow_ips="127.0.0.1",
        )
        return ExitCode.OK

    if cmd == "status":
        state = collect_host_state()
        if args.json:
            print_json(state.to_dict())
        else:
            render_status(state)
        return ExitCode.OK

    if cmd in {"doctor", "self-test"}:
        report = run_doctor(cfg)
        if args.json:
            print_json(report.to_dict())
        else:
            render_doctor(report)
        return ExitCode.OK if report.ok else ExitCode.CHECK_FAILED

    if cmd == "backup":
        if args.dry_run:
            existing = [str(p) for p in cfg.backup.paths if p.exists()]
            data = {"dry_run": True, "would_backup": existing}
            print_json(data) if args.json else print(
                "Будет сохранено:\n" + "\n".join(existing)
            )
            return ExitCode.OK
        archive = create_backup(cfg)
        print_json({"backup": str(archive)}) if args.json else print(
            f"Backup создан: {archive}"
        )
        return ExitCode.OK

    if cmd == "backups":
        items = [str(x) for x in list_backups(cfg)]
        print_json(items) if args.json else print(
            "\n".join(items) if items else "Backup пока нет"
        )
        return ExitCode.OK

    if cmd == "rollback":
        restored = rollback(cfg, args.backup_id, dry_run=args.dry_run)
        if args.json:
            print_json({"dry_run": args.dry_run, "paths": restored})
        else:
            title = "Будут восстановлены:" if args.dry_run else "Восстановлено:"
            print(title)
            print("\n".join(restored))
        return ExitCode.OK

    if cmd == "config-show":
        data = _config_public(cfg)
        print_json(data) if args.json else print(
            json.dumps(data, ensure_ascii=False, indent=2)
        )
        return ExitCode.OK

    if cmd == "install-all":
        panel_domain = getattr(args, "panel_domain", None)
        subscription_domain = getattr(args, "subscription_domain", None)
        with_subscription = bool(getattr(args, "with_subscription", False))
        if panel_domain:
            plan = InstallPlan(
                panel_domain=panel_domain,
                subscription_domain=subscription_domain or panel_domain,
                install_subscription=with_subscription,
            )
        else:
            plan = interactive_plan()

        runner = ShellRunner(
            logger,
            timeout=cfg.manager.command_timeout_seconds,
            dry_run=args.dry_run,
            secrets=[cfg.remnawave.token() or ""],
        )
        result = install_all(cfg, runner, plan)
        if args.json:
            print_json(result)
        else:
            print("Установка завершена.")
            print(f"Панель: https://{plan.panel_domain}")
            print(f"Subscription Page: {result['subscription']}")
        return ExitCode.OK

    if cmd == "first-run":
        runner = ShellRunner(
            logger,
            timeout=cfg.manager.command_timeout_seconds,
            dry_run=args.dry_run,
            secrets=[cfg.remnawave.token() or ""],
        )
        result = run_first_run(cfg, runner)
        return ExitCode.OK if result.get("bundle_dir") else ExitCode.ERROR

    if cmd == "mobile-init":
        store = MobileStateStore(cfg.mobile.state_file)
        paths = default_paths(args.host, args.front_host)
        saved = store.set_paths(paths)
        data = {"state_file": str(saved), "paths": [x.to_dict() for x in paths]}
        print_json(data) if args.json else print(
            "Mobile profile создан:\n"
            + "\n".join(
                f"- {x.name}: {x.network.upper()} {x.host}:{x.port}" for x in paths
            )
        )
        return ExitCode.OK

    if cmd == "mobile-probe":
        store = MobileStateStore(cfg.mobile.state_file)
        paths = store.paths()
        if not paths:
            raise ManagerError(
                "Mobile profile не создан. Сначала: mobile-init --host <domain>"
            )
        network_kind = NetworkKind(args.network)
        rows = []
        for path in paths:
            sample = probe_path(path, cfg.mobile.probe_timeout_seconds)
            sample.network_kind = network_kind
            store.add_sample(sample)
            rows.append(sample.to_dict())

        rec = recommend(
            paths,
            store.samples(),
            network_kind=network_kind,
            failure_penalty=cfg.mobile.failure_penalty,
            stale_after_seconds=cfg.mobile.stale_after_seconds,
            prefer_tcp_on_unknown_network=cfg.mobile.prefer_tcp_on_unknown_network,
        )
        data = {"probes": rows, "recommendation": rec.to_dict()}
        if args.json:
            print_json(data)
        else:
            for row in rows:
                print(f"{row['path_id']:18} {row['status']:8} {row.get('detail', '')}")
            print()
            print("Рекомендация:", rec.reason)
        return ExitCode.OK

    if cmd == "mobile-status":
        # Интерактивное меню не имеет args.network — используем unknown.
        network_value = getattr(args, "network", "unknown")
        store = MobileStateStore(cfg.mobile.state_file)
        paths = store.paths()
        if not paths:
            raise ManagerError(
                "Mobile profile не создан. Сначала: mobile-init --host <domain>"
            )
        rec = recommend(
            paths,
            store.samples(),
            network_kind=NetworkKind(network_value),
            failure_penalty=cfg.mobile.failure_penalty,
            stale_after_seconds=cfg.mobile.stale_after_seconds,
            prefer_tcp_on_unknown_network=cfg.mobile.prefer_tcp_on_unknown_network,
        )
        if args.json:
            print_json(rec.to_dict())
        else:
            print("=== MOBILE RESILIENCE ===")
            for row in rec.ordered:
                print(
                    f"{row.path.name:24} "
                    f"{row.status.value:8} "
                    f"score={row.score:6.1f}  {row.reason}"
                )
            print()
            print(
                "Выбор:",
                rec.selected.path.name if rec.selected else "нет рабочего пути",
            )
        return ExitCode.OK

    if cmd == "mobile-record":
        store = MobileStateStore(cfg.mobile.state_file)
        known = {x.id for x in store.paths()}
        if args.path_id not in known:
            raise ManagerError(f"Неизвестный path_id: {args.path_id}")
        sample = ProbeSample.now(
            args.path_id,
            ProbeStatus(args.status),
            latency_ms=args.latency_ms,
            source=args.source,
            detail=args.detail,
            network_kind=NetworkKind(args.network),
        )
        path = store.add_sample(sample)
        data = {"saved": str(path), "sample": sample.to_dict()}
        print_json(data) if args.json else print(
            f"Записано: {args.path_id} -> {args.status}"
        )
        return ExitCode.OK

    if cmd == "remnawave-inventory":
        token = cfg.remnawave.token()
        if not token:
            raise ManagerError(f"Не задан ${cfg.remnawave.token_env}")
        if not cfg.remnawave.base_url:
            raise ManagerError("Не задан remnawave.base_url в config.toml")

        client = RemnawaveClient(
            cfg.remnawave.base_url,
            token,
            timeout=cfg.manager.command_timeout_seconds,
        )
        summary, raw = fetch_inventory(client)
        data = {"summary": summary.to_dict()}
        if getattr(args, "raw", False):
            data["raw"] = raw
        if args.json or getattr(args, "raw", False):
            print_json(redact_sensitive(data))
        else:
            print("=== REMNAWAVE INVENTORY ===")
            for key, value in summary.to_dict().items():
                print(f"{key:18}: {value}")
        return ExitCode.OK

    if cmd in {"node-plan", "node-enable", "node-disable", "node-delete"}:
        token = cfg.remnawave.token()
        if not token:
            raise ManagerError(f"Не задан ${cfg.remnawave.token_env}")
        if not cfg.remnawave.base_url:
            raise ManagerError("Не задан remnawave.base_url")

        client = RemnawaveClient(
            cfg.remnawave.base_url,
            token,
            timeout=cfg.manager.command_timeout_seconds,
        )

        if cmd == "node-plan":
            payload = load_json_payload(args.payload)
            result = apply_node_plan(client, payload, apply=bool(args.apply))
            print_json(result) if args.json else print(
                json.dumps(result, ensure_ascii=False, indent=2)
            )
            return ExitCode.OK

        if cmd == "node-enable":
            result = client.enable_node(args.uuid)
            print_json(result) if args.json else print("Node enabled")
            return ExitCode.OK

        if cmd == "node-disable":
            result = client.disable_node(args.uuid)
            print_json(result) if args.json else print("Node disabled")
            return ExitCode.OK

        if cmd == "node-delete":
            if not args.yes:
                raise ManagerError(
                    "Удаление требует явного подтверждения: добавь --yes"
                )
            result = client.delete_node(args.uuid)
            print_json(result) if args.json else print("Node deleted")
            return ExitCode.OK

    if cmd == "node-compose":
        node_port = args.node_port or cfg.nodes.default_node_port
        spec = NodeRuntimeSpec(
            node_port=node_port,
            secret_key=args.secret_key,
            enable_net_admin=cfg.nodes.enable_net_admin,
            mount_letsencrypt=args.mount_letsencrypt,
        )
        compose = build_node_compose(spec)
        if args.output:
            args.output.write_text(compose, encoding="utf-8")
            print(f"Compose сохранён: {args.output}")
        else:
            print(compose)
        return ExitCode.OK

    if cmd in {"node-remote-deploy", "node-remote-health"}:
        target = RemoteTarget(
            host=args.host,
            user=args.user or cfg.nodes.ssh_user,
            ssh_port=args.ssh_port or cfg.nodes.ssh_port,
            identity_file=args.identity_file
            or (str(cfg.nodes.identity_file) if cfg.nodes.identity_file else None),
        )
        runner = ShellRunner(
            logger,
            timeout=cfg.manager.command_timeout_seconds,
            dry_run=args.dry_run,
            secrets=[getattr(args, "secret_key", "") or ""],
        )

        if cmd == "node-remote-health":
            ssh_test(runner, target)
            health = remote_health(runner, target)
            if args.logs:
                health["logs"] = remote_node_logs(runner, target, tail=100)
            print_json(health) if args.json else print(
                json.dumps(health, ensure_ascii=False, indent=2)
            )
            return ExitCode.OK if health.get("ok") else ExitCode.CHECK_FAILED

        ssh_test(runner, target)
        if args.prepare:
            remote_prepare(runner, target)

        spec = NodeRuntimeSpec(
            node_port=args.node_port or cfg.nodes.default_node_port,
            secret_key=args.secret_key,
            enable_net_admin=cfg.nodes.enable_net_admin,
            mount_letsencrypt=args.mount_letsencrypt,
        )
        compose = build_node_compose(spec)
        deploy_compose(
            runner,
            target,
            compose,
            start=not args.no_start,
        )
        health = (
            remote_health(runner, target)
            if not args.no_start
            else {"ok": True, "skipped": True}
        )
        print_json(health) if args.json else print(
            json.dumps(health, ensure_ascii=False, indent=2)
        )
        return ExitCode.OK if health.get("ok") else ExitCode.CHECK_FAILED

    if cmd == "profile-generate-secrets":
        runner = ShellRunner(
            logger,
            timeout=cfg.manager.command_timeout_seconds,
            dry_run=args.dry_run,
        )
        vless_uuid, short_id, hy_auth = generate_basic()
        private_key = None
        password = None
        if args.with_reality:
            private_key, password = generate_reality_keypair(runner)

        data = {
            "vless_uuid": vless_uuid,
            "short_id": short_id,
            "hysteria_auth": hy_auth,
            "reality_private_key": private_key,
            "reality_password": password,
        }
        # Secret-generating command is intentionally explicit.
        print_json(data) if args.json else print(
            json.dumps(data, ensure_ascii=False, indent=2)
        )
        return ExitCode.OK

    if cmd == "mobile-profile-build":
        settings = MobileProfileSettings(
            name=args.name,
            edge_domain=args.edge_domain,
            front_domain=args.front_domain,
            reality=RealitySettings(
                target=args.reality_target,
                server_name=args.reality_server_name,
                private_key=args.reality_private_key,
                short_id=args.short_id,
            ),
            reality_xhttp_port=args.reality_xhttp_port,
            reality_raw_port=args.reality_raw_port,
            hysteria_port=args.hysteria_port,
            host_front_local_port=args.front_local_port,
            host_front_listen=args.front_listen,
            host_front_external_port=args.front_external_port,
            xhttp_path=args.xhttp_path,
            host_front_path=args.front_path,
            hysteria_auth=args.hysteria_auth,
        )
        try:
            profile = build_mobile_profile(settings)
        except ValueError as exc:
            raise ManagerError(str(exc)) from exc

        created = write_bundle(profile, args.output_dir)
        result = {
            "bundle_dir": str(args.output_dir),
            "files": [str(x) for x in created],
            "validation": None,
        }

        if args.validate:
            runner = ShellRunner(
                logger,
                timeout=cfg.manager.command_timeout_seconds,
                dry_run=False,
                secrets=[args.reality_private_key, args.hysteria_auth],
            )
            validation = validate_with_xray(profile.xray_config, runner)
            result["validation"] = validation.to_dict()
            if not validation.ok:
                print_json(result) if args.json else print(
                    json.dumps(result, ensure_ascii=False, indent=2)
                )
                return ExitCode.CHECK_FAILED

        print_json(result) if args.json else print(
            "Mobile profile bundle создан:\n" + "\n".join(result["files"])
        )
        return ExitCode.OK

    if cmd == "mobile-profile-validate":
        if not args.config.exists():
            raise ManagerError(f"Файл не найден: {args.config}")
        try:
            config = json.loads(args.config.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ManagerError(f"Не удалось прочитать JSON: {exc}") from exc

        runner = ShellRunner(
            logger,
            timeout=cfg.manager.command_timeout_seconds,
            dry_run=False,
        )
        result = validate_with_xray(config, runner)
        print_json(result.to_dict()) if args.json else print(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        )
        return ExitCode.OK if result.ok else ExitCode.CHECK_FAILED

    if cmd in {
        "remnawave-capabilities",
        "deploy-mobile-plan",
        "deploy-mobile-apply",
    }:
        token = cfg.remnawave.token()
        if not token:
            raise ManagerError(f"Не задан ${cfg.remnawave.token_env}")
        if not cfg.remnawave.base_url:
            raise ManagerError("Не задан remnawave.base_url")

        client = RemnawaveClient(
            cfg.remnawave.base_url,
            token,
            timeout=cfg.manager.command_timeout_seconds,
        )

        caps, raw_caps = discover_capabilities(client)

        if cmd == "remnawave-capabilities":
            data = {"capabilities": caps.to_dict()}
            if args.raw:
                data["raw"] = raw_caps
            print_json(data) if args.json or args.raw else print(
                json.dumps(data, ensure_ascii=False, indent=2)
            )
            return ExitCode.OK

        bundle = load_mobile_bundle(args.bundle)
        journal = TransactionJournal(cfg.deploy.transaction_dir)
        tx = journal.begin(
            "deploy-mobile-profile",
            metadata={
                "bundle": str(args.bundle),
                "panel": cfg.remnawave.base_url,
                "api_version": caps.api_version,
            },
        )
        journal.write_json(tx.path / "capabilities.json", caps.to_dict())
        snapshot = capture_panel_snapshot(
            client,
            journal,
            tx,
            force_without_rollback=bool(getattr(args, "force_without_rollback", False)),
        )
        plan = build_deploy_plan(bundle, snapshot)
        journal.write_json(tx.path / "plan.json", plan.to_dict())

        if cmd == "deploy-mobile-plan":
            journal.update_status(tx, "planned")
            data = {
                "transaction": tx.id,
                "capabilities": caps.to_dict(),
                "plan": plan.to_dict(),
            }
            safe_data = redact_sensitive(data)
            print_json(safe_data) if args.json else print(
                json.dumps(safe_data, ensure_ascii=False, indent=2)
            )
            return ExitCode.OK

        if not args.yes:
            journal.update_status(tx, "cancelled", {"reason": "--yes required"})
            raise ManagerError("Для применения добавь --yes")

        if not cfg.deploy.allow_mutations:
            journal.update_status(
                tx,
                "blocked",
                {"reason": "deploy.allow_mutations=false"},
            )
            raise ManagerError(
                "API mutations выключены. "
                "После проверки plan установи [deploy] allow_mutations = true"
            )

        try:
            applied = apply_mobile_bundle_v32(
                client,
                caps,
                bundle,
                journal,
                tx,
                required_version_prefix=cfg.deploy.require_api_version_prefix,
            )
            journal.write_json(tx.path / "applied.json", applied)

            verification = verify_panel_after_apply(
                client,
                expected_inbound_tags=list(bundle.inbound_map),
                expected_role_nodes={
                    role: node_uuid
                    for role, node_uuid in (
                        ("edge", getattr(args, "edge_node_uuid", None)),
                        ("front", getattr(args, "front_node_uuid", None)),
                    )
                    if node_uuid
                },
                role_inbound_tags={
                    role: list(data.get("enable_inbounds", []))
                    for role, data in bundle.node_roles.items()
                    if isinstance(data, dict)
                },
            )
            journal.write_json(tx.path / "verify.json", verification)

            if not verification.get("ok"):
                inverse = build_inverse_plan(snapshot, applied)
                journal.write_json(
                    tx.path / "inverse-plan.json",
                    [x.to_dict() for x in inverse],
                )

                if cfg.deploy.automatic_rollback:
                    rollback_result = apply_inverse_plan(
                        client,
                        inverse,
                        require_verified_shape=cfg.deploy.require_verified_rollback_shape,
                        apply=True,
                    )
                    journal.write_json(
                        tx.path / "rollback-result.json",
                        rollback_result,
                    )
                    rollback_verify = verify_rollback_after_apply(
                        client, snapshot, applied
                    )
                    journal.write_json(
                        tx.path / "rollback-verify.json",
                        rollback_verify,
                    )
                    journal.update_status(
                        tx,
                        "rolled_back"
                        if rollback_verify.get("ok")
                        else "rollback_verification_failed",
                        {
                            "verification": verification,
                            "rollback_verification": rollback_verify,
                        },
                    )
                    raise ManagerError(
                        "Post-check не пройден; выполнен автоматический rollback. "
                        f"Transaction: {tx.id}"
                    )

                journal.update_status(
                    tx,
                    "verification_failed",
                    {"verification": verification},
                )
                raise ManagerError(
                    "Apply выполнен, но post-check не пройден. "
                    f"Transaction: {tx.id}. Создан inverse-plan; "
                    "rollback можно проверить командой transaction-rollback."
                )

            journal.update_status(
                tx,
                "committed",
                {"verification": verification},
            )
            data = {
                "transaction": tx.id,
                "applied": applied,
                "verification": verification,
            }
            safe_data = redact_sensitive(data)
            print_json(safe_data) if args.json else print(
                json.dumps(safe_data, ensure_ascii=False, indent=2)
            )
            return ExitCode.OK

        except Exception as exc:
            if (
                cfg.deploy.automatic_rollback
                and journal.status(tx)
                not in {
                    "rolled_back",
                    "rollback_verification_failed",
                    "rollback_failed",
                }
                and (tx.path / "applied.json").exists()
            ):
                partial = json.loads(
                    (tx.path / "applied.json").read_text(encoding="utf-8")
                )
                if partial.get("results"):
                    inverse = build_inverse_plan(snapshot, partial)
                    journal.write_json(
                        tx.path / "inverse-plan.json",
                        [step.to_dict() for step in inverse],
                    )
                    try:
                        rollback_result = apply_inverse_plan(
                            client,
                            inverse,
                            require_verified_shape=cfg.deploy.require_verified_rollback_shape,
                            apply=True,
                        )
                        journal.write_json(
                            tx.path / "rollback-result.json", rollback_result
                        )
                        rollback_verify = verify_rollback_after_apply(
                            client, snapshot, partial
                        )
                        journal.write_json(
                            tx.path / "rollback-verify.json", rollback_verify
                        )
                        rollback_status = (
                            "rolled_back"
                            if rollback_verify.get("ok")
                            else "rollback_verification_failed"
                        )
                        journal.update_status(
                            tx,
                            rollback_status,
                            {
                                "apply_error": str(exc),
                                "rollback_verification": rollback_verify,
                            },
                        )
                    except Exception as rollback_exc:  # noqa: BLE001
                        journal.update_status(
                            tx,
                            "rollback_failed",
                            {
                                "apply_error": str(exc),
                                "rollback_error": str(rollback_exc),
                            },
                        )
                        raise ManagerError(
                            "Apply завершился ошибкой, затем ошибкой завершился rollback. "
                            f"Transaction: {tx.id}; rollback: {rollback_exc}"
                        ) from exc
                    raise ManagerError(
                        "Apply завершился ошибкой; выполнен автоматический rollback. "
                        f"Transaction: {tx.id}; status: {rollback_status}"
                    ) from exc
            journal.update_failure(tx, exc)
            raise

    if cmd == "transactions":
        journal = TransactionJournal(cfg.deploy.transaction_dir)
        items = []
        for path in journal.list_transactions():
            try:
                manifest = json.loads(
                    (path / "manifest.json").read_text(encoding="utf-8")
                )
            except Exception:  # noqa: BLE001
                manifest = {"id": path.name, "status": "unreadable"}
            items.append(manifest)
        print_json(items) if args.json else print(
            json.dumps(items, ensure_ascii=False, indent=2)
        )
        return ExitCode.OK

    if cmd == "transaction-rollback":
        journal = TransactionJournal(cfg.deploy.transaction_dir)
        tx_path = next(
            (p for p in journal.list_transactions() if p.name == args.transaction_id),
            None,
        )
        if tx_path is None:
            raise ManagerError(f"Transaction не найдена: {args.transaction_id}")

        before_file = tx_path / "before.json"
        applied_file = tx_path / "applied.json"
        if not before_file.exists() or not applied_file.exists():
            raise ManagerError("В transaction нет before.json/applied.json")

        before = json.loads(before_file.read_text(encoding="utf-8"))
        applied = json.loads(applied_file.read_text(encoding="utf-8"))
        inverse = build_inverse_plan(before, applied)

        inverse_json = [x.to_dict() for x in inverse]
        journal.write_json(tx_path / "inverse-plan.json", inverse_json)

        if not args.yes:
            print_json(
                {
                    "transaction": args.transaction_id,
                    "apply": False,
                    "inverse_plan": inverse_json,
                    "message": "Это только план. Для применения добавь --yes.",
                }
            ) if args.json else print(
                json.dumps(
                    {
                        "transaction": args.transaction_id,
                        "apply": False,
                        "inverse_plan": inverse_json,
                        "message": "Это только план. Для применения добавь --yes.",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return ExitCode.OK

        if not cfg.deploy.allow_mutations:
            raise ManagerError("deploy.allow_mutations=false")

        token = cfg.remnawave.token()
        if not token or not cfg.remnawave.base_url:
            raise ManagerError("Не настроен Remnawave API")

        client = RemnawaveClient(
            cfg.remnawave.base_url,
            token,
            timeout=cfg.manager.command_timeout_seconds,
        )
        result = apply_inverse_plan(
            client,
            inverse,
            require_verified_shape=cfg.deploy.require_verified_rollback_shape,
            apply=True,
        )
        journal.write_json(tx_path / "rollback-result.json", result)

        verification = verify_rollback_after_apply(client, before, applied)
        journal.write_json(tx_path / "rollback-verify.json", verification)
        journal.update_status(
            type("Tx", (), {"path": tx_path})(),
            "rolled_back" if verification.get("ok") else "rollback_verification_failed",
            {"rollback_verification": verification},
        )

        data = {
            "transaction": args.transaction_id,
            "rollback": result,
            "verification": verification,
        }
        print_json(data) if args.json else print(
            json.dumps(data, ensure_ascii=False, indent=2)
        )
        return ExitCode.OK if verification.get("ok") else ExitCode.CHECK_FAILED

    if cmd in {"node-role-plan", "node-role-apply"}:
        bundle = load_mobile_bundle(args.bundle)
        token = cfg.remnawave.token()
        if not token or not cfg.remnawave.base_url:
            raise ManagerError("Не настроен Remnawave API")

        client = RemnawaveClient(
            cfg.remnawave.base_url,
            token,
            timeout=cfg.manager.command_timeout_seconds,
        )
        node = client.get_node(args.node_uuid)
        raw_inbounds = client.get_config_profile_inbounds(args.profile_uuid)
        inbounds = {}
        for row in unwrap_list(raw_inbounds, ("inbounds", "response", "data")):
            tag = row.get("tag") or row.get("inboundTag")
            if isinstance(tag, str) and tag:
                inbounds[tag] = row

        role_data = bundle.node_roles.get(args.role)
        if not isinstance(role_data, dict):
            raise ManagerError(f"В bundle нет role={args.role}")
        tags = list(role_data.get("enable_inbounds", []))

        plan = build_assignment_plan(
            node,
            node_uuid=args.node_uuid,
            role=args.role,
            profile_uuid=args.profile_uuid,
            role_tags=tags,
            inbounds_by_tag=inbounds,
        )

        if cmd == "node-role-plan":
            print_json(plan.to_dict()) if args.json else print(
                json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
            )
            return ExitCode.OK

        if not args.yes:
            raise ManagerError("Для node-role-apply добавь --yes")
        if not cfg.deploy.allow_mutations:
            raise ManagerError("deploy.allow_mutations=false")

        before = node
        response = client.update_node(plan.patch_payload)
        after = client.get_node(args.node_uuid)

        txj = TransactionJournal(cfg.deploy.transaction_dir)
        tx = txj.begin(
            "node-role-assignment",
            metadata={
                "node_uuid": args.node_uuid,
                "role": args.role,
                "profile_uuid": args.profile_uuid,
            },
        )
        txj.write_json(tx.path / "before-node.json", before)
        txj.write_json(tx.path / "assignment-plan.json", plan.to_dict())
        txj.write_json(tx.path / "response.json", response)
        txj.write_json(tx.path / "after-node.json", after)
        txj.update_status(tx, "committed")

        data = {
            "transaction": tx.id,
            "plan": plan.to_dict(),
            "response": response,
        }
        print_json(data) if args.json else print(
            json.dumps(data, ensure_ascii=False, indent=2)
        )
        return ExitCode.OK

    if cmd == "mobile-failover":
        store = MobileStateStore(cfg.mobile.state_file)
        paths = store.paths()
        if not paths:
            raise ManagerError("Mobile profile не создан")

        network_kind = NetworkKind(args.network)
        rec = recommend(
            paths,
            store.samples(),
            network_kind=network_kind,
            failure_penalty=cfg.mobile.failure_penalty,
            stale_after_seconds=cfg.mobile.stale_after_seconds,
            prefer_tcp_on_unknown_network=cfg.mobile.prefer_tcp_on_unknown_network,
        )
        decision = decide_failover(
            rec.ordered,
            current_path_id=args.current_path,
            minimum_score_gain=args.minimum_score_gain,
        )
        data = {
            "recommendation": rec.to_dict(),
            "failover": decision.to_dict(),
        }
        print_json(data) if args.json else print(
            json.dumps(data, ensure_ascii=False, indent=2)
        )
        return ExitCode.OK

    if cmd == "watchdog-status":
        state = WatchdogStore(cfg.watchdog.state_file).load()
        print_json(state) if args.json else print(
            json.dumps(state, ensure_ascii=False, indent=2)
        )
        return ExitCode.OK

    if cmd in {"watchdog-once", "watchdog-run"}:
        if cmd == "watchdog-run" and not cfg.watchdog.enabled:
            raise ManagerError("watchdog.enabled=false")
        if cmd == "watchdog-run" and args.iterations < 0:
            raise ManagerError("--iterations должен быть >= 0")

        store = WatchdogStore(cfg.watchdog.state_file)
        completed = 0
        last_data = {}
        while True:
            signals = collect_signals(cfg)
            decision, state = evaluate(signals, store.load(), cfg.watchdog)
            repairs = []
            requested = bool(getattr(args, "repair", False))
            unattended = cmd == "watchdog-run" and cfg.watchdog.unattended_repair
            wants_repair = requested or (cfg.watchdog.auto_repair and unattended)

            if wants_repair and decision.repair_allowed:
                if requested and not getattr(args, "yes", False):
                    raise ManagerError("Для watchdog-once --repair добавь --yes")
                if not cfg.watchdog.auto_repair:
                    raise ManagerError("watchdog.auto_repair=false")
                runner = ShellRunner(
                    logger,
                    timeout=cfg.manager.command_timeout_seconds,
                    dry_run=args.dry_run,
                )
                repairs = restart_services(
                    runner,
                    decision.repair_services,
                    cfg.watchdog.allowed_services,
                    panel_dir=cfg.install.panel_dir,
                )
                state = record_repair(state)

            store.save(state)
            last_data = {
                "decision": decision.to_dict(),
                "signals": [x.to_dict() for x in signals],
                "repairs": repairs,
                "state_file": str(cfg.watchdog.state_file),
            }
            if cmd == "watchdog-once":
                break
            print(json.dumps(last_data, ensure_ascii=False), flush=True)
            completed += 1
            if args.iterations and completed >= args.iterations:
                break
            time.sleep(cfg.watchdog.interval_seconds)

        if cmd == "watchdog-once":
            print_json(last_data) if args.json else print(
                json.dumps(last_data, ensure_ascii=False, indent=2)
            )
        return (
            ExitCode.OK if last_data["decision"]["healthy"] else ExitCode.CHECK_FAILED
        )

    raise ManagerError(f"Неизвестная команда: {cmd}")


def entrypoint() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        load_secrets_environment(cfg.manager.secrets_file)
    except ConfigError as exc:
        print(f"ОШИБКА КОНФИГА: {exc}", file=sys.stderr)
        raise SystemExit(ExitCode.INVALID_CONFIG)

    logger, log_file = setup_logging(cfg.manager.log_dir, debug=args.debug)
    logger.debug("VPN Orchestrator %s start", __version__)

    try:
        if args.command == "web-serve":
            # The read-mostly API is a long-running process and must coexist
            # with administrative CLI commands.
            code = _dispatch(args, cfg, logger)
        elif args.command == "watchdog-run":
            watchdog_lock = cfg.manager.lock_file.with_name(
                cfg.manager.lock_file.name + ".watchdog"
            )
            with ProcessLock(watchdog_lock):
                code = _dispatch(args, cfg, logger)
        else:
            with ProcessLock(cfg.manager.lock_file):
                code = _dispatch(args, cfg, logger)
    except KeyboardInterrupt:
        logger.warning("Операция отменена пользователем")
        print("\nОтменено.")
        code = ExitCode.ERROR
    except LockError as exc:
        logger.error("%s", exc)
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        code = ExitCode.LOCKED
    except ManagerError as exc:
        logger.exception("Ожидаемая ошибка Manager")
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        print(f"Лог: {log_file}", file=sys.stderr)
        code = ExitCode.ERROR
    except Exception as exc:
        logger.exception("Неожиданная ошибка")
        print(f"НЕОЖИДАННАЯ ОШИБКА: {exc}", file=sys.stderr)
        print(f"Лог: {log_file}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        code = ExitCode.ERROR

    raise SystemExit(int(code))
