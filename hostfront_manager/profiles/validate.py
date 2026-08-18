from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..shell import ShellRunner


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    structural_errors: list[str]
    xray_checked: bool
    xray_stdout: str = ""
    xray_stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "structural_errors": self.structural_errors,
            "xray_checked": self.xray_checked,
            "xray_stdout": self.xray_stdout,
            "xray_stderr": self.xray_stderr,
        }


def structural_validate(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    inbounds = config.get("inbounds")
    if not isinstance(inbounds, list) or not inbounds:
        errors.append("inbounds отсутствует или пуст")
        return errors

    tags: set[str] = set()
    tcp_ports: list[tuple[str, int]] = []

    for idx, inbound in enumerate(inbounds):
        if not isinstance(inbound, dict):
            errors.append(f"inbounds[{idx}] не object")
            continue

        tag = inbound.get("tag")
        if not isinstance(tag, str) or not tag:
            errors.append(f"inbounds[{idx}] без tag")
        elif tag in tags:
            errors.append(f"повторяющийся inbound tag: {tag}")
        else:
            tags.add(tag)

        port = inbound.get("port")
        if not isinstance(port, int) or not 1 <= port <= 65535:
            errors.append(f"{tag or idx}: некорректный port")

        protocol = inbound.get("protocol")
        if protocol not in {"vless", "hysteria"}:
            errors.append(f"{tag or idx}: неожиданный protocol={protocol}")

        stream = inbound.get("streamSettings", {})
        method = stream.get("network")
        security = stream.get("security", "none")

        if security == "reality":
            reality = stream.get("realitySettings")
            if not isinstance(reality, dict):
                errors.append(f"{tag}: realitySettings отсутствует")
            else:
                for key in ("target", "serverNames", "privateKey", "shortIds"):
                    if key not in reality:
                        errors.append(f"{tag}: realitySettings.{key} отсутствует")

        if method == "xhttp":
            xhttp = stream.get("xhttpSettings")
            if not isinstance(xhttp, dict) or not str(xhttp.get("path", "")).startswith(
                "/"
            ):
                errors.append(f"{tag}: xhttpSettings.path отсутствует/некорректен")

        if protocol == "hysteria":
            hyst = stream.get("hysteriaSettings")
            if not isinstance(hyst, dict) or hyst.get("version") != 2:
                errors.append(f"{tag}: hysteriaSettings version 2 отсутствует")

        # UDP Hysteria and TCP can share the same numeric port. Collision checking
        # is intentionally only done for non-Hysteria listeners.
        if protocol != "hysteria" and isinstance(port, int):
            listen = str(inbound.get("listen", "0.0.0.0"))
            wildcard = {"0.0.0.0", "::", "[::]", "*", ""}
            for used_listen, used_port in tcp_ports:
                if used_port != port:
                    continue
                if (
                    listen == used_listen
                    or listen in wildcard
                    or used_listen in wildcard
                ):
                    errors.append(
                        f"TCP listen collision: {used_listen}:{port} conflicts with {listen}:{port}"
                    )
                    break
            tcp_ports.append((listen, port))

    return errors


def validate_with_xray(
    config: dict[str, Any],
    runner: ShellRunner,
    *,
    xray_binary: str = "xray",
) -> ValidationResult:
    structural = structural_validate(config)
    if structural:
        return ValidationResult(False, structural, False)

    binary = shutil.which(xray_binary)
    if not binary:
        return ValidationResult(
            False,
            [],
            False,
            xray_stderr="xray binary not found; full validation was not performed",
        )

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "config.json"
        path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        result = runner.run(
            [binary, "run", "-test", "-c", str(path)],
            check=False,
            timeout=max(runner.timeout, 30),
        )

    return ValidationResult(
        ok=result.returncode == 0,
        structural_errors=[],
        xray_checked=True,
        xray_stdout=result.stdout,
        xray_stderr=result.stderr,
    )
