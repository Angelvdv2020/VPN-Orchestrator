from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..errors import ManagerError
from .models import (
    NetworkKind,
    PathCandidate,
    ProbeSample,
    ProbeStatus,
    TransportKind,
)


class MobileStateStore:
    def __init__(self, path: Path):
        self.path = path

    def _fallback_path(self) -> Path:
        return Path("./mobile-state.json")

    def _resolve_write_path(self) -> Path:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            test = self.path.parent / ".write-test"
            test.write_text("1", encoding="utf-8")
            test.unlink()
            return self.path
        except PermissionError:
            return self._fallback_path()

    def load_raw(self) -> dict[str, Any]:
        path = self.path if self.path.exists() else self._fallback_path()
        if not path.exists():
            return {"version": 1, "paths": [], "samples": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ManagerError(f"Не удалось прочитать mobile state {path}: {exc}") from exc

    def save_raw(self, data: dict[str, Any]) -> Path:
        path = self._resolve_write_path()
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(path)
        return path

    def paths(self) -> list[PathCandidate]:
        result: list[PathCandidate] = []
        for item in self.load_raw().get("paths", []):
            result.append(
                PathCandidate(
                    id=str(item["id"]),
                    name=str(item.get("name", item["id"])),
                    transport=TransportKind(item["transport"]),
                    host=str(item["host"]),
                    port=int(item["port"]),
                    network=str(item.get("network", "tcp")),
                    enabled=bool(item.get("enabled", True)),
                    priority=int(item.get("priority", 100)),
                    metadata=dict(item.get("metadata", {})),
                )
            )
        return result

    def samples(self) -> list[ProbeSample]:
        result: list[ProbeSample] = []
        for item in self.load_raw().get("samples", []):
            result.append(
                ProbeSample(
                    path_id=str(item["path_id"]),
                    status=ProbeStatus(item["status"]),
                    checked_at=str(item["checked_at"]),
                    latency_ms=item.get("latency_ms"),
                    source=str(item.get("source", "server")),
                    detail=str(item.get("detail", "")),
                    network_kind=NetworkKind(item.get("network_kind", "unknown")),
                )
            )
        return result

    def set_paths(self, paths: list[PathCandidate]) -> Path:
        raw = self.load_raw()
        raw["paths"] = [p.to_dict() for p in paths]
        return self.save_raw(raw)

    def add_sample(self, sample: ProbeSample, keep_per_path: int = 40) -> Path:
        raw = self.load_raw()
        samples = list(raw.get("samples", []))
        samples.append(sample.to_dict())

        # Ограничиваем историю отдельно для каждого path.
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in samples:
            grouped.setdefault(str(row.get("path_id")), []).append(row)

        trimmed: list[dict[str, Any]] = []
        for rows in grouped.values():
            trimmed.extend(rows[-keep_per_path:])
        trimmed.sort(key=lambda x: str(x.get("checked_at", "")))
        raw["samples"] = trimmed
        return self.save_raw(raw)
