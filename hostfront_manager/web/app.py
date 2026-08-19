from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..backup import list_backups
from ..config import AppConfig
from ..errors import ManagerError
from ..mobile.engine import recommend
from ..mobile.models import NetworkKind, ProbeSample, ProbeStatus
from ..mobile.store import MobileStateStore
from ..remnawave.client import RemnawaveClient
from ..remnawave.inventory import fetch_inventory
from ..telemetry.auth import device_secret, verify
from ..telemetry.store import TelemetryStore
from ..watchdog.checks import collect_signals
from ..watchdog.store import WatchdogStore


class TelemetryInput(BaseModel):
    observed_at: int
    path_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    status: Literal["up", "down", "unknown"]
    network: Literal["mobile", "wifi", "unknown"] = "mobile"
    operator: str = Field(default="", max_length=80)
    country: str = Field(default="", max_length=2, pattern=r"^$|^[A-Z]{2}$")
    latency_ms: float | None = Field(default=None, ge=0, le=120000)
    detail: str = Field(default="", max_length=500)


def create_app(cfg: AppConfig) -> FastAPI:
    app = FastAPI(
        title="ORCHESTRATOR", version=__version__, docs_url=None, redoc_url=None
    )
    store = TelemetryStore(cfg.web.telemetry_db)

    def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = cfg.web.admin_token()
        if not expected:
            raise HTTPException(503, "Admin API token is not configured")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Bearer token required")
        import hmac

        if not hmac.compare_digest(authorization[7:], expected):
            raise HTTPException(403, "Invalid admin token")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > 65536:
                    return JSONResponse(
                        {"detail": "Request body too large"}, status_code=413
                    )
            except ValueError:
                return JSONResponse(
                    {"detail": "Invalid Content-Length"}, status_code=400
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'"
        )
        return response

    @app.get("/livez")
    def livez():
        return {"ok": True, "version": __version__}

    @app.get("/readyz")
    def readyz():
        try:
            store.connect()
            cfg.mobile.state_file.parent.mkdir(parents=True, exist_ok=True)
            return {"ok": True, "version": __version__}
        except (OSError, sqlite3.Error) as exc:
            return JSONResponse(
                {"ok": False, "version": __version__, "error": str(exc)},
                status_code=503,
            )

    @app.get("/healthz")
    def healthz():
        return readyz()

    @app.post("/api/v1/telemetry", status_code=202)
    async def telemetry(
        request: Request,
        x_device_id: Annotated[str, Header()],
        x_timestamp: Annotated[str, Header()],
        x_nonce: Annotated[str, Header()],
        x_signature: Annotated[str, Header()],
    ):
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 65536:
                raise HTTPException(413, "Request body too large")
            chunks.append(chunk)
        body = b"".join(chunks)
        secret = device_secret(cfg.web.telemetry_key_prefix, x_device_id)
        if not secret:
            raise HTTPException(401, "Unknown telemetry device")
        try:
            verify(
                secret,
                x_timestamp,
                x_nonce,
                body,
                x_signature,
                max_skew=cfg.web.telemetry_max_clock_skew_seconds,
            )
            payload = TelemetryInput.model_validate_json(body)
            row_id = store.add(x_device_id, x_nonce, payload.model_dump())
            store.prune_if_due(
                int(time.time()) - cfg.web.telemetry_retention_days * 86400
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Telemetry nonce already used")
        except ManagerError as exc:
            raise HTTPException(401, str(exc))
        except ValueError as exc:
            raise HTTPException(422, "Invalid telemetry payload") from exc
        return {"accepted": True, "id": row_id}

    @app.get("/api/v1/status", dependencies=[Depends(require_admin)])
    def status():
        return {
            "version": __version__,
            "watchdog": WatchdogStore(cfg.watchdog.state_file).load(),
            "telemetry_db": str(cfg.web.telemetry_db),
        }

    @app.get("/api/v1/checks", dependencies=[Depends(require_admin)])
    def checks():
        signals = collect_signals(cfg)
        return {
            "ok": all(x.ok for x in signals),
            "signals": [x.to_dict() for x in signals],
        }

    @app.get("/api/v1/inventory", dependencies=[Depends(require_admin)])
    def inventory():
        token = cfg.remnawave.token()
        if not token or not cfg.remnawave.base_url:
            raise HTTPException(503, "Remnawave API is not configured")
        try:
            summary, _ = fetch_inventory(
                RemnawaveClient(
                    cfg.remnawave.base_url, token, cfg.manager.command_timeout_seconds
                )
            )
        except ManagerError as exc:
            raise HTTPException(502, str(exc))
        return summary.to_dict()

    def remnawave_client() -> RemnawaveClient:
        token = cfg.remnawave.token()
        if not token or not cfg.remnawave.base_url:
            raise HTTPException(503, "Remnawave API is not configured")
        return RemnawaveClient(
            cfg.remnawave.base_url, token, cfg.manager.command_timeout_seconds
        )

    @app.get("/api/v1/resources/{kind}", dependencies=[Depends(require_admin)])
    def resources(kind: Literal["nodes", "hosts", "profiles", "squads", "users"]):
        """Return live Remnawave resources for the ORCHESTRATOR inventory views."""
        client = remnawave_client()
        getters = {
            "nodes": client.get_nodes,
            "hosts": client.get_hosts,
            "profiles": client.get_config_profiles,
            "squads": client.get_internal_squads,
            "users": client.get_users,
        }
        try:
            return {"kind": kind, "items": getters[kind]()}
        except ManagerError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/api/v1/system", dependencies=[Depends(require_admin)])
    def system():
        client = remnawave_client()
        calls = {
            "health": client.get_system_health,
            "metadata": client.get_system_metadata,
            "stats": client.get_system_stats_recap,
        }
        result: dict[str, object] = {}
        for name, call in calls.items():
            try:
                result[name] = call()
            except ManagerError as exc:
                result[name] = {"ok": False, "error": str(exc)}
        return result

    @app.get("/api/v1/backups", dependencies=[Depends(require_admin)])
    def backups():
        return {
            "items": [
                {"name": path.name, "path": str(path), "size": path.stat().st_size}
                for path in list_backups(cfg)
                if path.is_file()
            ]
        }

    @app.get("/api/v1/telemetry/recent", dependencies=[Depends(require_admin)])
    def recent(limit: int = Query(100, ge=1, le=1000)):
        return {"items": store.recent(limit)}

    @app.get("/api/v1/telemetry/summary", dependencies=[Depends(require_admin)])
    def summary(hours: int = Query(24, ge=1, le=24 * 31)):
        return {"hours": hours, "items": store.summary(int(time.time()) - hours * 3600)}

    @app.get("/api/v1/mobile/recommendation", dependencies=[Depends(require_admin)])
    def mobile_recommendation(network: Literal["mobile", "wifi", "unknown"] = "mobile"):
        mobile_store = MobileStateStore(cfg.mobile.state_file)
        paths = mobile_store.paths()
        if not paths:
            raise HTTPException(409, "Mobile profile is not initialized")
        result = recommend(
            paths,
            [
                ProbeSample(
                    path_id=row["path_id"],
                    status=ProbeStatus(row["status"]),
                    checked_at=datetime.fromtimestamp(
                        row["received_at"], UTC
                    ).isoformat(),
                    latency_ms=row["latency_ms"],
                    source=f"telemetry:{row['device_id']}",
                    detail=row["detail"],
                    network_kind=NetworkKind(row["network"]),
                )
                for row in store.samples()
            ],
            network_kind=NetworkKind(network),
            failure_penalty=cfg.mobile.failure_penalty,
            stale_after_seconds=cfg.mobile.stale_after_seconds,
            prefer_tcp_on_unknown_network=cfg.mobile.prefer_tcp_on_unknown_network,
        )
        return result.to_dict()

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        path = Path(__file__).with_name("dashboard.html")
        return HTMLResponse(path.read_text(encoding="utf-8"))

    @app.get("/assets/vpn-orchestrator-logo.png")
    def logo():
        return FileResponse(Path(__file__).with_name("assets") / "vpn-orchestrator-logo.png")

    @app.get("/favicon.png")
    def favicon():
        return FileResponse(Path(__file__).with_name("assets") / "favicon.png")

    return app
