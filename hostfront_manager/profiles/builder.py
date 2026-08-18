from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import BuiltProfile, MobileProfileSettings


def _reality_stream(
    settings: MobileProfileSettings,
    *,
    method: str,
    path: str | None = None,
) -> dict[str, Any]:
    stream = {
        "network": method,
        "security": "reality",
        "realitySettings": {
            "show": False,
            "target": settings.reality.target,
            "xver": 0,
            "serverNames": [settings.reality.server_name],
            "privateKey": settings.reality.private_key,
            "maxTimeDiff": 0,
            "shortIds": [settings.reality.short_id],
        },
    }
    if method == "xhttp":
        # packet-up splits uploads into ordinary HTTP requests and is the most
        # tolerant mode for lossy mobile paths and HTTP/DPI middleboxes.  The
        # downlink remains streamed, while a failed upload does not pin all
        # client traffic to one long-lived TCP request.
        stream["xhttpSettings"] = {
            "path": path or settings.xhttp_path,
            "mode": "packet-up",
        }
    return stream


def _vless_inbound(
    *,
    tag: str,
    port: int,
    stream_settings: dict[str, Any],
    listen: str = "0.0.0.0",
) -> dict[str, Any]:
    return {
        "tag": tag,
        "listen": listen,
        "port": port,
        "protocol": "vless",
        "settings": {
            # Remnawave injects/controls users for managed inbounds.
            "clients": [],
            "decryption": "none",
        },
        "streamSettings": stream_settings,
        "sniffing": {
            "enabled": True,
            "destOverride": ["http", "tls", "quic"],
        },
    }


def _hysteria_inbound(settings: MobileProfileSettings) -> dict[str, Any]:
    return {
        "tag": "MOBILE-HY2",
        "listen": "0.0.0.0",
        "port": settings.hysteria_port,
        "protocol": "hysteria",
        "settings": {
            "version": 2,
            # Remnawave/Xray managed users may override transport auth later.
            "users": [],
        },
        "streamSettings": {
            "network": "hysteria",
            "security": "tls",
            "tlsSettings": {
                "serverName": settings.edge_domain,
                "certificates": [
                    {
                        "certificateFile": (
                            f"/etc/letsencrypt/live/{settings.edge_domain}/fullchain.pem"
                        ),
                        "keyFile": (
                            f"/etc/letsencrypt/live/{settings.edge_domain}/privkey.pem"
                        ),
                    }
                ],
            },
            "hysteriaSettings": {
                "version": 2,
                "auth": settings.hysteria_auth,
                "udpIdleTimeout": 60,
                "masquerade": {
                    "type": "string",
                    "content": "ok",
                    "headers": {
                        "content-type": "text/plain; charset=utf-8"
                    },
                    "statusCode": 200,
                },
            },
        },
        "sniffing": {
            "enabled": True,
            "destOverride": ["http", "tls", "quic"],
        },
    }


def _host_front_inbound(settings: MobileProfileSettings) -> dict[str, Any]:
    # This inbound is intentionally bound to localhost and expects a reverse proxy
    # on a domain controlled by the operator. VLESS without transport security is
    # acceptable only on this trusted local hop.
    return {
        "tag": "MOBILE-HOST-FRONT",
        "listen": settings.host_front_listen,
        "port": settings.host_front_local_port,
        "protocol": "vless",
        "settings": {
            "clients": [],
            "decryption": "none",
        },
        "streamSettings": {
            "network": "xhttp",
            "security": "none",
            "xhttpSettings": {
                "path": settings.host_front_path,
                "mode": "packet-up",
            },
        },
        "sniffing": {
            "enabled": True,
            "destOverride": ["http", "tls"],
        },
    }


def build_mobile_profile(settings: MobileProfileSettings) -> BuiltProfile:
    settings.validate()

    reality_xhttp = _vless_inbound(
        tag="MOBILE-REALITY-XHTTP",
        port=settings.reality_xhttp_port,
        stream_settings=_reality_stream(
            settings,
            method="xhttp",
            path=settings.xhttp_path,
        ),
    )

    reality_raw = _vless_inbound(
        tag="MOBILE-REALITY-RAW",
        port=settings.reality_raw_port,
        stream_settings=_reality_stream(
            settings,
            method="raw",
        ),
    )

    hysteria = _hysteria_inbound(settings)
    host_front = _host_front_inbound(settings)

    inbounds = [reality_xhttp, reality_raw, hysteria, host_front]

    config = {
        "version": {
            "min": settings.min_xray_version,
        },
        "log": {
            "loglevel": "warning",
        },
        "inbounds": inbounds,
        "outbounds": [
            {
                "tag": "DIRECT",
                "protocol": "freedom",
            },
            {
                "tag": "BLOCK",
                "protocol": "blackhole",
            },
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "ip": ["geoip:private"],
                    "outboundTag": "BLOCK",
                }
            ],
        },
    }

    inbound_map = {
        item["tag"]: {
            "protocol": item["protocol"],
            "listen": item["listen"],
            "port": item["port"],
            "transport": item.get("streamSettings", {}).get("network", ""),
            "security": item.get("streamSettings", {}).get("security", ""),
        }
        for item in inbounds
    }

    host_plan = [
        {
            "remark": f"{settings.name} Reality XHTTP",
            "address": settings.edge_domain,
            "port": settings.reality_xhttp_port,
            "inbound_tag": "MOBILE-REALITY-XHTTP",
            "network": "tcp",
            "path": settings.xhttp_path,
            "sni": settings.reality.server_name,
            "fingerprint": "chrome",
        },
        {
            "remark": f"{settings.name} Reality RAW",
            "address": settings.edge_domain,
            "port": settings.reality_raw_port,
            "inbound_tag": "MOBILE-REALITY-RAW",
            "network": "tcp",
            "sni": settings.reality.server_name,
            "fingerprint": "chrome",
        },
        {
            "remark": f"{settings.name} Hysteria2",
            "address": settings.edge_domain,
            "port": settings.hysteria_port,
            "inbound_tag": "MOBILE-HY2",
            "network": "udp",
            "sni": settings.edge_domain,
            "securityLayer": "TLS",
        },
        {
            "remark": f"{settings.name} Host Front",
            "address": settings.front_domain,
            "port": settings.host_front_external_port,
            "inbound_tag": "MOBILE-HOST-FRONT",
            "network": "tcp",
            "path": settings.host_front_path,
            "sni": settings.front_domain,
            "securityLayer": "TLS",
        },
    ]

    squad_plan = {
        "name": f"{settings.name}-Mobile",
        "inbound_tags": [x["tag"] for x in inbounds],
    }

    node_roles = {
        "edge": {
            "enable_inbounds": [
                "MOBILE-REALITY-XHTTP",
                "MOBILE-REALITY-RAW",
                "MOBILE-HY2",
            ],
            "domain": settings.edge_domain,
        },
        "front": {
            "enable_inbounds": [
                "MOBILE-HOST-FRONT",
            ],
            "domain": settings.front_domain,
            "notes": (
                "HOST-FRONT рассчитан на отдельный front-node/reverse-proxy "
                "или отдельный IP, чтобы внешний TCP/443 не конфликтовал с REALITY."
            ),
        },
    }

    caddy_front = f"""https://{settings.front_domain}:{settings.host_front_external_port} {{
    encode
    @mobile path {settings.host_front_path}*
    reverse_proxy @mobile {settings.host_front_listen}:{settings.host_front_local_port}
    respond 404
}}
"""

    client_metadata = {
        "profile": settings.name,
        "paths": [
            {
                "id": "reality-xhttp",
                "tag": "MOBILE-REALITY-XHTTP",
                "address": settings.edge_domain,
                "port": settings.reality_xhttp_port,
                "network": "tcp",
                "transport": "xhttp",
                "security": "reality",
                "server_name": settings.reality.server_name,
                "short_id": settings.reality.short_id,
                "path": settings.xhttp_path,
            },
            {
                "id": "reality-raw",
                "tag": "MOBILE-REALITY-RAW",
                "address": settings.edge_domain,
                "port": settings.reality_raw_port,
                "network": "tcp",
                "transport": "raw",
                "security": "reality",
                "server_name": settings.reality.server_name,
                "short_id": settings.reality.short_id,
            },
            {
                "id": "hysteria2",
                "tag": "MOBILE-HY2",
                "address": settings.edge_domain,
                "port": settings.hysteria_port,
                "network": "udp",
                "transport": "hysteria",
                "version": 2,
            },
            {
                "id": "host-front",
                "tag": "MOBILE-HOST-FRONT",
                "address": settings.front_domain,
                "port": settings.host_front_external_port,
                "network": "tcp",
                "transport": "xhttp",
                "security": "tls-at-front-proxy",
                "path": settings.host_front_path,
            },
        ],
    }

    return BuiltProfile(
        xray_config=config,
        inbound_map=inbound_map,
        host_plan=host_plan,
        squad_plan=squad_plan,
        node_roles=node_roles,
        caddy_front=caddy_front,
        client_metadata=client_metadata,
    )
