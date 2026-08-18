from __future__ import annotations

import json
from typing import Any

from .models import DoctorReport
from .state import HostState


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def render_status(state: HostState) -> None:
    print("=== VPN Orchestrator v4 ===")
    print(f"Host:       {state.hostname}")
    print(f"OS:         {state.os_name}")
    print(f"Kernel:     {state.kernel}")
    print(f"Arch:       {state.architecture}")
    print(f"Python:     {state.python}")
    print(f"Root:       {'OK' if state.is_root else 'NO'}")
    print(f"systemd:    {'OK' if state.systemd_present else 'NO'}")
    print(f"Docker:     {'OK' if state.docker_present else 'NO'}")


def render_doctor(report: DoctorReport) -> None:
    print("=== DIAGNOSTICS ===")
    for item in report.checks:
        mark = "OK" if item.ok else "FAIL"
        crit = "" if item.critical else " [optional]"
        print(f"[{mark:4}] {item.name:22} {item.summary}{crit}")
    print()
    passed = sum(1 for x in report.checks if x.ok)
    print(f"Итог: {passed}/{len(report.checks)} проверок пройдено")
    print("SYSTEM HEALTH:", "OK" if report.ok else "ATTENTION")
