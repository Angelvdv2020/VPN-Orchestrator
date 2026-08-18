from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from .config import AppConfig
from .errors import BackupError


MANIFEST = "manifest.json"


def _backup_root(cfg: AppConfig) -> Path:
    root = cfg.manager.backup_dir
    try:
        root.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        root = Path("./backups")
        root.mkdir(parents=True, exist_ok=True)
    return root


def create_backup(cfg: AppConfig, *, label: str = "manual") -> Path:
    root = _backup_root(cfg)
    backup_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{label}"
    archive = root / f"{backup_id}.tar.gz"

    existing = [p for p in cfg.backup.paths if p.exists()]
    if not existing:
        raise BackupError("Нет существующих путей для backup из [backup].paths")

    manifest = {
        "id": backup_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "paths": [str(p) for p in existing],
        "hostname": os.uname().nodename if hasattr(os, "uname") else "",
    }

    try:
        with tempfile.TemporaryDirectory() as td:
            mp = Path(td) / MANIFEST
            mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            with tarfile.open(archive, "w:gz") as tf:
                tf.add(mp, arcname=MANIFEST)
                for p in existing:
                    tf.add(p, arcname=f"rootfs{p}")
    except Exception as exc:
        archive.unlink(missing_ok=True)
        raise BackupError(f"Не удалось создать backup: {exc}") from exc

    _prune(cfg)
    return archive


def list_backups(cfg: AppConfig) -> list[Path]:
    root = _backup_root(cfg)
    return sorted(root.glob("*.tar.gz"), reverse=True)


def _prune(cfg: AppConfig) -> None:
    keep = max(1, cfg.manager.backup_keep)
    for old in list_backups(cfg)[keep:]:
        old.unlink(missing_ok=True)


def _safe_members(tf: tarfile.TarFile):
    for member in tf.getmembers():
        name = Path(member.name)
        if name.is_absolute() or ".." in name.parts:
            raise BackupError(f"Небезопасный путь в архиве: {member.name}")
        yield member


def rollback(cfg: AppConfig, backup_id: str, *, dry_run: bool = False) -> list[str]:
    root = _backup_root(cfg)
    candidates = [
        root / backup_id,
        root / f"{backup_id}.tar.gz",
    ]
    archive = next((p for p in candidates if p.exists()), None)
    if not archive:
        raise BackupError(f"Backup не найден: {backup_id}")

    restored: list[str] = []
    try:
        with tarfile.open(archive, "r:gz") as tf:
            members = list(_safe_members(tf))
            mf = tf.extractfile(MANIFEST)
            if mf is None:
                raise BackupError("В backup нет manifest.json")
            manifest = json.loads(mf.read().decode("utf-8"))
            allowed = {str(Path(p)) for p in manifest.get("paths", [])}

            for member in members:
                if not member.name.startswith("rootfs/"):
                    continue
                target = Path("/") / Path(member.name).relative_to("rootfs")
                # Восстанавливаем только пути, которые были записаны в manifest.
                if not any(
                    str(target) == a or str(target).startswith(a.rstrip("/") + "/")
                    for a in allowed
                ):
                    raise BackupError(f"Путь не разрешён manifest: {target}")

            if dry_run:
                return sorted(allowed)

            with tempfile.TemporaryDirectory() as td:
                tf.extractall(td, members=members)
                stage = Path(td) / "rootfs"
                for allowed_path in sorted(allowed):
                    src = stage / allowed_path.lstrip("/")
                    dst = Path(allowed_path)
                    if not src.exists() and not src.is_symlink():
                        continue
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if dst.exists() or dst.is_symlink():
                        if dst.is_dir() and not dst.is_symlink():
                            shutil.rmtree(dst)
                        else:
                            dst.unlink()
                    shutil.move(str(src), str(dst))
                    restored.append(str(dst))
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError(f"Rollback не выполнен: {exc}") from exc

    return restored
