from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import StrEnum
from typing import Any


class InverseAction(StrEnum):
    DELETE_CREATED = "delete-created"
    RESTORE_UPDATED = "restore-updated"
    NOOP = "noop"


@dataclass(slots=True)
class InverseStep:
    order: int
    kind: str
    action: InverseAction
    uuid: str | None
    name: str
    before: dict[str, Any] | None
    verified_shape: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        return data
