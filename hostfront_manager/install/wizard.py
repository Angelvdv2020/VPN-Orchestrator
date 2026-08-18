from __future__ import annotations

from dataclasses import dataclass

from ..config import AppConfig
from ..shell import ShellRunner
from .caddy import install_caddy
from .common import resolve_domain, validate_domain
from .panel import install_panel
from .remnawave_admin import install_remnawave_admin
from .subscription import install_subscription_page


@dataclass(slots=True)
class InstallPlan:
    panel_domain: str
    subscription_domain: str
    install_subscription: bool
    admin_domain: str | None = None


def interactive_plan() -> InstallPlan:
    print("=== ORCHESTRATOR — первоначальная установка ===")
    panel = validate_domain(input("Домен панели (panel.example.com): "))
    sub_raw = input("Домен страницы подписки (sub.example.com): ").strip()
    sub = validate_domain(sub_raw) if sub_raw else panel
    install_sub = input("Ставить Subscription Page сейчас? [y/N]: ").strip().lower() in {"y", "yes", "д", "да"}
    return InstallPlan(panel, sub, install_sub)


def install_all(cfg: AppConfig, runner: ShellRunner, plan: InstallPlan) -> dict:
    panel_ips = resolve_domain(plan.panel_domain)
    sub_ips = resolve_domain(plan.subscription_domain)

    if not panel_ips:
        runner.logger.warning("DNS панели пока не резолвится: %s", plan.panel_domain)
    if plan.subscription_domain != plan.panel_domain and not sub_ips:
        runner.logger.warning("DNS Subscription Page пока не резолвится: %s", plan.subscription_domain)

    panel = install_panel(
        cfg,
        runner,
        panel_domain=plan.panel_domain,
        subscription_domain=plan.subscription_domain,
    )

    subscription_status = "skipped"
    token = cfg.remnawave.token()
    admin_dir = None
    if plan.admin_domain and token:
        admin_dir = install_remnawave_admin(
            cfg, runner, admin_domain=plan.admin_domain, panel_domain=plan.panel_domain
        )

    if plan.install_subscription and token:
        install_subscription_page(
            cfg,
            runner,
            subscription_domain=plan.subscription_domain,
            api_token=token,
        )
        subscription_status = "installed"
    elif plan.install_subscription:
        subscription_status = "waiting_for_api_token"
        runner.logger.warning("Subscription Page отложена: нет %s", cfg.remnawave.token_env)

    install_caddy(
        cfg,
        runner,
        panel_domain=plan.panel_domain,
        subscription_domain=plan.subscription_domain if subscription_status == "installed" else None,
        admin_domain=plan.admin_domain,
    )

    return {
        "panel": {
            "panel_dir": panel.panel_dir,
            "panel_domain": panel.panel_domain,
            "subscription_domain": panel.subscription_domain,
            "created": panel.created,
            "admin_dir": admin_dir,
        },
        "subscription": subscription_status,
        "dns": {"panel": panel_ips, "subscription": sub_ips},
    }
