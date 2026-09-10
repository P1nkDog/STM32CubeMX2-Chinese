from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

# 占位：发布到 GitHub 后改成 raw 地址
DEFAULT_REMOTE_URL = (
    "https://raw.githubusercontent.com/YOUR_NAME/STM32CubeMX2-Chinese/main/dict/localization.json"
)
CACHE_NAME = "localization.cache.json"


def bundled_dict_path() -> Path:
    # 开发态：项目内 dict/；PyInstaller：sys._MEIPASS/dict/
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "dict" / "localization.json"


def cache_path() -> Path:
    return Path.home() / ".stm32cubemx2-chinese" / CACHE_NAME


def load_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_remote(url: str = DEFAULT_REMOTE_URL, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "STM32CubeMX2-Chinese"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    obj = json.loads(data.decode("utf-8"))
    cache_path().parent.mkdir(parents=True, exist_ok=True)
    cache_path().write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return obj


def resolve_dictionary(
    external: Path | None = None,
    remote_url: str = DEFAULT_REMOTE_URL,
    prefer_remote: bool = False,
) -> tuple[dict, str]:
    """返回 (词典, 来源说明)。

    优先级：external > 用户目录 localization.json > remote(可选) > cache > 内置 bundled。
    """
    from . import paths

    if external and external.is_file():
        return load_json_file(external), f"external:{external}"

    # 用户词典（EXE 旁或 %LOCALAPPDATA%）：回灌后应优先使用
    user = paths.user_dict_path()
    if user.is_file():
        try:
            return load_json_file(user), f"user:{user}"
        except (OSError, json.JSONDecodeError):
            pass

    if prefer_remote:
        try:
            return fetch_remote(remote_url), f"remote:{remote_url}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            pass

    cache = cache_path()
    if cache.is_file():
        try:
            return load_json_file(cache), f"cache:{cache}"
        except (OSError, json.JSONDecodeError):
            pass

    bundled = bundled_dict_path()
    if bundled.is_file():
        return load_json_file(bundled), f"bundled:{bundled}"

    # 最后再试一次远程
    return fetch_remote(remote_url), f"remote:{remote_url}"
