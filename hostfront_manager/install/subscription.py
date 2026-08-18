from __future__ import annotations

from pathlib import Path

from ..config import AppConfig
from ..errors import ManagerError
from ..shell import ShellRunner
from .common import atomic_write, require_root, validate_domain

SUB_COMPOSE = """services:
  remnawave-subscription-page:
    image: remnawave/subscription-page:latest
    container_name: remnawave-subscription-page
    hostname: remnawave-subscription-page
    restart: always
    env_file:
      - .env
    ports:
      - '127.0.0.1:3010:3010'
    networks:
      - remnawave-network
networks:
  remnawave-network:
    driver: bridge
    external: true
"""


def install_subscription_page(
    cfg: AppConfig,
    runner: ShellRunner,
    *,
    subscription_domain: str,
    api_token: str | None,
    start: bool = True,
) -> Path:
    require_root()
    validate_domain(subscription_domain)
    if not api_token:
        raise ManagerError(
            "Для Subscription Page нужен Remnawave API Token. "
            "Создай его после первого входа в Remnawave Settings → API Tokens."
        )

    sub_dir = cfg.install.panel_dir / "subscription"
    if runner.dry_run:
        runner.logger.info("[DRY-RUN] create Subscription Page in %s", sub_dir)
        return sub_dir

    sub_dir.mkdir(parents=True, exist_ok=True)
    env = "\n".join([
        "APP_PORT=3010",
        "REMNAWAVE_PANEL_URL=http://remnawave:3000",
        f"REMNAWAVE_API_TOKEN={api_token}",
        "CUSTOM_SUB_PREFIX=",
        "CADDY_AUTH_API_TOKEN=",
        "TRUST_PROXY=1",
        "",
    ])
    atomic_write(sub_dir / ".env", env, 0o600)
    atomic_write(sub_dir / "docker-compose.yml", SUB_COMPOSE, 0o644)
    runner.run(["docker", "compose", "-f", str(sub_dir / "docker-compose.yml"), "config", "-q"])
    if start:
        runner.run(
            ["docker", "compose", "-f", str(sub_dir / "docker-compose.yml"), "up", "-d"],
            timeout=max(600, cfg.manager.command_timeout_seconds),
        )
    return sub_dir
