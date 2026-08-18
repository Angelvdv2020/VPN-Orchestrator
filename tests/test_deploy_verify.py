from hostfront_manager.deploy.verify import verify_panel_after_apply


class Client:
    def __init__(self, *, connected=True, bind_host=True, complete_squad=True):
        self.connected = connected
        self.bind_host = bind_host
        self.complete_squad = complete_squad

    def get_system_health(self):
        return {"ok": True}

    def get_config_profiles(self):
        return {
            "response": [
                {
                    "name": "p",
                    "inbounds": [
                        {"uuid": "i1", "tag": "A"},
                        {"uuid": "i2", "tag": "B"},
                    ],
                }
            ]
        }

    def get_hosts(self):
        uuid = "i1" if self.bind_host else "wrong"
        return {
            "response": [
                {"remark": "h1", "inbound": {"configProfileInboundUuid": uuid}},
                {"remark": "h2", "inbound": {"configProfileInboundUuid": "i2"}},
            ]
        }

    def get_internal_squads(self):
        rows = (
            [{"uuid": "i1"}, {"uuid": "i2"}]
            if self.complete_squad
            else [{"uuid": "i1"}]
        )
        return {"response": [{"name": "s", "inbounds": rows}]}

    def get_nodes(self):
        return {
            "response": [
                {
                    "name": "n",
                    "isConnected": self.connected,
                    "isDisabled": False,
                    "configProfile": {
                        "activeInbounds": [{"uuid": "i1"}, {"uuid": "i2"}]
                    },
                }
            ]
        }


def test_verify_checks_relationships_and_connected_coverage():
    assert verify_panel_after_apply(Client(), ["A", "B"])["ok"] is True
    assert verify_panel_after_apply(Client(bind_host=False), ["A", "B"])["ok"] is False
    assert (
        verify_panel_after_apply(Client(complete_squad=False), ["A", "B"])["ok"]
        is False
    )
    assert verify_panel_after_apply(Client(connected=False), ["A", "B"])["ok"] is False
