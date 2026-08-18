from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    OK = 0
    ERROR = 1
    CHECK_FAILED = 2
    INVALID_CONFIG = 3
    LOCKED = 4


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    critical: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "summary": self.summary,
            "details": self.details,
            "critical": self.critical,
        }


@dataclass(slots=True)
class DoctorReport:
    checks: list[CheckResult]

    @property
    def ok(self) -> bool:
        return all(item.ok or not item.critical for item in self.checks)

    @property
    def failed(self) -> list[CheckResult]:
        return [x for x in self.checks if not x.ok]

    def to_dict(self) -> dict[str, Any]:
        passed = sum(1 for x in self.checks if x.ok)
        return {
            "ok": self.ok,
            "passed": passed,
            "failed": len(self.checks) - passed,
            "checks": [x.to_dict() for x in self.checks],
        }
