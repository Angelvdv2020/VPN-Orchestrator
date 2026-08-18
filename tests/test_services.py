from pathlib import Path

from hostfront_manager.install.services import render_services, write_services


def test_render_services(tmp_path):
    files = render_services(
        "/opt/hf/bin/hostfront-manager",
        Path("/etc/hf/config.toml"),
        Path("/etc/hf/secrets.env"),
    )
    assert "watchdog-run" in files.watchdog
    assert "web-serve" in files.web
    assert "ProtectSystem=strict" in files.web
    assert "User=hostfront-manager" in files.web
    assert "User=root" in files.watchdog
    paths = write_services(files, tmp_path)
    assert len(paths) == 2
    assert all(x.exists() for x in paths)
