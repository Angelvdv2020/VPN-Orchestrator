from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..config import WatchdogSection
from .models import HealthSignal, WatchdogDecision


def utc_timestamp() -> float:
    return datetime.now(timezone.utc).timestamp()


def evaluate(
    signals: list[HealthSignal],
    state: dict[str, Any],
    cfg: WatchdogSection,
    *,
    now: float | None = None,
) -> tuple[WatchdogDecision, dict[str, Any]]:
    now = utc_timestamp() if now is None else now
    healthy = all(x.ok for x in signals)
    failures = 0 if healthy else int(state.get("failure_streak", 0)) + 1
    recoveries = int(state.get("recovery_streak", 0)) + 1 if healthy else 0
    previous = str(state.get("state", "unknown"))

    current = previous
    if not healthy and failures >= cfg.failure_threshold:
        current = "unhealthy"
    elif healthy and (previous != "unhealthy" or recoveries >= cfg.recovery_threshold):
        current = "healthy"

    cutoff = now - cfg.repair_window_seconds
    history = [float(x) for x in state.get("repair_timestamps", []) if float(x) >= cutoff]
    last = state.get("last_repair_at")
    cooldown_ok = last is None or now - float(last) >= cfg.cooldown_seconds
    budget_ok = len(history) < cfg.max_repairs_per_window
    services = sorted({x.repair_service for x in signals if not x.ok and x.repair_service})
    threshold_met = current == "unhealthy"
    repair_allowed = bool(services and threshold_met and cooldown_ok and budget_ok)

    if not threshold_met:
        reason = "failure threshold not reached" if not healthy else "healthy"
    elif not services:
        reason = "no safe repair action mapped"
    elif not cooldown_ok:
        reason = "repair cooldown active"
    elif not budget_ok:
        reason = "repair-loop protection blocked the action"
    else:
        reason = "repair may run"

    updated = dict(state)
    updated.update({
        "state": current,
        "failure_streak": failures,
        "recovery_streak": recoveries,
        "repair_timestamps": history,
        "last_check_at": now,
        "last_signals": [x.to_dict() for x in signals],
    })
    return WatchdogDecision(
        healthy=healthy, state=current, failure_streak=failures,
        recovery_streak=recoveries, repair_services=services,
        repair_allowed=repair_allowed, reason=reason,
    ), updated


def record_repair(state: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    now = utc_timestamp() if now is None else now
    updated = dict(state)
    updated["last_repair_at"] = now
    updated["repair_timestamps"] = [*state.get("repair_timestamps", []), now]
    return updated
