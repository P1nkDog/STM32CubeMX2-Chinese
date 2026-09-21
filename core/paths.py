"""打包 EXE / 开发环境下的路径约定。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "STM32CubeMX2-Chinese"
DICT_NAME = "localization.json"


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


# ---------------------------------------------------------------------------
# 机器级状态（与 EXE 放哪无关）
# ---------------------------------------------------------------------------

STATE_DIRNAME = ".stm32cubemx2-chinese"


def state_dir() -> Path:
    """家目录下的点目录。

    刻意不用 ``user_data_dir()``：那个优先落在 EXE 旁边，而这里存的是
    「这台机器上 CubeMX2 装在哪」—— 它属于机器，不属于某一份工具副本。
    把工具从桌面挪到 U 盘不该让它失忆。
    """
    return Path.home() / STATE_DIRNAME


def config_path() -> Path:
    return state_dir() / "config.json"


# ---------------------------------------------------------------------------
# 词典（唯一的一份：扁平 {英文原文: 中文}）
# ---------------------------------------------------------------------------


def user_dict_path() -> Path:
    """用户目录里的词典 —— ``--update-dict`` 的落点，优先级高于内置词典。"""
    return user_data_dir() / DICT_NAME


def bundled_dict_path() -> Path:
    return bundled_root() / "dict" / DICT_NAME


# ---------------------------------------------------------------------------
# 术语规范（译法的唯一依据，人工维护；被术语门禁读取，不是文档）
# ---------------------------------------------------------------------------

GLOSSARY_NAME = "glossary.zh.json"


def bundled_glossary_path() -> Path:
    return bundled_root() / "rules" / GLOSSARY_NAME


def user_glossary_path() -> Path:
    return user_data_dir() / GLOSSARY_NAME


def glossary_path() -> Path | None:
    """术语规范文件：优先随工具分发的那份。

    顺序与 ``user_dict_path()`` 的优先级**相反**：术语表是人工维护的唯一依据，
    若让用户目录里的过期副本压过随包分发的那份，门禁就变成在核对一份
    可能已经陈旧的规范 —— 那正是它要防的那种漂移。
    """
    for p in (bundled_glossary_path(), user_glossary_path()):
        if p.is_file():
            return p
    return None
