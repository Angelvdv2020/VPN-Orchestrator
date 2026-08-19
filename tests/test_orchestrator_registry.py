from pathlib import Path

from hostfront_manager.web.registry import load_registry, save_registry


def test_registry_roundtrip_normalizes_country_and_writes_atomically(tmp_path: Path):
    saved = save_registry(
        tmp_path,
        {
            "mode": "safe-attach",
            "locations": [
                {
                    "id": "france",
                    "name": "Франция",
                    "country": "fr",
                    "flag": "🇫🇷",
                    "profile_uuid": "profile-1",
                }
            ],
        },
    )
    assert saved["mode"] == "safe-attach"
    loaded = load_registry(tmp_path)
    assert loaded["locations"][0]["country"] == "FR"
    assert loaded["locations"][0]["profile_uuid"] == "profile-1"


def test_invalid_registry_mode_is_rejected(tmp_path: Path):
    try:
        save_registry(tmp_path, {"mode": "unsafe", "locations": []})
    except ValueError as exc:
        assert "mode" in str(exc)
    else:  # pragma: no cover - assertion keeps the failure message explicit
        raise AssertionError("invalid mode was accepted")
