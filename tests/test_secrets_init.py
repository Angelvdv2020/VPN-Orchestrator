from hostfront_manager.telemetry.auth import device_env_name


def test_device_env_name_is_stable():
    assert device_env_name("PREFIX_", "phone-1.eu") == "PREFIX_ID_70686F6E652D312E6575"


def test_device_env_names_do_not_collide():
    names = {
        device_env_name("PREFIX_", value) for value in ("phone-1", "phone_1", "phone.1")
    }
    assert len(names) == 3
