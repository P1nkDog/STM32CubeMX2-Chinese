"""词典 -> 注入用语言包。

词典（`dict/localization.json`）本身就是一张扁平的
``{"英文原文": "中文"}`` 表，和框架 ``localization.replacements`` 要的形状一致，
所以这里**不再有任何合成/还原步骤**，只做「可用性过滤」和「序列化成 JS 字面量」。

历史上这一层负责把「字节片段词典」（`,"Cancel")` 那种形态）连同 CSV、supplement
三轮合成成扁平表。v0.2.0 把扁平表扶正为词典本身之后，那套机器全部删除：
键已经是界面原文，不需要还原。

保留过滤而不是直接透传，是因为词典里可能混进不该注入的键（路径、模块 id、
纯符号、含 U+FFFD 的解码残骸），以及没真正翻译的恒等条目。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

LOCALE_ID = "zh-cn"
LOCALE_NAME = "Chinese (Simplified)"
LOCALE_NATIVE_NAME = "简体中文"

# 源串长度上限。这张表同时喂两条通道：
#   i18n 通道（框架 i18n）：键是界面短标签
#   DOM 通道（DOM 兜底）：整串精确匹配，键可能是几百字的面板 description
# 取 4000（与 assets/dom-translate.js 的 MAX_LEN_LONG 对齐）。
MAX_SOURCE_LEN = 4000

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
HAS_LATIN = re.compile(r"[A-Za-z]")

# 明显不是界面文案的源串（路径 / 模块 id / 纯符号）
_BAD_SOURCE = re.compile(
    r"^(?:"
    r"[A-Za-z0-9_]{16,}"  # 随机 id / 哈希
    r"|https?://"
    r"|\./|/lib/|/src/|\.js$|\.json$|\.html$|\.css$|\.png$"
    r"|theia-console-content"
    r")$"
)

# JS 转义序列
_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "0": "\0",
}


def js_unescape(text: str) -> str:
    """还原 JS 字符串字面量里的转义序列（不含首尾引号）。

    供 `i18n` 从 bundle 里抠 i18n 调用点时解码字面量用。
    """
    if "\\" not in text:
        return text
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != "\\" or i + 1 >= n:
            out.append(ch)
            i += 1
            continue
        nxt = text[i + 1]
        if nxt in _ESCAPES:
            out.append(_ESCAPES[nxt])
            i += 2
        elif nxt == "x" and i + 3 < n:
            try:
                out.append(chr(int(text[i + 2 : i + 4], 16)))
                i += 4
            except ValueError:
                out.append(ch)
                i += 1
        elif nxt == "u":
            if i + 2 < n and text[i + 2] == "{":
                end = text.find("}", i + 3)
                if end > 0:
                    try:
                        out.append(chr(int(text[i + 3 : end], 16)))
                        i = end + 1
                        continue
                    except ValueError:
                        pass
            try:
                out.append(chr(int(text[i + 2 : i + 6], 16)))
                i += 6
            except ValueError:
                out.append(nxt)
                i += 2
        elif nxt == "\n":  # 行继续
            i += 2
        elif nxt == "\r":
            i += 3 if text[i + 2 : i + 3] == "\n" else 2
        else:
            out.append(nxt)
            i += 2
    return "".join(out)


@dataclass
class BuildReport:
    """构建统计。"""

    total: int = 0
    kept: int = 0
    dropped: dict[str, int] = field(default_factory=dict)

    def brief(self) -> str:
        return f"语言包条目: {self.kept} 条（词典共 {self.total} 条，跳过: {self.dropped or '无'}）"


def _is_usable_source(src: str) -> bool:
    if not (2 <= len(src) <= MAX_SOURCE_LEN):
        return False
    if not HAS_LATIN.search(src):
        return False
    if _BAD_SOURCE.match(src.strip()):
        return False
    if "\ufffd" in src:
        return False
    return True


def _is_usable_target(tgt: str, src: str) -> bool:
    """译文必须非空、含中文、且不等于原文（恒等条目注入进来只会白占体积）。"""
    if not tgt or tgt == src:
        return False
    if not CJK.search(tgt):
        return False
    return True


def build(dictionary: dict) -> tuple[dict[str, str], BuildReport]:
    """从词典对象构建注入用的扁平语言包。纯过滤，不做任何还原或改写。

    **键一律原样保留，不 strip。** 有些键故意带不换行空格（NBSP），因为界面上
    显示的文本就含 NBSP（如 ``"\\xa0 Pin function \\xa0"``），而 DOM 兜底通道做的是
    逐字节整串匹配 —— 一旦在这里把键「顺手清理」成 ``"Pin function"``，这四条
    引脚相关的词条就永远命中不了。键写错就该报错，不要自动纠正。
    """
    rep = BuildReport()
    pack: dict[str, str] = {}
    dropped: dict[str, int] = {}
    entries = dictionary.get("entries") or {}
    rep.total = len(entries)

    for src, tgt in entries.items():
        if not isinstance(src, str) or not isinstance(tgt, str):
            dropped["键或值不是字符串"] = dropped.get("键或值不是字符串", 0) + 1
            continue
        if not _is_usable_source(src):
            dropped["源串不可用"] = dropped.get("源串不可用", 0) + 1
            continue
        if not _is_usable_target(tgt, src):
            dropped["译为空/未翻译/无中文"] = dropped.get("译为空/未翻译/无中文", 0) + 1
            continue
        pack[src] = tgt

    rep.kept = len(pack)
    rep.dropped = dropped
    return pack, rep


def load_dictionary(path: Path) -> dict:
    """读词典文件。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def js_literal(pack: dict[str, str]) -> str:
    """把语言包序列化成可直接内嵌的 JS 对象字面量。

    - 用紧凑分隔符省体积
    - 转义 U+2028/U+2029（旧解析器在字符串里不接受它们）
    - 键排序，保证同一词典产出同一份字节，便于 diff 与幂等校验
    """
    text = json.dumps(pack, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return (
        text.replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
        .replace("</", "<\\/")
    )


def stats(pack: dict[str, str]) -> dict:
    lengths = [len(k) for k in pack]
    return {
        "count": len(pack),
        "bytes": len(js_literal(pack).encode("utf-8")),
        "avg_src_len": round(sum(lengths) / max(len(lengths), 1), 1),
        "max_src_len": max(lengths) if lengths else 0,
        "placeholders": sum(1 for k in pack if re.search(r"\{\d+\}", k)),
    }
