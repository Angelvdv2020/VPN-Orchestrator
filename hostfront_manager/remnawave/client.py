from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..errors import ManagerError


@dataclass(slots=True)
class ApiResponse:
    status: int
    data: Any


class RemnawaveClient:
    def __init__(self, base_url: str, token: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        query: dict[str, Any] | None = None,
    ) -> ApiResponse:
        if not self.base_url.startswith(("http://", "https://")):
            raise ManagerError("Некорректный Remnawave base_url")

        url = self.base_url + "/" + path.lstrip("/")
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            url += "?" + urllib.parse.urlencode(clean)

        payload = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=payload, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                try:
                    data = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    data = raw
                return ApiResponse(resp.status, data)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            raise ManagerError(f"Remnawave API HTTP {exc.code}: {raw[:800]}") from exc
        except urllib.error.URLError as exc:
            raise ManagerError(f"Remnawave API недоступен: {exc}") from exc


    def get_node(self, uuid: str) -> Any:
        return self.request("GET", f"/api/nodes/{uuid}").data

    def create_node(self, payload: dict[str, Any]) -> Any:
        return self.request("POST", "/api/nodes", body=payload).data

    def update_node(self, payload: dict[str, Any]) -> Any:
        # Current Remnawave API uses PATCH /api/nodes for node updates.
        return self.request("PATCH", "/api/nodes", body=payload).data

    def delete_node(self, uuid: str) -> Any:
        return self.request("DELETE", f"/api/nodes/{uuid}").data

    def enable_node(self, uuid: str) -> Any:
        return self.request("POST", f"/api/nodes/{uuid}/actions/enable").data

    def disable_node(self, uuid: str) -> Any:
        return self.request("POST", f"/api/nodes/{uuid}/actions/disable").data


    def get_system_metadata(self) -> Any:
        return self.request("GET", "/api/system/metadata").data

    def get_system_configuration(self) -> Any:
        return self.request("GET", "/api/system/configuration").data

    def get_system_health(self) -> Any:
        return self.request("GET", "/api/system/health").data

    def get_system_stats_recap(self) -> Any:
        return self.request("GET", "/api/system/stats/recap").data

    def get_config_profile(self, uuid: str) -> Any:
        return self.request("GET", f"/api/config-profiles/{uuid}").data

    def get_config_profile_inbounds(self, uuid: str) -> Any:
        return self.request("GET", f"/api/config-profiles/{uuid}/inbounds").data

    def get_config_profile_computed_config(self, uuid: str) -> Any:
        return self.request("GET", f"/api/config-profiles/{uuid}/computed-config").data

    def delete_config_profile(self, uuid: str) -> Any:
        return self.request("DELETE", f"/api/config-profiles/{uuid}").data

    def get_host(self, uuid: str) -> Any:
        return self.request("GET", f"/api/hosts/{uuid}").data

    def delete_host(self, uuid: str) -> Any:
        return self.request("DELETE", f"/api/hosts/{uuid}").data

    def get_internal_squad(self, uuid: str) -> Any:
        return self.request("GET", f"/api/internal-squads/{uuid}").data

    def delete_internal_squad(self, uuid: str) -> Any:
        return self.request("DELETE", f"/api/internal-squads/{uuid}").data

    def get_nodes(self) -> Any:
        return self.request("GET", "/api/nodes").data

    def get_hosts(self) -> Any:
        return self.request("GET", "/api/hosts").data

    def get_users(self, *, size: int = 1000, start: int = 0) -> Any:
        return self.request("GET", "/api/users", query={"size": size, "start": start}).data


    def create_config_profile(self, payload: dict[str, Any]) -> Any:
        return self.request("POST", "/api/config-profiles", body=payload).data

    def update_config_profile(self, payload: dict[str, Any]) -> Any:
        return self.request("PATCH", "/api/config-profiles", body=payload).data

    def create_host(self, payload: dict[str, Any]) -> Any:
        return self.request("POST", "/api/hosts", body=payload).data

    def update_host(self, payload: dict[str, Any]) -> Any:
        return self.request("PATCH", "/api/hosts", body=payload).data

    def create_internal_squad(self, payload: dict[str, Any]) -> Any:
        return self.request("POST", "/api/internal-squads", body=payload).data

    def update_internal_squad(self, payload: dict[str, Any]) -> Any:
        return self.request("PATCH", "/api/internal-squads", body=payload).data

    def get_config_profiles(self) -> Any:
        return self.request("GET", "/api/config-profiles").data

    def get_internal_squads(self) -> Any:
        return self.request("GET", "/api/internal-squads").data
