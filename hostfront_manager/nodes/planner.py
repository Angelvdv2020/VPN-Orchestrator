from __future__ import annotations

from typing import Any

from .models import NodePlan, PlanAction


def _unwrap_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("nodes", "response", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = _unwrap_list(value)
            if nested:
                return nested
    return []


def _node_name(node: dict[str, Any]) -> str | None:
    for key in ("name", "remark", "nodeName"):
        value = node.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _node_uuid(node: dict[str, Any]) -> str | None:
    for key in ("uuid", "id"):
        value = node.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def plan_node(desired_payload: dict[str, Any], current_payload: Any) -> NodePlan:
    desired_name = (
        desired_payload.get("name")
        or desired_payload.get("remark")
        or desired_payload.get("nodeName")
    )
    if not isinstance(desired_name, str) or not desired_name:
        return NodePlan(
            PlanAction.CREATE,
            "<unnamed>",
            "payload не содержит распознаваемого имени; безопасно считаем новой нодой",
            desired_payload=desired_payload,
        )

    nodes = _unwrap_list(current_payload)
    match = next((x for x in nodes if _node_name(x) == desired_name), None)
    if match is None:
        return NodePlan(
            PlanAction.CREATE,
            desired_name,
            "нода с таким именем не найдена",
            desired_payload=desired_payload,
        )

    uuid = _node_uuid(match)

    # Сравниваем только ключи, которые оператор явно задал.
    changed = {}
    for key, value in desired_payload.items():
        if key in {"uuid", "id"}:
            continue
        if match.get(key) != value:
            changed[key] = {"current": match.get(key), "desired": value}

    if not changed:
        return NodePlan(
            PlanAction.NOOP,
            desired_name,
            "текущее состояние соответствует заданному payload",
            current_uuid=uuid,
            desired_payload=desired_payload,
        )

    return NodePlan(
        PlanAction.UPDATE,
        desired_name,
        f"изменений: {len(changed)}",
        current_uuid=uuid,
        desired_payload=desired_payload,
    )
