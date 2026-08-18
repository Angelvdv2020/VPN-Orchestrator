from hostfront_manager.rollback.planner import build_inverse_plan
from hostfront_manager.rollback.models import InverseAction
from hostfront_manager.nodes.assignment import (
    discover_assignment_shape,
    build_assignment_plan,
)
from hostfront_manager.mobile.policy import decide_failover
from hostfront_manager.mobile.models import (
    PathCandidate,
    PathHealth,
    ProbeStatus,
    TransportKind,
)


def test_inverse_create_host():
    before = {"hosts": {"response": []}}
    applied = {
        "results": [
            {
                "kind": "host",
                "action": "create",
                "name": "h1",
                "response": {"response": {"uuid": "u1"}},
            }
        ]
    }
    steps = build_inverse_plan(before, applied)
    assert steps[0].action == InverseAction.DELETE_CREATED
    assert steps[0].uuid == "u1"


def test_assignment_shape_discovery():
    node = {
        "response": {
            "uuid": "node-1",
            "configProfile": {
                "activeConfigProfileUuid": "p0",
                "activeInbounds": ["i0"],
            },
        }
    }
    shape = discover_assignment_shape(node)
    assert shape.verified
    assert shape.container_key == "configProfile"


def test_assignment_plan():
    node = {
        "response": {
            "uuid": "node-1",
            "configProfile": {
                "activeConfigProfileUuid": "p0",
                "activeInbounds": ["i0"],
            },
        }
    }
    plan = build_assignment_plan(
        node,
        node_uuid="node-1",
        role="edge",
        profile_uuid="p1",
        role_tags=["A", "B"],
        inbounds_by_tag={
            "A": {"uuid": "ia"},
            "B": {"uuid": "ib"},
        },
    )
    assert plan.patch_payload["configProfile"]["activeConfigProfileUuid"] == "p1"
    assert plan.patch_payload["configProfile"]["activeInbounds"] == ["ia", "ib"]


def test_failover_down_current():
    a = PathCandidate(
        id="a", name="A", transport=TransportKind.REALITY_XHTTP,
        host="a.example.com", port=443, network="tcp",
    )
    b = PathCandidate(
        id="b", name="B", transport=TransportKind.HOST_FRONT,
        host="b.example.com", port=443, network="tcp",
    )
    ordered = [
        PathHealth(b, 110, ProbeStatus.UP, 40, 0, "ok"),
        PathHealth(a, 40, ProbeStatus.DOWN, None, 2, "down"),
    ]
    d = decide_failover(ordered, current_path_id="a")
    assert d.switch
    assert d.target_path_id == "b"
