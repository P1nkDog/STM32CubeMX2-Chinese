"""词典更新与软件更新。

- 词典更新：从 GitHub raw 拉取最新 localization.json，写入用户词典目录
  （EXE 旁或 %LOCALAPPDATA%），汉化时按 resolve_dictionary 优先级自动优先使用。
- 软件更新：用默认浏览器打开 GitHub Releases 发布页，由用户自行下载新版 EXE。
"""
from __future__ import annotations

import json
import urllib.error
import webbrowser
from pathlib import Path

from . import dictionary, paths
from .dictionary import DEFAULT_REMOTE_URL, fetch_remote

# 你的 GitHub 仓库（owner/repo），与 core/dictionary.py 的 GITHUB_REPO 保持一致
GITHUB_REPO = "P1nkDog/STM32CubeMX2-Chinese"
GITHUB_HOME = f"https://github.com/{GITHUB_REPO}"
RELEASES_PAGE = f"{GITHUB_HOME}/releases"


def version_key(v) -> tuple[int, ...]:
    """'v0.1.0' / '0.1.0' → (0, 1, 0)；无法解析的段按 0 处理。"""
    text = str(v or "").lstrip("vV").strip()
    out: list[int] = []
    for seg in text.replace("-", ".").split("."):
        try:
            out.append(int(seg))
        except ValueError:
            out.append(0)
    return tuple(out)


def is_newer(remote: str, local: str) -> bool:
    return version_key(remote) > version_key(local)


def validate_dictionary(d: object) -> bool:
    """远程词典能不能用：扁平 ``entries`` 格式 + 带版本号。

    判据只此一份，取自 ``dictionary.is_current_format()`` —— 和
    ``resolve_dictionary()`` 认词典用的是同一个函数。以前这里自己写了一遍
    v0.1.0 的 ``files[<bundle>].entries[]`` 字节片段结构，那种格式在 v0.2.0
    已经不存在，于是本函数对**仓库自己那份词典**恒返回 False，
    「词典更新」在任何网络条件下都失败（见 tools/test_update.py 的回归断言）。

    版本号单独查：``is_newer()`` 靠它比较，缺了会退化成 ``(0,)`` 而误判「有更新」。
    """
    if not dictionary.is_current_format(d):
        return False
    return bool(str(d.get("version") or "").strip())


def current_dict_info() -> tuple[dict | None, str]:
    """返回当前生效的 (词典, 来源)；失败返回 (None, 错误信息)。"""
    try:
        return dictionary.resolve_dictionary()
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def check_dict_update(timeout: float = 15.0) -> tuple[dict | None, str]:
    """拉取远程词典并比较版本。返回 ``(结果, 错误说明)``，成功时错误为空串。

    两种失败要分开说：「拉不到」是网络或地址问题，「拉到了但格式不对」是
    远程那份的问题。以前两者都折成同一个 ``None``，调用方只能说一句
    「网络不可用 / 被墙」，等于把用户支去排查自己网通不通。
    """
    try:
        remote = fetch_remote(DEFAULT_REMOTE_URL, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return None, f"拉取失败：{type(e).__name__}: {e}"
    if not validate_dictionary(remote):
        top = ",".join(sorted(remote)[:6]) if isinstance(remote, dict) else type(remote).__name__
        return None, (
            "远程词典不是扁平 entries 格式，或缺 version —— "
            f"拿到的顶层键: {top}。请确认远程地址指向本仓库的 dict/localization.json。"
        )
    local, src = current_dict_info()
    local_ver = str((local or {}).get("version", ""))
    return {
        "remote_version": str(remote.get("version", "")),
        "local_version": local_ver,
        "local_source": src,
        "has_update": is_newer(str(remote.get("version", "")), local_ver),
        "raw": remote,
    }, ""


def update_dict(remote: dict) -> Path:
    """将远程词典原子写入用户目录，返回写入路径。"""
    target = paths.user_dict_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(remote, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(target)
    return target


def open_releases_page() -> bool:
    """用默认浏览器打开 GitHub Releases 发布页（软件更新入口）。"""
    return webbrowser.open(RELEASES_PAGE)
