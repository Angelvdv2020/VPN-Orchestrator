from hostfront_manager.install.caddy import CADDY_COMPOSE, build_caddyfile
from hostfront_manager.install.common import replace_env_value, replace_database_password


def test_caddyfile():
    text = build_caddyfile("panel.example.com", "sub.example.com")
    assert "https://panel.example.com" in text
    assert "https://sub.example.com" in text
    assert "remnawave:3000" in text
    assert "X-Forwarded-Host" in text


def test_env_replace():
    text = 'APP_SECRET=old\nPOSTGRES_PASSWORD=old\nDATABASE_URL="postgresql://postgres:old@db:5432/db"\n'
    text = replace_env_value(text, "APP_SECRET", "new")
    text = replace_database_password(text, "pass123")
    assert "APP_SECRET=new" in text
    assert "POSTGRES_PASSWORD=pass123" in text
    assert "postgres:pass123@db" in text


def test_caddy_tracks_stable_major():
    assert "image: caddy:2\n" in CADDY_COMPOSE
