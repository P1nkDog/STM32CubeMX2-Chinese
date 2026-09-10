from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__
from .dictionary import DEFAULT_REMOTE_URL

# 占位：发布后改成你的 GitHub repo releases API
RELEASES_API = (
    "https://api.github.com/repos/YOUR_NAME/STM32CubeMX2-Chinese/releases/latest"
)


def check_tool_update(timeout: float = 10.0) -> dict | None:
    """返回 {tag, url, body} 或 None。失败静默。"""
    try:
        req = urllib.request.Request(
            RELEASES_API, headers={"User-Agent": "STM32CubeMX2-Chinese"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = (data.get("tag_name") or "").lstrip("v")
        if not tag or tag == __version__:
            return None
        return {
            "tag": tag,
            "url": data.get("html_url") or "",
            "body": (data.get("body") or "")[:500],
            "current": __version__,
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, KeyError):
        return None


def check_dict_update(timeout: float = 10.0) -> dict | None:
    try:
        req = urllib.request.Request(
            DEFAULT_REMOTE_URL, headers={"User-Agent": "STM32CubeMX2-Chinese"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            remote = json.loads(resp.read().decode("utf-8"))
        return {"version": remote.get("version"), "raw": remote}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
