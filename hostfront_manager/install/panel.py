from __future__ import annotations

from dataclasses import dataclass

from ..config import AppConfig
from ..shell import ShellRunner
from .common import (
    atomic_write,
    ensure_docker,
    replace_database_password,
    replace_env_value,
    require_root,
    token_hex,
    validate_domain,
)

COMPOSE_URL = "https://raw.githubusercontent.com/remnawave/backend/refs/heads/main/docker-compose-prod.yml"
ENV_URL = "https://raw.githubusercontent.com/remnawave/backend/refs/heads/main/.env.sample"


@dataclass(slots=True)
class PanelInstallResult:
    panel_dir: str
    panel_domain: str
    subscription_domain: str
    created: list[str]


def install_panel(
    cfg: AppConfig,
    runner: ShellRunner,
    *,
    panel_domain: str,
    subscription_domain: str | None = None,
    start: bool = True,
) -> PanelInstallResult:
    require_root()
    panel_domain = validate_domain(panel_domain)
    subscription_domain = validate_domain(subscription_domain) if subscription_domain else panel_domain
    ensure_docker(runner)

    base = cfg.install.panel_dir
    created: list[str] = []

    if runner.dry_run:
        runner.logger.info("[DRY-RUN] mkdir -p %s", base)
        runner.logger.info("[DRY-RUN] download official Remnawave compose/.env")
        return PanelInstallResult(str(base), panel_domain, subscription_domain, created)

    base.mkdir(parents=True, exist_ok=True)
    compose = base / "docker-compose.yml"
    env_file = base / ".env"
    env_is_new = not env_file.exists()

    if not compose.exists():
        runner.run(["curl", "-fL", COMPOSE_URL, "-o", str(compose)])
        created.append(str(compose))
    if not env_file.exists():
        runner.run(["curl", "-fL", ENV_URL, "-o", str(env_file)])
        created.append(str(env_file))

    text = env_file.read_text(encoding="utf-8")
    # Secrets are generated exactly once. Re-running install must never rotate
    # credentials behind an already initialized PostgreSQL volume.
    if env_is_new:
        text = replace_env_value(text, "APP_SECRET", token_hex(64))
        text = replace_env_value(text, "JWT_AUTH_SECRET", token_hex(64))
        text = replace_env_value(text, "JWT_API_TOKENS_SECRET", token_hex(64))
        text = replace_env_value(text, "METRICS_PASS", token_hex(64))
        text = replace_env_value(text, "WEBHOOK_SECRET_HEADER", token_hex(64))
        text = replace_database_password(text, token_hex(24))
    text = replace_env_value(text, "FRONT_END_DOMAIN", panel_domain)
    sub_public = subscription_domain if subscription_domain != panel_domain else f"{panel_domain}/api/sub"
    text = replace_env_value(text, "SUB_PUBLIC_DOMAIN", sub_public)
    text = replace_env_value(text, "PANEL_DOMAIN", panel_domain)
    atomic_write(env_file, text, 0o600)

    runner.run(["docker", "compose", "-f", str(compose), "config", "-q"])
    if start:
        runner.run(
            ["docker", "compose", "-f", str(compose), "up", "-d"],
            timeout=max(600, cfg.manager.command_timeout_seconds),
        )

    return PanelInstallResult(str(base), panel_domain, subscription_domain, created)
