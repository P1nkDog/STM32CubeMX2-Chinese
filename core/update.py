"""词典更新与软件更新。

- 词典更新：从 GitHub raw 拉取最新 localization.json，写入用户词典目录
  （EXE 旁或 %LOCALAPPDATA%），汉化时按 resolve_dictionary 优先级自动优先使用。
- 软件更新：用默认浏览器打开 GitHub Releases 发布页，由用户自行下载新版 EXE。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import paths
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


def validate_dictionary(d: dict) -> bool:
    """最小可用性校验：版本号 + bundle.js 条目存在。"""
    if not isinstance(d, dict):
        return False
    if not d.get("version"):
        return False
    files = d.get("files")
    if not isinstance(files, dict):
        return False
    file_cfg = files.get("lib/frontend/bundle.js")
    return bool(
        isinstance(file_cfg, dict)
        and isinstance(file_cfg.get("entries"), list)
        and file_cfg["entries"]
    )


def current_dict_info() -> tuple[dict | None, str]:
    """返回当前生效的 (词典, 来源)；失败返回 (None, 错误信息)。"""
    from . import dictionary

    try:
        return dictionary.resolve_dictionary()
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def check_dict_update(timeout: float = 15.0) -> dict | None:
    """拉取远程词典并比较版本。成功返回结果字典，失败/无效返回 None。"""
    try:
        remote = fetch_remote(DEFAULT_REMOTE_URL, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if not validate_dictionary(remote):
        return None
    local, src = current_dict_info()
    local_ver = str((local or {}).get("version", ""))
    return {
        "remote_version": str(remote.get("version", "")),
        "local_version": local_ver,
        "local_source": src,
        "has_update": is_newer(str(remote.get("version", "")), local_ver),
        "raw": remote,
    }


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
