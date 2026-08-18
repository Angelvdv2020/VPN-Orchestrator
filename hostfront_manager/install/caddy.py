from __future__ import annotations

from pathlib import Path

from ..config import AppConfig
from ..shell import ShellRunner
from .common import atomic_write, require_root, validate_domain

CADDY_COMPOSE = """services:
  caddy:
    image: caddy:2
    container_name: 'caddy'
    hostname: caddy
    restart: always
    ports:
      - '0.0.0.0:443:443'
      - '0.0.0.0:80:80'
    networks:
      - remnawave-network
    volumes:
      - ./:/etc/caddy:ro
      - caddy-ssl-data:/data
networks:
  remnawave-network:
    name: remnawave-network
    driver: bridge
    external: true
volumes:
  caddy-ssl-data:
    driver: local
    external: false
    name: caddy-ssl-data
"""


def build_caddyfile(panel_domain: str, subscription_domain: str | None = None, admin_domain: str | None = None) -> str:
    panel_domain = validate_domain(panel_domain)
    blocks = [
        f"""https://{panel_domain} {{
    encode
    reverse_proxy * http://remnawave:3000
}}"""
    ]
    if subscription_domain and subscription_domain != panel_domain:
        subscription_domain = validate_domain(subscription_domain)
        blocks.append(
            f"""https://{subscription_domain} {{
    encode
    reverse_proxy * http://remnawave-subscription-page:3010 {{
        header_up X-Forwarded-Host {{host}}
        header_up X-Forwarded-Port {{server_port}}
        header_up X-Real-IP {{remote_host}}
    }}
    handle_errors {{
        respond 404
    }}
}}"""
        )
    if admin_domain and admin_domain not in {panel_domain, subscription_domain}:
        admin_domain = validate_domain(admin_domain)
        blocks.append(f"""https://{admin_domain} {{
    encode
    reverse_proxy * http://remnawave-web-frontend:80
}}""")
    blocks.append(""":443 {
    tls internal
    respond 204
}""")
    return "\n\n".join(blocks) + "\n"


def install_caddy(
    cfg: AppConfig,
    runner: ShellRunner,
    *,
    panel_domain: str,
    subscription_domain: str | None = None,
    admin_domain: str | None = None,
    start: bool = True,
) -> Path:
    require_root()
    caddy_dir = cfg.install.panel_dir / "caddy"
    if runner.dry_run:
        runner.logger.info("[DRY-RUN] create Caddy config in %s", caddy_dir)
        return caddy_dir

    caddy_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(caddy_dir / "Caddyfile", build_caddyfile(panel_domain, subscription_domain, admin_domain), 0o644)
    atomic_write(caddy_dir / "docker-compose.yml", CADDY_COMPOSE, 0o644)
    runner.run(["docker", "compose", "-f", str(caddy_dir / "docker-compose.yml"), "config", "-q"])
    if start:
        runner.run(
            ["docker", "compose", "-f", str(caddy_dir / "docker-compose.yml"), "up", "-d"],
            timeout=max(600, cfg.manager.command_timeout_seconds),
        )
        runner.run(
            ["docker", "exec", "caddy", "caddy", "reload", "--config", "/etc/caddy/Caddyfile"],
            timeout=max(60, cfg.manager.command_timeout_seconds),
        )
    return caddy_dir
