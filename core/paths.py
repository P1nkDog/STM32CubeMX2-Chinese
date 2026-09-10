"""打包 EXE / 开发环境下的路径约定。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "STM32CubeMX2-Chinese"
DICT_NAME = "localization.json"
CSV_NAME = "manual-translate.csv"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> Path:
    """EXE 所在目录；开发态为项目根。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_root() -> Path:
    """PyInstaller 解压目录 / 项目根（内置资源）。"""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """用户可写数据目录：优先 EXE 旁，不可写则 %LOCALAPPDATA%。"""
    base = exe_dir()
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return base
    except OSError:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        p = Path(local) / APP_NAME
        p.mkdir(parents=True, exist_ok=True)
        return p


def user_dict_path() -> Path:
    return user_data_dir() / DICT_NAME


def bundled_dict_path() -> Path:
    return bundled_root() / "dict" / DICT_NAME


def csv_path() -> Path:
    return user_data_dir() / CSV_NAME
