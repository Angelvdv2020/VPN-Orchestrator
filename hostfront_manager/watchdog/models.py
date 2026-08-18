from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class HealthSignal:
    name: str
    ok: bool
    summary: str
    repair_service: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WatchdogDecision:
    healthy: bool
    state: str
    failure_streak: int
    recovery_streak: int
    repair_services: list[str]
    repair_allowed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
