from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

ORIG_SUFFIX = ".orig"
STATE_NAME = ".stm32cubemx2-chinese.json"
TMP_SUFFIX = ".cubemx2zh-tmp"


def _tmp_path(target: Path) -> Path:
    # 后缀不是 .js/.gz，万一残留在 app 目录里也不会被应用加载
    return target.with_name(target.name + TMP_SUFFIX)


def replace_into(target: Path, fill) -> None:
    """先写同目录临时文件，再 os.replace 原子换上。

    中途断电/被杀只会留下临时文件，target 要么是旧内容、要么是新内容，
    不会出现写了一半的 bundle —— 对 .orig 尤其要紧：它只写一次，
    写坏了就会被当成「干净基线」一直用下去。
    """
    tmp = _tmp_path(target)
    try:
        fill(tmp)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_bytes(target: Path, data: bytes) -> None:
    replace_into(target, lambda tmp: tmp.write_bytes(data))


def atomic_copy(src: Path, dst: Path) -> None:
    replace_into(dst, lambda tmp: shutil.copy2(src, tmp))


def backup_path(target: Path) -> Path:
    return target.with_name(target.name + ORIG_SUFFIX)


def ensure_backup(target: Path) -> Path:
    """仅首次备份为 .orig，之后不覆盖。"""
    bak = backup_path(target)
    if not bak.exists():
        atomic_copy(target, bak)
    return bak


def restore_from_backup(target: Path) -> bool:
    bak = backup_path(target)
    if not bak.exists():
        return False
    atomic_copy(bak, target)
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
