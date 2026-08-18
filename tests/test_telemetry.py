import json
import time

from fastapi.testclient import TestClient

from hostfront_manager.config import AppConfig
from hostfront_manager.telemetry.auth import device_env_name, sign, verify
from hostfront_manager.telemetry.store import TelemetryStore
from hostfront_manager.web.app import create_app


def test_signature_and_clock():
    body = b'{"ok":true}'
    signature = sign("secret", "1000", "abcdefghijklmnop", body)
    verify("secret", "1000", "abcdefghijklmnop", body, signature, max_skew=10, now=1005)


def test_store_summary_and_replay(tmp_path):
    store = TelemetryStore(tmp_path / "telemetry.db")
    payload = {
        "observed_at": 100,
        "path_id": "reality-xhttp",
        "status": "up",
        "network": "mobile",
        "latency_ms": 42,
    }
    store.add("phone-1", "abcdefghijklmnop", payload, received_at=100)
    assert store.recent()[0]["path_id"] == "reality-xhttp"
    assert store.summary(0)[0]["samples"] == 1


def test_api_auth_replay_and_admin(tmp_path, monkeypatch):
    cfg = AppConfig()
    cfg.web.telemetry_db = tmp_path / "telemetry.db"
    cfg.watchdog.state_file = tmp_path / "watchdog.json"
    cfg.mobile.state_file = tmp_path / "mobile.json"
    monkeypatch.setenv(
        device_env_name(cfg.web.telemetry_key_prefix, "phone-1"), "device-secret"
    )
    monkeypatch.setenv(cfg.web.admin_token_env, "admin-secret")
    client = TestClient(create_app(cfg))
    now = str(int(time.time()))
    nonce = "abcdefghijklmnop"
    payload = {
        "observed_at": int(now),
        "path_id": "reality-xhttp",
        "status": "up",
        "network": "mobile",
        "operator": "test",
        "country": "RU",
        "latency_ms": 55,
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {
        "X-Device-ID": "phone-1",
        "X-Timestamp": now,
        "X-Nonce": nonce,
        "X-Signature": sign("device-secret", now, nonce, body),
        "Content-Type": "application/json",
    }
    response = client.post("/api/v1/telemetry", content=body, headers=headers)
    assert response.status_code == 202
    assert (
        client.post("/api/v1/telemetry", content=body, headers=headers).status_code
        == 409
    )
    assert client.get("/api/v1/status").status_code == 401
    assert (
        client.get(
            "/api/v1/status", headers={"Authorization": "Bearer admin-secret"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/telemetry",
            content=b"x",
            headers={"Content-Length": "65537"},
        ).status_code
        == 413
    )


def test_chunked_telemetry_body_limit(tmp_path):
    cfg = AppConfig()
    cfg.web.telemetry_db = tmp_path / "telemetry.db"
    client = TestClient(create_app(cfg))

    def chunks():
        yield b"x" * 40000
        yield b"y" * 40000

    response = client.post(
        "/api/v1/telemetry",
        content=chunks(),
        headers={
            "X-Device-ID": "phone-1",
            "X-Timestamp": "1",
            "X-Nonce": "abcdefghijklmnop",
            "X-Signature": "invalid",
        },
    )
    assert response.status_code == 413
