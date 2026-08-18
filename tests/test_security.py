from hostfront_manager.security import redact_sensitive


def test_redact_sensitive_nested_values():
    value = {
        "response": {
            "privateKey": "private",
            "hysteria_auth": "hy-secret",
            "nested": [{"auth": "password", "name": "safe"}],
        }
    }

    redacted = redact_sensitive(value)

    assert redacted["response"]["privateKey"] == "***"
    assert redacted["response"]["hysteria_auth"] == "***"
    assert redacted["response"]["nested"][0] == {"auth": "***", "name": "safe"}
