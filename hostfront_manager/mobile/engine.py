from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from .models import (
    NetworkKind,
    PathCandidate,
    PathHealth,
    ProbeSample,
    ProbeStatus,
    Recommendation,
    TransportKind,
)


BASE_TRANSPORT_SCORE = {
    TransportKind.REALITY_XHTTP: 100.0,
    TransportKind.HOST_FRONT: 96.0,
    TransportKind.REALITY_RAW: 92.0,
    TransportKind.HYSTERIA2: 90.0,
}


def _age_seconds(iso: str) -> float:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return 10**9


def evaluate_paths(
    paths: Iterable[PathCandidate],
    samples: Iterable[ProbeSample],
    *,
    network_kind: NetworkKind,
    failure_penalty: int,
    stale_after_seconds: int,
    prefer_tcp_on_unknown_network: bool,
) -> list[PathHealth]:
    by_path: dict[str, list[ProbeSample]] = defaultdict(list)
    for sample in samples:
        by_path[sample.path_id].append(sample)
    for rows in by_path.values():
        rows.sort(key=lambda x: x.checked_at)

    result: list[PathHealth] = []

    for path in paths:
        if not path.enabled:
            result.append(PathHealth(path, -1000, ProbeStatus.UNKNOWN, None, 0, "disabled"))
            continue

        rows = by_path.get(path.id, [])
        latest = rows[-1] if rows else None
        score = BASE_TRANSPORT_SCORE[path.transport] + (path.priority / 100.0)
        reason: list[str] = []
        consecutive_failures = 0

        for row in reversed(rows):
            if row.status == ProbeStatus.DOWN:
                consecutive_failures += 1
            else:
                break

        if latest is None:
            status = ProbeStatus.UNKNOWN
            reason.append("нет измерений")
            score -= 12
        else:
            status = latest.status
            if _age_seconds(latest.checked_at) > stale_after_seconds:
                reason.append("измерение устарело")
                score -= 15
            if latest.status == ProbeStatus.UP:
                score += 20
                reason.append("последняя проверка успешна")
            elif latest.status == ProbeStatus.DOWN:
                score -= 45
                reason.append("последняя проверка неуспешна")
            else:
                score -= 5
                reason.append("доступность не подтверждена полностью")

            if latest.latency_ms is not None:
                # Мягко штрафуем высокую задержку, не превращая latency в главный фактор.
                score -= min(25.0, latest.latency_ms / 40.0)
                reason.append(f"{latest.latency_ms:.0f} ms")

        if consecutive_failures:
            score -= consecutive_failures * failure_penalty
            reason.append(f"ошибок подряд: {consecutive_failures}")

        # Для неизвестной/мобильной сети TCP-пути считаем более предсказуемым fallback.
        if path.network.lower() == "udp":
            if network_kind == NetworkKind.MOBILE:
                # Не баним UDP: если клиент подтвердил UP, он всё равно поднимется наверх.
                score -= 7
                reason.append("UDP на мобильной сети требует подтверждения клиента")
            elif network_kind == NetworkKind.UNKNOWN and prefer_tcp_on_unknown_network:
                score -= 10
                reason.append("сеть неизвестна: TCP имеет небольшой приоритет")
        else:
            if network_kind in {NetworkKind.MOBILE, NetworkKind.UNKNOWN}:
                score += 3

        result.append(
            PathHealth(
                path=path,
                score=score,
                status=status,
                last_latency_ms=latest.latency_ms if latest else None,
                consecutive_failures=consecutive_failures,
                reason="; ".join(reason),
            )
        )

    return sorted(result, key=lambda x: x.score, reverse=True)


def recommend(
    paths: list[PathCandidate],
    samples: list[ProbeSample],
    *,
    network_kind: NetworkKind,
    failure_penalty: int,
    stale_after_seconds: int,
    prefer_tcp_on_unknown_network: bool,
) -> Recommendation:
    ordered = evaluate_paths(
        paths,
        samples,
        network_kind=network_kind,
        failure_penalty=failure_penalty,
        stale_after_seconds=stale_after_seconds,
        prefer_tcp_on_unknown_network=prefer_tcp_on_unknown_network,
    )

    usable = [x for x in ordered if x.status != ProbeStatus.DOWN and x.path.enabled]
    selected = usable[0] if usable else None

    if selected:
        reason = f"выбран {selected.path.name}: score={selected.score:.1f}"
    else:
        reason = "нет подтверждённо пригодного пути"

    return Recommendation(selected, ordered, network_kind, reason)
