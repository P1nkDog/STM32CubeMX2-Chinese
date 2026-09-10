from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

ORIG_SUFFIX = ".orig"
STATE_NAME = ".stm32cubemx2-chinese.json"


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def backup_path(target: Path) -> Path:
    return target.with_name(target.name + ORIG_SUFFIX)


def ensure_backup(target: Path) -> Path:
    """仅首次备份为 .orig，之后不覆盖。"""
    bak = backup_path(target)
    if not bak.exists():
        shutil.copy2(target, bak)
    return bak


def restore_from_backup(target: Path) -> bool:
    bak = backup_path(target)
    if not bak.exists():
        return False
    shutil.copy2(bak, target)
    return True


def state_path(root: Path) -> Path:
    return root / STATE_NAME


def write_state(root: Path, payload: dict) -> None:
    payload = dict(payload)
    payload["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    state_path(root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_state(root: Path) -> dict | None:
    p = state_path(root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def clear_state(root: Path) -> None:
    p = state_path(root)
    if p.is_file():
        p.unlink()
