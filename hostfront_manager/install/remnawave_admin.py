from __future__ import annotations

import secrets
from pathlib import Path

from ..config import AppConfig
from ..errors import ManagerError
from ..shell import ShellRunner
from .common import atomic_write, require_root, validate_domain


ADMIN_COMPOSE = """services:
  remnawave-admin-db:
    image: postgres:16-alpine
    container_name: remnawave-admin-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - admin-postgres-data:/var/lib/postgresql/data
    networks: [remnawave-network]

  web-backend:
    image: ghcr.io/case211/remnawave-admin-web-backend:latest
    container_name: remnawave-web-backend
    restart: unless-stopped
    env_file: [.env]
    environment:
      WEB_HOST: 0.0.0.0
      WEB_PORT: 8081
      APP_MODE: full
      BACKUP_DIR: /app/backups
      ORCHESTRATOR_API_URL: ${ORCHESTRATOR_API_URL}
      ORCHESTRATOR_API_TOKEN: ${ORCHESTRATOR_API_TOKEN}
    volumes:
      - ./backups:/app/backups
      - ./logs:/app/logs
    networks: [remnawave-network]
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on: [remnawave-admin-db]

  web-frontend:
    image: ghcr.io/case211/remnawave-admin-web-frontend:latest
    container_name: remnawave-web-frontend
    restart: unless-stopped
    env_file: [.env]
    volumes:
      - ./logs:/app/logs
    networks: [remnawave-network]
    depends_on: [web-backend]

volumes:
  admin-postgres-data:
    name: remnawave-admin-postgres-data

networks:
  remnawave-network:
    name: remnawave-network
    external: true
"""


def install_remnawave_admin(
    cfg: AppConfig,
    runner: ShellRunner,
    *,
    admin_domain: str,
    panel_domain: str,
) -> Path:
    """Install the official Remnawave Admin web services without Telegram bot."""
    require_root()
    admin_domain = validate_domain(admin_domain)
    panel_domain = validate_domain(panel_domain)
    api_token = cfg.remnawave.token()
    if not api_token:
        raise ManagerError("REMNAWAVE_TOKEN обязателен для Remnawave Admin")

    admin_dir = cfg.install.panel_dir / "remnawave-admin"
    if runner.dry_run:
        return admin_dir
    admin_dir.mkdir(parents=True, exist_ok=True)
    (admin_dir / "backups").mkdir(exist_ok=True)
    (admin_dir / "logs").mkdir(exist_ok=True)
    db_password = secrets.token_urlsafe(32)
    env = "\n".join(
        [
            "BOT_TOKEN=disabled-no-telegram",
            f"API_BASE_URL=https://{panel_domain}",
            f"API_TOKEN={api_token}",
            "ADMINS=",
            "DEFAULT_LOCALE=ru",
            "LOG_LEVEL=INFO",
            "WEBHOOK_SECRET=" + secrets.token_hex(32),
            "INTERNAL_API_SECRET=" + secrets.token_urlsafe(32),
            "POSTGRES_USER=remnawave",
            f"POSTGRES_PASSWORD={db_password}",
            "POSTGRES_DB=remnawave_admin",
            f"DATABASE_URL=postgresql://remnawave:{db_password}@remnawave-admin-db:5432/remnawave_admin",
            "WEB_SECRET_KEY=" + secrets.token_hex(32),
            "WEB_BACKEND_PORT=8081",
            "WEB_FRONTEND_PORT=3000",
            f"WEB_CORS_ORIGINS=https://{admin_domain}",
            "EXTERNAL_API_ENABLED=false",
            "EXTERNAL_API_DOCS=false",
            "ORCHESTRATOR_API_URL=http://172.18.0.1:8765",
            f"ORCHESTRATOR_API_TOKEN={cfg.web.admin_token() or ''}",
            "\n",
        ]
    )
    atomic_write(admin_dir / ".env", env, 0o600)
    atomic_write(admin_dir / "docker-compose.yml", ADMIN_COMPOSE, 0o644)
    runner.run(["docker", "compose", "-f", str(admin_dir / "docker-compose.yml"), "config", "-q"])
    runner.run(
        ["docker", "compose", "-f", str(admin_dir / "docker-compose.yml"), "up", "-d", "remnawave-admin-db", "web-backend", "web-frontend"],
        timeout=max(900, cfg.manager.command_timeout_seconds),
    )
    return admin_dir
