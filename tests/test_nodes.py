from hostfront_manager.nodes.compose import build_node_compose
from hostfront_manager.nodes.models import NodeRuntimeSpec, PlanAction
from hostfront_manager.nodes.planner import plan_node


def test_compose():
    text = build_node_compose(
        NodeRuntimeSpec(node_port=2222, secret_key="abc123")
    )
    assert "remnawave/node:latest" in text
    assert "NODE_PORT=2222" in text
    assert "SECRET_KEY=abc123" in text
    assert "NET_ADMIN" in text


def test_compose_can_mount_letsencrypt_read_only():
    text = build_node_compose(
        NodeRuntimeSpec(
            node_port=2222,
            secret_key="abc123",
            mount_letsencrypt=True,
        )
    )
    assert "/etc/letsencrypt:/etc/letsencrypt:ro" in text


def test_plan_create():
    plan = plan_node({"name": "new-node", "port": 2222}, {"response": []})
    assert plan.action == PlanAction.CREATE


def test_plan_noop():
    current = {
        "response": [
            {"uuid": "u1", "name": "n1", "port": 2222}
        ]
    }
    plan = plan_node({"name": "n1", "port": 2222}, current)
    assert plan.action == PlanAction.NOOP


def test_plan_update():
    current = {
        "response": [
            {"uuid": "u1", "name": "n1", "port": 1111}
        ]
    }
    plan = plan_node({"name": "n1", "port": 2222}, current)
    assert plan.action == PlanAction.UPDATE
    assert plan.current_uuid == "u1"
