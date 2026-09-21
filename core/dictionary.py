from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

# 词典更新与软件更新都依赖它
GITHUB_REPO = "P1nkDog/STM32CubeMX2-Chinese"
# 仓库默认分支（你的仓库是 master；若以后在 GitHub 上把默认分支改成 main，记得同步）
DEFAULT_BRANCH = "master"
DEFAULT_REMOTE_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/{DEFAULT_BRANCH}/dict/localization.json"
)


def bundled_dict_path() -> Path:
    # 开发态：项目内 dict/；PyInstaller：sys._MEIPASS/dict/
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "dict" / "localization.json"


def load_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_current_format(d: object) -> bool:
    """词典是否是当前的扁平格式（顶层有非空 ``entries`` 映射）。

    旧版词典把译文存成 ``files[<bundle>].entries[]`` 的**字节片段**，
    那种结构喂给新的 langpack.build() 会得到一张**空表** —— 汉化不报错、
    但界面上一个字都不会变。所以这里显式识别并拒绝，让调用方回退到内置词典。
    """
    return (
        isinstance(d, dict)
        and isinstance(d.get("entries"), dict)
        and bool(d["entries"])
    )


def fetch_remote(url: str = DEFAULT_REMOTE_URL, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "STM32CubeMX2-Chinese"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def resolve_dictionary(
    external: Path | None = None,
    remote_url: str = DEFAULT_REMOTE_URL,
    prefer_remote: bool = False,
) -> tuple[dict, str]:
    """返回 (词典, 来源说明)。

    优先级：external > 用户目录 > 远程（可选）> 内置 bundled > 远程兜底。

    这里**没有缓存档**。早先实现里 `~/.stm32cubemx2-chinese/localization.cache.json`
    排在内置词典之前，而它是在 `fetch_remote()` 里顺手写的 —— 意味着用户只是
    「检查了一下更新」，就被钉死在那一刻的词典版本上，之后装再新的 EXE 读的还是
    旧缓存。`update_dict()` 本来就会把确认要用的词典写进用户目录，缓存那份
    纯属重复且只会造成错乱，故整档删除。
    """
    from . import paths

    if external and external.is_file():
        return load_json_file(external), f"external:{external}"

    # 用户词典（EXE 旁或 %LOCALAPPDATA%）：--update-dict 写在这里，应优先使用
    user = paths.user_dict_path()
    if user.is_file():
        try:
            d = load_json_file(user)
        except (OSError, json.JSONDecodeError):
            d = None
        if is_current_format(d):
            return d, f"user:{user}"
        # 格式不对（多半是升级前留下的旧版片段词典）—— 不能用，但要说出来
        note = f"user:{user} (旧格式，已忽略)"
    else:
        note = ""

    if prefer_remote:
        try:
            return fetch_remote(remote_url), f"remote:{remote_url}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            pass

    bundled = bundled_dict_path()
    if bundled.is_file():
        d = load_json_file(bundled)
        if note:
            return d, f"{note} -> bundled"
        return d, f"bundled:{bundled}"

    # 最后再试一次远程
    return fetch_remote(remote_url), f"remote:{remote_url}"


def current_pack(dict_path: Path | None = None) -> tuple[dict[str, str], str]:
    """当前生效词典构建出的语言包，以及词典来源说明。

    `main.py` 和 `tools/` 下那批验证脚本都从这里取表 —— 语言包不再是磁盘上的
    文件了，各处自己 `json.load` 一份旧产物会导致验证结果和实际注入内容不一致。
    """
    from . import langpack

    d, src = resolve_dictionary(dict_path)
    if not is_current_format(d):
        raise RuntimeError(
            f"词典 {src} 不是扁平 entries 格式（多半是旧版字节片段词典残留）"
        )
    pack, _rep = langpack.build(d)
    if not pack:
        raise RuntimeError(f"词典 {src} 构建不出任何语言包条目")
    return pack, src
