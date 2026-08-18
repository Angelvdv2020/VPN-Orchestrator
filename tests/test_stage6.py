from pathlib import Path

from hostfront_manager.deploy.planner import build_deploy_plan
from hostfront_manager.deploy.bundle import MobileBundle
from hostfront_manager.remnawave.capabilities import _extract_version
from hostfront_manager.deploy.adapter_v32 import RemnawaveV32Adapter


def test_extract_version():
    assert _extract_version({"response": {"version": "3.2.3"}}) == "3.2.3"


def test_plan_create():
    bundle = MobileBundle(
        root=Path("."),
        xray_config={"inbounds": []},
        inbound_map={"TAG": {}},
        host_plan=[{
            "remark": "Mobile Host",
            "address": "edge.example.com",
            "port": 443,
            "inbound_tag": "TAG",
        }],
        squad_plan={"name": "Mobile-Squad", "inbound_tags": ["TAG"]},
        node_roles={},
        client_metadata={"profile": "Mobile"},
    )
    snapshot = {
        "config_profiles": {"response": []},
        "hosts": {"response": []},
        "internal_squads": {"response": []},
    }
    plan = build_deploy_plan(bundle, snapshot)
    assert plan.steps[0].kind == "config-profile"
    assert plan.steps[0].action == "create"


def test_host_payload_uses_v32_inbound_object():
    adapter = RemnawaveV32Adapter(client=None)
    payload = adapter.build_host_payload(
        {"remark": "Mobile", "address": "edge.example", "port": 443},
        {"uuid": "inbound-uuid", "profileUuid": "profile-uuid"},
    )
    assert payload["inbound"] == {
        "configProfileUuid": "profile-uuid",
        "configProfileInboundUuid": "inbound-uuid",
    }
    assert "inboundUuid" not in payload
