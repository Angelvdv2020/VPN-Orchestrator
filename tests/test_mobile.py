from hostfront_manager.mobile.defaults import default_paths
from hostfront_manager.mobile.engine import recommend
from hostfront_manager.mobile.models import (
    NetworkKind,
    ProbeSample,
    ProbeStatus,
)


def test_mobile_recommend_prefers_confirmed_path():
    paths = default_paths("example.com")
    samples = [
        ProbeSample.now("reality-xhttp", ProbeStatus.DOWN),
        ProbeSample.now("host-front", ProbeStatus.UP, latency_ms=40),
    ]
    rec = recommend(
        paths,
        samples,
        network_kind=NetworkKind.MOBILE,
        failure_penalty=18,
        stale_after_seconds=900,
        prefer_tcp_on_unknown_network=True,
    )
    assert rec.selected is not None
    assert rec.selected.path.id == "host-front"


def test_udp_unknown_does_not_beat_confirmed_tcp():
    paths = default_paths("example.com")
    samples = [
        ProbeSample.now("reality-xhttp", ProbeStatus.UP, latency_ms=60),
        ProbeSample.now("hysteria2", ProbeStatus.UNKNOWN),
    ]
    rec = recommend(
        paths,
        samples,
        network_kind=NetworkKind.MOBILE,
        failure_penalty=18,
        stale_after_seconds=900,
        prefer_tcp_on_unknown_network=True,
    )
    assert rec.selected is not None
    assert rec.selected.path.id == "reality-xhttp"


def test_edge_and_front_hosts_are_separate():
    paths = {x.id: x for x in default_paths("edge.example.com", "front.example.com")}
    assert paths["host-front"].host == "front.example.com"
    assert paths["reality-xhttp"].host == "edge.example.com"
    assert paths["reality-raw"].port == 8443
