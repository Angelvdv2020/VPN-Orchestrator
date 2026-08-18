from __future__ import annotations

import socket
import ssl
import time

from .models import PathCandidate, ProbeSample, ProbeStatus, TransportKind


def _resolve(host: str) -> list[str]:
    try:
        return sorted({x[4][0] for x in socket.getaddrinfo(host, None)})
    except socket.gaierror:
        return []


def probe_tcp(path: PathCandidate, timeout: float) -> ProbeSample:
    ips = _resolve(path.host)
    if not ips:
        return ProbeSample.now(path.id, ProbeStatus.DOWN, detail="DNS resolution failed")

    started = time.perf_counter()
    try:
        with socket.create_connection((path.host, path.port), timeout=timeout):
            latency = (time.perf_counter() - started) * 1000
            return ProbeSample.now(
                path.id,
                ProbeStatus.UP,
                latency_ms=latency,
                detail=f"TCP connect OK; resolved={','.join(ips[:4])}",
            )
    except OSError as exc:
        return ProbeSample.now(path.id, ProbeStatus.DOWN, detail=f"TCP connect failed: {exc}")


def probe_tls(path: PathCandidate, timeout: float) -> ProbeSample:
    started = time.perf_counter()
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((path.host, path.port), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=path.host) as tls:
                tls.do_handshake()
                latency = (time.perf_counter() - started) * 1000
                version = tls.version() or "TLS"
                return ProbeSample.now(
                    path.id,
                    ProbeStatus.UP,
                    latency_ms=latency,
                    detail=f"{version} handshake OK",
                )
    except OSError as exc:
        return ProbeSample.now(path.id, ProbeStatus.DOWN, detail=f"TLS check failed: {exc}")


def probe_udp_route(path: PathCandidate, timeout: float) -> ProbeSample:
    # UDP connect не подтверждает Hysteria2 handshake.
    # Он проверяет только то, что локальный стек может построить UDP маршрут.
    ips = _resolve(path.host)
    if not ips:
        return ProbeSample.now(path.id, ProbeStatus.DOWN, detail="DNS resolution failed")
    try:
        family = socket.AF_INET6 if ":" in ips[0] else socket.AF_INET
        with socket.socket(family, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.connect((ips[0], path.port))
            return ProbeSample.now(
                path.id,
                ProbeStatus.UNKNOWN,
                detail="UDP route exists; application handshake not verified",
            )
    except OSError as exc:
        return ProbeSample.now(path.id, ProbeStatus.DOWN, detail=f"UDP route failed: {exc}")


def probe_path(path: PathCandidate, timeout: float) -> ProbeSample:
    if not path.enabled:
        return ProbeSample.now(path.id, ProbeStatus.UNKNOWN, detail="path disabled")

    if path.network.lower() == "udp" or path.transport == TransportKind.HYSTERIA2:
        return probe_udp_route(path, timeout)

    if path.transport == TransportKind.HOST_FRONT:
        return probe_tls(path, timeout)

    # REALITY нельзя корректно проверить обычным TLS-клиентом:
    # server-side handshake отличается. Здесь проверяем транспортную доступность TCP.
    return probe_tcp(path, timeout)
