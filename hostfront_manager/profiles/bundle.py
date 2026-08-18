from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import BuiltProfile


def _write_json(path: Path, data: object, mode: int = 0o600) -> None:
    _write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n", mode)


def _write_text(path: Path, data: str, mode: int = 0o600) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        os.chmod(path, mode)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(tmp_name).unlink(missing_ok=True)
        raise


def write_bundle(profile: BuiltProfile, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_dir, 0o700)

    paths = [
        output_dir / "xray-config.json",
        output_dir / "inbound-map.json",
        output_dir / "host-plan.json",
        output_dir / "squad-plan.json",
        output_dir / "node-roles.json",
        output_dir / "front.Caddyfile",
        output_dir / "client-metadata.json",
    ]

    _write_json(paths[0], profile.xray_config)
    _write_json(paths[1], profile.inbound_map)
    _write_json(paths[2], profile.host_plan)
    _write_json(paths[3], profile.squad_plan)
    _write_json(paths[4], profile.node_roles)
    _write_text(paths[5], profile.caddy_front)
    _write_json(paths[6], profile.client_metadata)

    return paths
