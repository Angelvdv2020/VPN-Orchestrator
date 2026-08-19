from __future__ import annotations

import sqlite3
import time
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Annotated, Literal

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
from .registry import load_registry, save_registry


class TelemetryInput(BaseModel):
    observed_at: int
    path_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    status: Literal["up", "down", "unknown"]
    network: Literal["mobile", "wifi", "unknown"] = "mobile"
    operator: str = Field(default="", max_length=80)
    country: str = Field(default="", max_length=2, pattern=r"^$|^[A-Z]{2}$")
    latency_ms: float | None = Field(default=None, ge=0, le=120000)
    detail: str = Field(default="", max_length=500)


class RegistryInput(BaseModel):
    mode: Literal["manager-owned", "safe-attach"] = "manager-owned"
    locations: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


def _items(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    """Unwrap the several list envelopes used by Remnawave API versions."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = _items(value, keys)
            if nested:
                return nested
    response = payload.get("response")
    if response is not None and response is not payload:
        return _items(response, keys)
    return []


def _host_transport(host: dict[str, Any], inbound: dict[str, Any] | None = None) -> str:
    value = " ".join(
        str(host.get(key, ""))
        for key in ("remark", "name", "address", "path", "securityLayer")
    ).lower()
    source = inbound or {}
    network = str(host.get("network") or source.get("network") or "").lower()
    security = str(host.get("security") or source.get("security") or "").lower()
    if "hysteria" in value or network == "hysteria":
        return "Hysteria2"
    if "host-front" in value or "host front" in value:
        return "HOST-FRONT"
    if "xhttp" in value or network in {"xhttp", "splithttp"}:
        return "XHTTP + " + ("REALITY" if security == "reality" else "TLS")
    return "RAW + " + ("REALITY" if security == "reality" else "TLS")


def _guess_location(text: str) -> tuple[str, str, str]:
    lowered = text.lower()
    guesses = (
        (r"france|франц", "FR", "🇫🇷", "Франция"),
        (r"latvia|латв", "LV", "🇱🇻", "Латвия"),
        (r"russia|росс|ru[- _]?ingress|вход", "RU", "🇷🇺", "Россия"),
    )
    for pattern, country, flag, name in guesses:
        if re.search(pattern, lowered):
            return country, flag, name
    return "", "◈", "Без локации"


def _orchestrator_overview(client: RemnawaveClient, cfg: AppConfig) -> dict[str, Any]:
    payloads = {
        "nodes": client.get_nodes(),
        "hosts": client.get_hosts(),
        "profiles": client.get_config_profiles(),
        "squads": client.get_internal_squads(),
        "users": client.get_users(),
    }
    nodes = _items(payloads["nodes"], ("nodes",))
    hosts = _items(payloads["hosts"], ("hosts",))
    profiles = _items(payloads["profiles"], ("configProfiles", "config_profiles"))
    squads = _items(payloads["squads"], ("internalSquads", "internal_squads"))
    users = _items(payloads["users"], ("users",))
    inbound_index: dict[str, dict[str, Any]] = {}
    profile_index = {str(x.get("uuid")): x for x in profiles if x.get("uuid")}
    for profile in profiles:
        for inbound in _items(profile.get("inbounds"), ("inbounds",)):
            if inbound.get("uuid"):
                inbound_index[str(inbound["uuid"])] = {
                    **inbound,
                    "profile_uuid": profile.get("uuid"),
                    "profile_name": profile.get("name"),
                }
    host_rows: list[dict[str, Any]] = []
    for host in hosts:
        binding = host.get("inbound") if isinstance(host.get("inbound"), dict) else {}
        inbound_uuid = binding.get("configProfileInboundUuid") or host.get("inboundUuid")
        inbound = inbound_index.get(str(inbound_uuid), {})
        profile_uuid = binding.get("configProfileUuid") or inbound.get("profile_uuid")
        host_rows.append(
            {
                "uuid": host.get("uuid"),
                "remark": host.get("remark") or host.get("name"),
                "address": host.get("address"),
                "port": host.get("port"),
                "path": host.get("path"),
                "sni": host.get("sni"),
                "profile_uuid": profile_uuid,
                "profile_name": profile_index.get(str(profile_uuid), {}).get("name")
                or inbound.get("profile_name"),
                "inbound_uuid": inbound_uuid,
                "inbound_tag": inbound.get("tag"),
                "network": host.get("network") or inbound.get("network"),
                "security": host.get("security") or inbound.get("security"),
                "transport": _host_transport(host, inbound),
                "disabled": bool(host.get("isDisabled", host.get("disabled", False))),
            }
        )
    registry = load_registry(cfg.manager.data_dir)
    locations = registry.get("locations", [])
    if not locations:
        # Keep a useful first view even before the operator fills the registry.
        # These are read-only inferred cards, never persisted as live objects.
        for profile in profiles:
            profile_uuid = profile.get("uuid")
            profile_hosts = [x for x in host_rows if x.get("profile_uuid") == profile_uuid]
            text = " ".join(
                [str(profile.get("name", ""))]
                + [str(x.get("remark", "")) for x in profile_hosts]
            )
            country, flag, name = _guess_location(text)
            locations.append(
                {
                    "id": f"auto-{profile_uuid or len(locations)}",
                    "name": profile.get("name") or name,
                    "country": country,
                    "flag": flag,
                    "profile_uuid": profile_uuid,
                    "node_uuid": "",
                    "squad_uuid": "",
                    "hosts": profile_hosts,
                    "auto": True,
                }
            )
    location_by_resource: dict[str, dict[str, Any]] = {}
    for location in locations:
        if not isinstance(location, dict):
            continue
        for key in ("profile_uuid", "node_uuid", "squad_uuid"):
            if location.get(key):
                location_by_resource[str(location[key])] = location
    for row in host_rows:
        location = location_by_resource.get(str(row.get("profile_uuid")))
        row["location"] = location.get("name") if location else "Без локации"
        row["flag"] = location.get("flag", "") if location else ""
    diagnostics = []
    for row in host_rows:
        diagnostics.append(
            {
                "host_uuid": row.get("uuid"),
                "name": row.get("remark") or row.get("uuid"),
                "transport": row.get("transport"),
                "location": row.get("location"),
                "ok": bool(row.get("profile_uuid") and row.get("inbound_uuid")),
                "reason": "binding ok"
                if row.get("profile_uuid") and row.get("inbound_uuid")
                else "host is not bound to a profile inbound",
            }
        )
    return {
        "registry": registry,
        "mode": registry.get("mode", "manager-owned"),
        "locations": locations,
        "nodes": nodes,
        "hosts": host_rows,
        "profiles": profiles,
        "squads": squads,
        "users": users,
        "diagnostics": diagnostics,
        "counts": {
            "nodes": len(nodes),
            "hosts": len(host_rows),
            "profiles": len(profiles),
            "squads": len(squads),
            "users": len(users),
        },
    }


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

    @app.get("/api/v1/orchestrator/overview", dependencies=[Depends(require_admin)])
    def orchestrator_overview():
        """Return one normalized view for the location/transport admin screen."""
        try:
            return _orchestrator_overview(remnawave_client(), cfg)
        except ManagerError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/api/v1/orchestrator/registry", dependencies=[Depends(require_admin)])
    def orchestrator_registry():
        return load_registry(cfg.manager.data_dir)

    @app.put("/api/v1/orchestrator/registry", dependencies=[Depends(require_admin)])
    def update_orchestrator_registry(payload: RegistryInput):
        """Persist only UI metadata; live Remnawave objects are never changed here."""
        value = payload.model_dump()
        value["updated_at"] = datetime.now(UTC).isoformat()
        try:
            return save_registry(cfg.manager.data_dir, value)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/orchestrator/transport-health", dependencies=[Depends(require_admin)])
    def orchestrator_transport_health():
        try:
            overview = _orchestrator_overview(remnawave_client(), cfg)
        except ManagerError as exc:
            raise HTTPException(502, str(exc)) from exc
        samples: dict[str, dict[str, Any]] = {}
        for row in store.summary(int(time.time()) - 24 * 3600):
            key = str(row.get("path_id", ""))
            aggregate = samples.setdefault(key, {"up": 0, "down": 0, "unknown": 0})
            status = str(row.get("status", "unknown"))
            aggregate[status] = aggregate.get(status, 0) + int(row.get("samples", 0))
            aggregate["last_seen"] = max(aggregate.get("last_seen", 0), int(row.get("last_seen", 0)))
        result = []
        for row in overview["diagnostics"]:
            host_uuid = str(row.get("host_uuid") or "")
            sample = samples.get(host_uuid) or samples.get(str(row.get("name")))
            result.append(
                {
                    **row,
                    "telemetry": sample,
                    "state": "up"
                    if sample and sample.get("up", 0) > sample.get("down", 0)
                    else "unknown",
                }
            )
        return {"items": result, "window_hours": 24}

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
