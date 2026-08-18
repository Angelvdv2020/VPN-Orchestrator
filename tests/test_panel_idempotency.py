from hostfront_manager.config import AppConfig
from hostfront_manager.install import panel


class FakeRunner:
    dry_run = False

    class Logger:
        def info(self, *args):
            pass

    logger = Logger()

    def run(self, argv, **kwargs):
        class Result:
            returncode = 0

        return Result()


def test_existing_env_secrets_are_not_rotated(tmp_path, monkeypatch):
    cfg = AppConfig()
    cfg.install.panel_dir = tmp_path
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    original = (
        "APP_SECRET=keep\nJWT_AUTH_SECRET=keep-auth\nJWT_API_TOKENS_SECRET=keep-api\n"
        "METRICS_PASS=keep-metrics\nWEBHOOK_SECRET_HEADER=keep-hook\n"
        'POSTGRES_PASSWORD=keep-db\nDATABASE_URL="postgresql://postgres:keep-db@remnawave-db:5432/postgres"\n'
    )
    (tmp_path / ".env").write_text(original)
    monkeypatch.setattr(panel, "ensure_docker", lambda runner: None)
    panel.install_panel(
        cfg,
        FakeRunner(),
        panel_domain="panel.example.com",
        subscription_domain="sub.example.com",
        start=False,
    )
    current = (tmp_path / ".env").read_text()
    for value in (
        "keep",
        "keep-auth",
        "keep-api",
        "keep-metrics",
        "keep-hook",
        "keep-db",
    ):
        assert value in current
