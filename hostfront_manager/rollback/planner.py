from __future__ import annotations

from typing import Any

from ..remnawave.shape import find_by_name, first_uuid
from .models import InverseAction, InverseStep


KINDS = {
    "config-profile": (
        "config_profiles",
        ("configProfiles", "config_profiles", "response", "data"),
    ),
    "host": (
        "hosts",
        ("hosts", "response", "data"),
    ),
    "internal-squad": (
        "internal_squads",
        ("internalSquads", "internal_squads", "response", "data"),
    ),
}


def build_inverse_plan(
    before_snapshot: dict[str, Any],
    applied: dict[str, Any],
) -> list[InverseStep]:
    results = list(applied.get("results", []))
    steps: list[InverseStep] = []

    # Roll back in reverse mutation order.
    for index, row in enumerate(reversed(results), start=1):
        kind = str(row.get("kind") or "")
        action = str(row.get("action") or "")
        name = str(row.get("name") or "")
        response = row.get("response")

        if kind not in KINDS:
            steps.append(
                InverseStep(
                    order=index,
                    kind=kind,
                    action=InverseAction.NOOP,
                    uuid=None,
                    name=name,
                    before=None,
                    verified_shape=False,
                    reason="неизвестный тип операции",
                )
            )
            continue

        snapshot_key, keys = KINDS[kind]
        before_obj = find_by_name(before_snapshot.get(snapshot_key), name, keys)

        if action == "create":
            uuid = first_uuid(response)
            # Create response may be wrapped or omit UUID. If so, caller can
            # re-resolve live object by name before delete.
            steps.append(
                InverseStep(
                    order=index,
                    kind=kind,
                    action=InverseAction.DELETE_CREATED,
                    uuid=uuid,
                    name=name,
                    before=None,
                    verified_shape=True,
                    reason="объект был создан этой транзакцией",
                )
            )
            continue

        if action == "update" and before_obj:
            uuid = before_obj.get("uuid")
            steps.append(
                InverseStep(
                    order=index,
                    kind=kind,
                    action=InverseAction.RESTORE_UPDATED,
                    uuid=str(uuid) if uuid else None,
                    name=name,
                    before=before_obj,
                    verified_shape=bool(uuid),
                    reason="в snapshot найдено исходное состояние объекта",
                )
            )
            continue

        steps.append(
            InverseStep(
                order=index,
                kind=kind,
                action=InverseAction.NOOP,
                uuid=None,
                name=name,
                before=before_obj,
                verified_shape=False,
                reason="не удалось построить безопасную обратную операцию",
            )
        )

    return steps
