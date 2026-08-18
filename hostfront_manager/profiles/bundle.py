from __future__ import annotations

import json
import os
from pathlib import Path

from .models import BuiltProfile


def _write_json(path: Path, data: object, mode: int = 0o600) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def write_bundle(profile: BuiltProfile, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

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
    paths[5].write_text(profile.caddy_front, encoding="utf-8")
    _write_json(paths[6], profile.client_metadata)

    return paths
