from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .models import PathHealth, ProbeStatus


@dataclass(slots=True)
class FailoverDecision:
    switch: bool
    current_path_id: str | None
    target_path_id: str | None
    reason: str
    score_delta: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_failover(
    ordered: list[PathHealth],
    *,
    current_path_id: str | None,
    minimum_score_gain: float = 15.0,
) -> FailoverDecision:
    usable = [x for x in ordered if x.path.enabled and x.status != ProbeStatus.DOWN]
    if not usable:
        return FailoverDecision(
            False,
            current_path_id,
            None,
            "нет пригодного пути",
            0.0,
        )

    best = usable[0]
    if not current_path_id:
        return FailoverDecision(
            True,
            None,
            best.path.id,
            "текущий путь не задан",
            best.score,
        )

    current = next((x for x in ordered if x.path.id == current_path_id), None)
    if current is None:
        return FailoverDecision(
            True,
            current_path_id,
            best.path.id,
            "текущий путь отсутствует в профиле",
            best.score,
        )

    if current.status == ProbeStatus.DOWN:
        return FailoverDecision(
            True,
            current_path_id,
            best.path.id,
            "текущий путь DOWN",
            best.score - current.score,
        )

    delta = best.score - current.score
    if best.path.id != current.path.id and delta >= minimum_score_gain:
        return FailoverDecision(
            True,
            current_path_id,
            best.path.id,
            f"альтернативный путь лучше минимум на {minimum_score_gain:.0f} score",
            delta,
        )

    return FailoverDecision(
        False,
        current_path_id,
        current_path_id,
        "переключение не требуется",
        delta,
    )
