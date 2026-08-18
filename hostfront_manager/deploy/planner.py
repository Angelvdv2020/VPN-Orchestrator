from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .bundle import MobileBundle


def _unwrap_list(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = _unwrap_list(value, keys)
            if nested:
                return nested
    return []


def _name(obj: dict[str, Any]) -> str:
    for key in ("name", "remark", "profileName"):
        value = obj.get(key)
        if isinstance(value, str):
            return value
    return ""


@dataclass(slots=True)
class DeployStep:
    kind: str
    action: str
    name: str
    reason: str
    live_uuid: str | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(slots=True)
class DeployPlan:
    profile_name: str
    steps: list[DeployStep]
    warnings: list[str]

    def to_dict(self):
        return {
            "profile_name": self.profile_name,
            "steps": [x.to_dict() for x in self.steps],
            "warnings": self.warnings,
        }


def build_deploy_plan(bundle: MobileBundle, snapshot: dict[str, Any]) -> DeployPlan:
    profile_name = str(bundle.client_metadata.get("profile") or "Mobile")

    profiles = _unwrap_list(
        snapshot.get("config_profiles"),
        ("configProfiles", "config_profiles", "response", "data"),
    )
    hosts = _unwrap_list(
        snapshot.get("hosts"),
        ("hosts", "response", "data"),
    )
    squads = _unwrap_list(
        snapshot.get("internal_squads"),
        ("internalSquads", "internal_squads", "response", "data"),
    )

    steps: list[DeployStep] = []
    warnings: list[str] = []

    live_profile = next((x for x in profiles if _name(x) == profile_name), None)
    if live_profile:
        steps.append(
            DeployStep(
                "config-profile",
                "update",
                profile_name,
                "профиль с таким именем уже существует",
                str(live_profile.get("uuid") or "") or None,
            )
        )
    else:
        steps.append(
            DeployStep(
                "config-profile",
                "create",
                profile_name,
                "профиль с таким именем не найден",
            )
        )

    for host in bundle.host_plan:
        host_name = str(host.get("remark") or host.get("name") or "")
        live = next((x for x in hosts if _name(x) == host_name), None)
        steps.append(
            DeployStep(
                "host",
                "update" if live else "create",
                host_name,
                "host найден" if live else "host отсутствует",
                str(live.get("uuid") or "") or None if live else None,
            )
        )

    squad_name = str(bundle.squad_plan.get("name") or f"{profile_name}-Mobile")
    live_squad = next((x for x in squads if _name(x) == squad_name), None)
    steps.append(
        DeployStep(
            "internal-squad",
            "update" if live_squad else "create",
            squad_name,
            "squad найден" if live_squad else "squad отсутствует",
            str(live_squad.get("uuid") or "") or None if live_squad else None,
        )
    )

    warnings.append(
        "Фактические UUID inbounds появляются после создания/обновления Config Profile; "
        "Hosts и Squad должны применяться второй фазой после повторного чтения API."
    )

    return DeployPlan(profile_name, steps, warnings)
