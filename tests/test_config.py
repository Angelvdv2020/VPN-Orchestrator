from pathlib import Path

from hostfront_manager.config import load_config


def test_default_config():
    cfg = load_config(None)
    assert cfg.manager.command_timeout_seconds > 0
    assert 443 in cfg.checks.tcp_ports


def test_toml_config(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        """
[manager]
command_timeout_seconds = 12

[checks]
tcp_ports = [443]
""",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.manager.command_timeout_seconds == 12
    assert cfg.checks.tcp_ports == [443]
