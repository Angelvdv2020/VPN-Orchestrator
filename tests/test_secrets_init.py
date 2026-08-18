from hostfront_manager.telemetry.auth import device_env_name


def test_device_env_name_is_stable():
    assert device_env_name("PREFIX_", "phone-1.eu") == "PREFIX_PHONE_1_EU"
