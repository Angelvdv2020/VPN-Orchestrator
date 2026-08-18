from hostfront_manager.remnawave.inventory import _count


def test_count_payloads():
    assert _count([1, 2], ("nodes",)) == 2
    assert _count({"total": 15}, ("users",)) == 15
    assert _count({"response": {"nodes": [1, 2, 3]}}, ("nodes", "response")) == 3
