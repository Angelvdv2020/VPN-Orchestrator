from __future__ import annotations

from typing import Any

from ..errors import ManagerError
from ..remnawave.client import RemnawaveClient
from ..remnawave.shape import find_by_name
from .models import InverseAction, InverseStep
from .sanitize import sanitize_update_object


LIVE_KEYS = {
    "config-profile": ("configProfiles", "config_profiles", "response", "data"),
    "host": ("hosts", "response", "data"),
    "internal-squad": ("internalSquads", "internal_squads", "response", "data"),
}


def _live_collection(client: RemnawaveClient, kind: str) -> Any:
    if kind == "config-profile":
        return client.get_config_profiles()
    if kind == "host":
        return client.get_hosts()
    if kind == "internal-squad":
        return client.get_internal_squads()
    raise ManagerError(f"Неизвестный rollback kind: {kind}")


def _delete(client: RemnawaveClient, kind: str, uuid: str) -> Any:
    if kind == "config-profile":
        return client.delete_config_profile(uuid)
    if kind == "host":
        return client.delete_host(uuid)
    if kind == "internal-squad":
        return client.delete_internal_squad(uuid)
    raise ManagerError(f"Удаление не поддерживается для {kind}")


def _update(client: RemnawaveClient, kind: str, payload: dict[str, Any]) -> Any:
    if kind == "config-profile":
        return client.update_config_profile(payload)
    if kind == "host":
        return client.update_host(payload)
    if kind == "internal-squad":
        return client.update_internal_squad(payload)
    raise ManagerError(f"Restore не поддерживается для {kind}")


def apply_inverse_plan(
    client: RemnawaveClient,
    steps: list[InverseStep],
    *,
    require_verified_shape: bool,
    apply: bool,
) -> dict[str, Any]:
    report: list[dict[str, Any]] = []

    for step in steps:
        row = step.to_dict()
        row["applied"] = False
        row["response"] = None

        if step.action == InverseAction.NOOP:
            report.append(row)
            continue

        if require_verified_shape and not step.verified_shape:
            raise ManagerError(
                f"Rollback остановлен: нет подтверждённой формы DTO для "
                f"{step.kind} {step.name}"
            )

        live = _live_collection(client, step.kind)
        current = find_by_name(live, step.name, LIVE_KEYS[step.kind])

        if step.action == InverseAction.DELETE_CREATED:
            if current is None:
                row["reason"] += "; объект уже отсутствует"
                report.append(row)
                continue

            uuid = step.uuid or current.get("uuid")
            if not uuid:
                raise ManagerError(
                    f"Rollback не может определить UUID созданного {step.kind}: {step.name}"
                )

            if apply:
                row["response"] = _delete(client, step.kind, str(uuid))
                row["applied"] = True
            report.append(row)
            continue

        if step.action == InverseAction.RESTORE_UPDATED:
            if not step.before:
                raise ManagerError(f"Нет before-состояния для {step.kind}: {step.name}")
            payload = sanitize_update_object(step.before)
            if step.uuid:
                payload.setdefault("uuid", step.uuid)

            if apply:
                row["response"] = _update(client, step.kind, payload)
                row["applied"] = True
            else:
                row["restore_payload"] = payload

            report.append(row)
            continue

    return {
        "apply": apply,
        "steps": report,
        "ok": True,
    }
