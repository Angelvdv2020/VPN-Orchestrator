from hostfront_manager.profiles.builder import build_mobile_profile
from hostfront_manager.profiles.models import MobileProfileSettings, RealitySettings
from hostfront_manager.profiles.validate import structural_validate


def settings():
    return MobileProfileSettings(
        name="Mobile",
        edge_domain="edge.example.com",
        front_domain="front.example.com",
        reality=RealitySettings(
            target="example.org:443",
            server_name="example.org",
            private_key="private_key_here",
            short_id="0011223344556677",
        ),
        hysteria_auth="secret-secret-secret",
    )


def test_builder_has_four_inbounds():
    p = build_mobile_profile(settings())
    assert len(p.xray_config["inbounds"]) == 4
    assert not structural_validate(p.xray_config)


def test_tags_unique():
    p = build_mobile_profile(settings())
    tags = [x["tag"] for x in p.xray_config["inbounds"]]
    assert len(tags) == len(set(tags))


def test_host_front_localhost():
    p = build_mobile_profile(settings())
    inbound = next(x for x in p.xray_config["inbounds"] if x["tag"] == "MOBILE-HOST-FRONT")
    assert inbound["listen"] == "127.0.0.1"
    assert inbound["streamSettings"]["security"] == "none"
