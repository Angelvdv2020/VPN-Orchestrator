from hostfront_manager.deploy.verify import verify_rollback_after_apply


class FakeClient:
    def __init__(self, hosts):
        self.hosts = hosts

    def get_system_health(self):
        return {"ok": True}

    def get_hosts(self):
        return {"response": {"hosts": self.hosts}}


def test_rollback_verifies_restored_update():
    original = {"uuid": "u1", "remark": "mobile", "address": "old.example"}
    before = {"hosts": {"response": {"hosts": [original]}}}
    applied = {"results": [{"kind": "host", "action": "update", "name": "mobile"}]}

    result = verify_rollback_after_apply(FakeClient([original]), before, applied)

    assert result["ok"]
    assert result["mismatches"] == []


def test_rollback_detects_created_object_left_behind():
    created = {"uuid": "u2", "remark": "new-mobile", "address": "new.example"}
    before = {"hosts": {"response": {"hosts": []}}}
    applied = {"results": [{"kind": "host", "action": "create", "name": "new-mobile"}]}

    result = verify_rollback_after_apply(FakeClient([created]), before, applied)

    assert not result["ok"]
    assert result["mismatches"][0]["reason"] == "created object still exists"
