from pathlib import Path

from hostfront_manager.shell import CommandResult
from hostfront_manager.watchdog.repair import restart_services


class Runner:
    dry_run = False

    def __init__(self):
        self.calls = []

    def run(self, argv):
        self.calls.append(argv)
        return CommandResult(argv, 0, "", "")


def test_remnawave_repair_uses_compose(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    runner = Runner()
    restart_services(runner, ["remnawave"], ["remnawave"], panel_dir=tmp_path)
    assert runner.calls == [
        [
            "docker",
            "compose",
            "-f",
            str(tmp_path / "docker-compose.yml"),
            "restart",
            "remnawave",
        ]
    ]


def test_system_service_still_uses_systemctl():
    runner = Runner()
    restart_services(runner, ["docker"], ["docker"], panel_dir=Path("/missing"))
    assert runner.calls == [["systemctl", "restart", "docker"]]
