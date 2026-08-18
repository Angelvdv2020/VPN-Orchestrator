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


def test_host_front_listen_can_use_private_bridge():
    value = settings()
    value.host_front_listen = "172.18.0.1"
    profile = build_mobile_profile(value)
    inbound = next(
        item for item in profile.xray_config["inbounds"]
        if item["tag"] == "MOBILE-HOST-FRONT"
    )
    assert inbound["listen"] == "172.18.0.1"


def test_reality_does_not_force_client_version():
    profile = build_mobile_profile(settings())
    inbound = next(
        item for item in profile.xray_config["inbounds"]
        if item["tag"] == "MOBILE-REALITY-XHTTP"
    )
    reality = inbound["streamSettings"]["realitySettings"]
    assert "minClientVer" not in reality
    assert "maxClientVer" not in reality


def test_transports_use_remnawave_network_field_and_hysteria_tls():
    profile = build_mobile_profile(settings())
    by_tag = {item["tag"]: item for item in profile.xray_config["inbounds"]}
    assert by_tag["MOBILE-REALITY-XHTTP"]["streamSettings"]["network"] == "xhttp"
    assert (
        by_tag["MOBILE-REALITY-XHTTP"]["streamSettings"]["xhttpSettings"]["mode"]
        == "packet-up"
    )
    hysteria = by_tag["MOBILE-HY2"]["streamSettings"]
    assert hysteria["network"] == "hysteria"
    assert hysteria["security"] == "tls"
    assert hysteria["tlsSettings"]["serverName"] == "edge.example.com"


def test_host_plan_contains_subscription_overrides():
    profile = build_mobile_profile(settings())
    by_tag = {item["inbound_tag"]: item for item in profile.host_plan}
    assert by_tag["MOBILE-REALITY-XHTTP"]["path"] == "/mobile"
    assert by_tag["MOBILE-REALITY-XHTTP"]["sni"] == "example.org"
    assert by_tag["MOBILE-HY2"]["securityLayer"] == "TLS"
    assert by_tag["MOBILE-HOST-FRONT"]["path"] == "/edge"
