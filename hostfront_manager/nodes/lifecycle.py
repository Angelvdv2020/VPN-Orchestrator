from __future__ import annotations

import copy
from typing import Any

from ..errors import ApiMutationError
from ..remnawave.client import RemnawaveClient
from .models import NodePlan, PlanAction
from .planner import plan_node


def apply_node_plan(
    client: RemnawaveClient,
    desired_payload: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    current = client.get_nodes()
    plan = plan_node(desired_payload, current)

    result: dict[str, Any] = {
        "plan": plan.to_dict(),
        "applied": False,
        "response": None,
    }

    if not apply or plan.action == PlanAction.NOOP:
        return result

    if plan.action == PlanAction.CREATE:
        response = client.create_node(copy.deepcopy(desired_payload))
        result["applied"] = True
        result["response"] = response
        return result

    if plan.action == PlanAction.UPDATE:
        if not plan.current_uuid:
            raise ApiMutationError("Невозможно UPDATE: UUID существующей ноды не найден")

        payload = copy.deepcopy(desired_payload)
        # API PATCH /api/nodes принимает идентификатор вместе с update payload
        # в актуальных версиях; добавляем uuid, если его не указал оператор.
        payload.setdefault("uuid", plan.current_uuid)
        response = client.update_node(payload)
        result["applied"] = True
        result["response"] = response
        return result

    raise ApiMutationError(f"Неподдерживаемое действие плана: {plan.action}")
