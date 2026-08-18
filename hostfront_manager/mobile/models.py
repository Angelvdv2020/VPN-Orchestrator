from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class TransportKind(StrEnum):
    REALITY_XHTTP = "reality-xhttp"
    REALITY_RAW = "reality-raw"
    HOST_FRONT = "host-front"
    HYSTERIA2 = "hysteria2"


class NetworkKind(StrEnum):
    UNKNOWN = "unknown"
    MOBILE = "mobile"
    WIFI = "wifi"


class ProbeStatus(StrEnum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class PathCandidate:
    id: str
    name: str
    transport: TransportKind
    host: str
    port: int
    network: str
    enabled: bool = True
    priority: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["transport"] = self.transport.value
        return data


@dataclass(slots=True)
class ProbeSample:
    path_id: str
    status: ProbeStatus
    checked_at: str
    latency_ms: float | None = None
    source: str = "server"
    detail: str = ""
    network_kind: NetworkKind = NetworkKind.UNKNOWN

    @classmethod
    def now(
        cls,
        path_id: str,
        status: ProbeStatus,
        *,
        latency_ms: float | None = None,
        source: str = "server",
        detail: str = "",
        network_kind: NetworkKind = NetworkKind.UNKNOWN,
    ) -> "ProbeSample":
        return cls(
            path_id=path_id,
            status=status,
            checked_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=latency_ms,
            source=source,
            detail=detail,
            network_kind=network_kind,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["network_kind"] = self.network_kind.value
        return d


@dataclass(slots=True)
class PathHealth:
    path: PathCandidate
    score: float
    status: ProbeStatus
    last_latency_ms: float | None
    consecutive_failures: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path.to_dict(),
            "score": round(self.score, 2),
            "status": self.status.value,
            "last_latency_ms": self.last_latency_ms,
            "consecutive_failures": self.consecutive_failures,
            "reason": self.reason,
        }


@dataclass(slots=True)
class Recommendation:
    selected: PathHealth | None
    ordered: list[PathHealth]
    network_kind: NetworkKind
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected.to_dict() if self.selected else None,
            "ordered": [x.to_dict() for x in self.ordered],
            "network_kind": self.network_kind.value,
            "reason": self.reason,
        }
