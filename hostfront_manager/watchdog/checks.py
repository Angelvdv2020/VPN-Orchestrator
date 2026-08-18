from __future__ import annotations

from ..config import AppConfig
from ..diagnostics import run_doctor
from ..remnawave.client import RemnawaveClient
from .models import HealthSignal


def collect_signals(cfg: AppConfig) -> list[HealthSignal]:
    report = run_doctor(cfg)
    signals = [
        HealthSignal(
            name=x.name, ok=x.ok or not x.critical, summary=x.summary,
            repair_service="docker" if x.name == "docker" and not x.ok else None,
            details=x.details,
        )
        for x in report.checks
    ]
    token = cfg.remnawave.token()
    if cfg.remnawave.enabled and cfg.remnawave.base_url and token:
        try:
            client = RemnawaveClient(cfg.remnawave.base_url, token, cfg.manager.command_timeout_seconds)
            payload = client.get_system_health()
            signals.append(HealthSignal("remnawave:api", True, "API health доступен", details={"response": payload}))
        except Exception as exc:
            signals.append(HealthSignal("remnawave:api", False, str(exc), repair_service="remnawave"))
    return signals
