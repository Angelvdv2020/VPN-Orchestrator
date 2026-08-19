from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class RealitySettings:
    target: str
    server_name: str
    private_key: str
    short_id: str

    def validate(self) -> None:
        if ":" not in self.target:
            raise ValueError("REALITY target должен быть host:port")
        if not self.server_name:
            raise ValueError("REALITY server_name пуст")
        if not self.private_key:
            raise ValueError("REALITY private_key пуст")
        sid = self.short_id.strip().lower()
        if len(sid) > 16 or len(sid) % 2 != 0:
            raise ValueError(
                "REALITY short_id должен содержать чётное число hex-символов, максимум 16"
            )
        if sid and any(ch not in "0123456789abcdef" for ch in sid):
            raise ValueError("REALITY short_id должен быть hex")


@dataclass(slots=True)
class MobileProfileSettings:
    name: str
    edge_domain: str
    front_domain: str
    reality: RealitySettings
    # RAW may use a separate Reality keypair.  ``None`` keeps compatibility
    # with bundles created before per-transport key isolation was introduced.
    reality_raw: RealitySettings | None = None
    ingress_domains: tuple[str, ...] = ()
    reality_xhttp_port: int = 443
    reality_raw_port: int = 8443
    hysteria_port: int = 443
    host_front_local_port: int = 9443
    # Caddy is deployed in Docker and reaches the host through the default
    # bridge gateway. 127.0.0.1 would point back to the Caddy container.
    host_front_listen: str = "172.18.0.1"
    host_front_external_port: int = 443
    xhttp_path: str = "/mobile"
    host_front_path: str = "/edge"
    hysteria_auth: str = ""
    min_xray_version: str = "26.3.27"

    def validate(self) -> None:
        self.reality.validate()
        if self.reality_raw is not None:
            self.reality_raw.validate()
        for field_name in (
            "reality_xhttp_port",
            "reality_raw_port",
            "hysteria_port",
            "host_front_local_port",
            "host_front_external_port",
        ):
            value = getattr(self, field_name)
            if not 1 <= int(value) <= 65535:
                raise ValueError(f"{field_name} должен быть 1..65535")
        for attr in ("xhttp_path", "host_front_path"):
            value = getattr(self, attr)
            if not value.startswith("/"):
                raise ValueError(f"{attr} должен начинаться с /")
        if not self.edge_domain or "." not in self.edge_domain:
            raise ValueError("edge_domain выглядит некорректно")
        if not self.front_domain or "." not in self.front_domain:
            raise ValueError("front_domain выглядит некорректно")
        if not self.hysteria_auth:
            raise ValueError("hysteria_auth пуст")
        if not self.host_front_listen:
            raise ValueError("host_front_listen пуст")


@dataclass(slots=True)
class BuiltProfile:
    xray_config: dict[str, Any]
    inbound_map: dict[str, dict[str, Any]]
    host_plan: list[dict[str, Any]]
    squad_plan: dict[str, Any]
    node_roles: dict[str, Any]
    caddy_front: str
    client_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
