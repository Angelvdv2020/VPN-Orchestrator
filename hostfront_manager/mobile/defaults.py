from __future__ import annotations

from .models import PathCandidate, TransportKind


def default_paths(edge_host: str, front_host: str | None = None) -> list[PathCandidate]:
    front_host = front_host or edge_host
    return [
        PathCandidate(
            id="reality-xhttp",
            name="VLESS REALITY XHTTP",
            transport=TransportKind.REALITY_XHTTP,
            host=edge_host,
            port=443,
            network="tcp",
            priority=100,
        ),
        PathCandidate(
            id="host-front",
            name="HOST-FRONT",
            transport=TransportKind.HOST_FRONT,
            host=front_host,
            port=443,
            network="tcp",
            priority=95,
        ),
        PathCandidate(
            id="reality-raw",
            name="VLESS REALITY RAW",
            transport=TransportKind.REALITY_RAW,
            host=edge_host,
            port=8443,
            network="tcp",
            priority=90,
        ),
        PathCandidate(
            id="hysteria2",
            name="Hysteria2",
            transport=TransportKind.HYSTERIA2,
            host=edge_host,
            port=443,
            network="udp",
            priority=90,
        ),
    ]
