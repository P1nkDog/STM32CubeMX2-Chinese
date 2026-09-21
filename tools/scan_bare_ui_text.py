"""扫描「界面上的裸字符串但语言包里没有」的文案，导出成 CSV 供翻译。

为什么需要它
------------
``tools/dump_missing.py`` 只看**走了 i18n 调用的**字面量（i18n 通道的覆盖范围）。
但 ST 自绘界面大量使用**裸字符串**直接当 React 子节点 / 属性值：

    createElement(Button, {...}, "Reset pins")
    leftLabel:"Graphic view", rightLabel:"Table view"

这些既不在 i18n 调用点里，也不会被基于调用点的统计发现，只能靠
「源码字面量 - 语言包」这个差集来找。本工具就是做这个差集。

判定范围刻意收得很紧（宁可漏，不要给翻译者一堆噪音）：
  * 只取**参数/属性位置**的字面量（前一个字符是 ``(`` / ``,`` / ``:``，
    后一个字符是 ``)`` / ``,`` / ``}``），避免抓到正文、日志、URL；
  * 只取首字母大写、含空格、长度 3~80 的（界面标签的典型形态）；
  * 只允许常规标点（出现 ``{`` ``}`` ``;`` ``=`` ``$`` ``\\`` 的一律丢掉）；
  * 已经在语言包里的（原样或去首尾空白后）直接排除。

用法::

    python tools/scan_bare_ui_text.py -g <安装根目录> [-o bare-missing.csv]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import dictionary, i18n, langpack, locate  # noqa: E402

# 参数 / 属性位置的字面量：前一个字符是 ( , :  后一个字符是 ) , }
LITERAL = re.compile(
    r"""(?<=[(,:])\s*(?P<q>["'])(?P<v>(?:[^"'\\]|\\.){3,120})(?P=q)(?=\s*[),}])"""
)

BLANK = "\u00a0\u200b \t\r\n"

# 出现这些字符的，基本不是界面标签
BAD_CHARS = re.compile(r"[{};=$`\\<>|@#*\[\]]|\bhttps?://|\bwww\.")

# 上下文特征：用来给候选打分。界面标签几乎总出现在这些位置附近，
# 而错误/日志消息则出现在 Error( / console. / 带 %s 占位符的地方。
UI_CTX = re.compile(
    r"createElement\(|className:|title:|label:|placeholder:|aria-label"
    r"|data-testid|leftLabel|rightLabel|header:|tooltip:|variant:"
)
MSG_CTX = re.compile(r"\bnew\s+Error\(|\bError\(|\bassert\b|throw\s|console\.|warn\(|%[sdif]\b")

# 句末句号 + 很长 => 多半是日志/描述句而非标签
SENTENCE = re.compile(r"\.\s*$")

# 纯技术标识：没有空格、或全大写、或像文件/模块名
TECHNICAL = re.compile(r"^[A-Za-z0-9_.\-:/]+$")


def strip_metadata(text: str) -> str:
    """剥掉内嵌的 VS Code nls 元数据块（``JSON.parse(<巨大字符串字面量>)``）。

    这个坑值得记：**10 个目标文件里每一个都内嵌了一份完整元数据**（约 1354 条
    key→英文），不剥掉的话同一句英文会被重复统计 10 遍，排序完全失真。
    另外元数据里的英文本来就以 i18n 调用的形式出现，
    已经在 ``tools/dump_missing.py`` 的统计范围内，这里不必重复报。
    """
    for m in re.finditer(r"JSON\.parse\(", text):
        i = m.end()
        while i < len(text) and text[i] in " \t":
            i += 1
        if i >= len(text) or text[i] not in "\"'`":
            continue
        quote = text[i]
        j = i + 1
        while j < len(text):
            c = text[j]
            if c == "\\":
                j += 2
                continue
            if c == quote:
                break
            j += 1
        if j - i > 20000:  # 只有元数据才这么大
            return strip_metadata(text[:i] + quote + quote + text[j + 1 :])
    return text


def is_ui_text(s: str) -> bool:
    if not (3 <= len(s) <= 80):
        return False
    if s[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        return False
    if BAD_CHARS.search(s):
        return False
    if not any(c.isspace() for c in s):  # 界面标签基本都带空格
        return False
    if TECHNICAL.match(s):  # 无空格的路径/模块名
        return False
    if not any(c.islower() for c in s):  # 全大写 => 日期格式/缩写表，不是标签
        return False
    if SENTENCE.search(s) and len(s) > 45:  # 长句多半是日志/说明
        return False
    if s.startswith(("./", "../", "/")):
        return False
    return True


def js_decode(s: str) -> str:
    return langpack.js_unescape(s)


def scan(app_dir: Path, pack: dict[str, str]) -> list[dict]:
    """返回 [{en, count, files, context}]，按出现次数降序。"""
    found: dict[str, dict] = {}
    for target in i18n.TARGETS:
        path = app_dir / target.rel
        if not path.is_file():
            continue
        # 用 .orig 基线：已注入的文件里混着我们的中文表，会污染统计
        base = path.with_name(path.name + ".orig")
        src = base if base.is_file() else path
        text = strip_metadata(src.read_text(encoding="utf-8", errors="replace"))

        for m in LITERAL.finditer(text):
            raw = m.group("v")
            if m.group("q") == '"' and "'" in raw:
                continue
            s = js_decode(raw)
            if not is_ui_text(s):
                continue
            # 包里已有（原样 / 去首尾空白）就跳过
            if s in pack or s.strip(BLANK) in pack:
                continue
            rec = found.setdefault(
                s,
                {"en": s, "count": 0, "files": set(), "context": "", "score": 0},
            )
            rec["count"] += 1
            rec["files"].add(target.rel)
            before = text[max(0, m.start() - 80) : m.start()]
            if not rec["context"]:
                lo = max(0, m.start() - 60)
                rec["context"] = text[lo : m.end() + 10].replace("\n", " ")
            # 界面标签 +3，错误/日志消息 -4（只在第一次见到时评估一次）
            if rec["score"] == 0:
                score = 0
                if UI_CTX.search(before):
                    score += 3
                if MSG_CTX.search(before):
                    score -= 4
                rec["score"] = score
    out = []
    for rec in found.values():
        rec["files"] = ",".join(sorted(rec["files"]))
        out.append(rec)
    # 先按「像不像界面标签」排，再按出现次数
    out.sort(key=lambda r: (-r["score"], -r["count"], r["en"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="导出界面裸字符串缺口")
    ap.add_argument(
        "-g",
        "--path",
        required=True,
        help="CubeMX2 安装目录（指到 dist/app 那一层也行）",
    )
    ap.add_argument("-o", "--out", default="bare-missing.csv", help="输出 CSV")
    ap.add_argument("--top", type=int, default=40, help="终端里预览多少条")
    ap.add_argument(
        "--dict",
        default=None,
        help="词典路径（默认按 resolve_dictionary 的优先级取当前生效那份）",
    )
    args = ap.parse_args()

    try:
        pack, dict_src = dictionary.current_pack(Path(args.dict) if args.dict else None)
    except Exception as e:  # noqa: BLE001
        print(f"取语言包失败: {e}")
        return 2
    print(f"词典: {dict_src} -> 语言包 {len(pack):,} 条")

    root = locate.root_from_arg(args.path)
    if root is None:
        print(f"[错误] 不是有效的安装目录: {args.path}")
        return 2
    app_dir = locate.app_dir(root)
    if app_dir is None:
        print(f"在 {root} 下没找到 CubeMX2 应用目录")
        return 2

    rows = scan(app_dir, pack)
    out = Path(args.out)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["en", "zh", "ui_score", "count", "files", "context"])
        for r in rows:
            w.writerow([r["en"], "", r["score"], r["count"], r["files"], r["context"]])

    print(f"语言包条目: {len(pack)}")
    print(f"未覆盖的裸字符串: {len(rows)} 条 → {out}")
    print()
    print(f"最像界面标签的 {args.top} 条（ui_score 高 = 大概率是界面文案）:")
    print(f"{'分':>3}{'次数':>6}  {'英文原文':<44}{'文件'}")
    print("-" * 96)
    for r in rows[: args.top]:
        en = r["en"] if len(r["en"]) <= 42 else r["en"][:41] + "…"
        files = r["files"].replace("lib/frontend/", "").replace("lib/backend/", "")
        print(f"{r['score']:>3}{r['count']:>6}  {en:<44}{files}")
    print()
    print("补法：把确认要翻的条目并进 dict/localization.json 的 entries（键=界面英文原文，")
    print("      值=中文），然后 python main.py --patch -g <安装目录>。")
    print("      也可以 python main.py --export-dict 导出工作副本改完再 --import-dict。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
