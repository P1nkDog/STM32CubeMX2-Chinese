"""从 ST 配置描述符（``.config/*_parameters.json``）里抽出全部界面文案。

为什么需要这个工具
------------------
2026-09-19 定位到「ST 配置面板整页英文」的真正源头：

    C:\\Users\\<用户>\\AppData\\Local\\stm32cube\\packs\\STMicroelectronics\\
        <pack>\\<版本>\\.config\\<外设>_parameters.json

CubeMX2 的前端只是一个**通用渲染器** —— 它按描述符里的
``properties.*.title`` / ``description`` / ``oneOf[].title`` 画控件，
所以 MPU / PWR / GPIO / RCC… 各面板的标签、选项、提示全都是**数据**，
不在 bundle.js 里，静态扫描 bundle 永远扫不到（之前误判为「运行时数据」）。

这份描述符才是权威清单：按它枚举，一次能把某个外设面板**穷尽**，
不必再靠用户截图一轮一轮补。

用法::

    python tools/extract_st_params.py                 # 汇总统计 + 写 st-params-extract.csv
    python tools/extract_st_params.py --missing       # 只列尚未收录的
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 描述符所在位置（随用户而异，故按候选顺序探测）
PACK_ROOTS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "stm32cube" / "packs",
    Path.home() / "AppData" / "Local" / "stm32cube" / "packs",
]

# 收集哪些字段：
#   title / description  —— 控件标签、选项名、ⓘ 提示
#   message              —— actions 里的校验消息（出现在提示气泡与消息面板）
TITLE_KEYS = ("title",)
DESC_KEYS = ("description", "message")


def find_descriptors() -> list[Path]:
    out: list[Path] = []
    for root in PACK_ROOTS:
        if not root.is_dir():
            continue
        for pack in sorted(root.glob("*/*")):
            if not pack.is_dir():
                continue
            for ver in sorted(pack.iterdir()):
                cfg = ver / ".config"
                if cfg.is_dir():
                    out.extend(sorted(cfg.glob("*_parameters.json")))
    # 去重（符号链接 / 多候选根目录可能重复）
    seen: dict[str, Path] = {}
    for p in out:
        seen.setdefault(str(p).lower(), p)
    return list(seen.values())


def walk(node, titles: list[str], descs: list[str], path: str = "") -> None:
    """递归收集 title / description；数组下标用 [] 归一化，便于跨外设聚合。"""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in TITLE_KEYS and isinstance(v, str):
                titles.append(v)
            elif k in DESC_KEYS and isinstance(v, str):
                descs.append(v)
            else:
                walk(v, titles, descs, path)
    elif isinstance(node, list):
        for v in node:
            walk(v, titles, descs, path + "[]")


def looks_translatable(s: str) -> bool:
    """排除标识符 / 寄存器名 / 纯符号 —— 那些不该翻译。

    注意：**不要用「长度 ≤6 且非全小写」当过滤条件** —— 那会把
    ``Device`` / ``Normal`` / ``Master`` 这类只有一个词的**真标签**一起滤掉
    （2026-09-19 踩过：MPU 的 Memory type 两个选项凭空消失）。
    只按「形态」判断：含空格的多半是文案；不含空格的，只有全大写、
    含下划线、或纯十六进制/数字的才当标识符丢掉。
    """
    t = s.strip()
    if len(t) < 2:
        return False
    if not any(c.isalpha() for c in t):
        return False
    if any("\u4e00" <= c <= "\u9fff" for c in t):
        return False          # 描述符里已经是中文（不该发生）
    if " " in t:
        return True           # 含空格 → 文案
    # 单个词：全大写（HAL/ADC/NGNRNE）、蛇形（ATTR_0）、纯十六进制 → 标识符
    if t.isupper():
        return False
    if "_" in t:
        return False
    if re.fullmatch(r"0[xX][0-9A-Fa-f]+|\d+", t):
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing", action="store_true", help="只列尚未收录的")
    ap.add_argument("--out", default=str(ROOT / "st-params-extract.csv"))
    args = ap.parse_args()

    defs = find_descriptors()
    if not defs:
        print("[错误] 未找到 *_parameters.json 描述符")
        print("       候选目录:", *[str(p) for p in PACK_ROOTS], sep="\n         ")
        return 1

    # 已收录的英文原文（当前词典构建出的语言包 + 参数表）
    known: set[str] = set()
    try:
        from core import dictionary

        known |= set(dictionary.current_pack()[0])
    except Exception:  # noqa: BLE001
        pass
    p = ROOT / "dict" / "st-params.zh.json"
    if p.is_file():
        known |= set(json.loads(p.read_text(encoding="utf-8")))

    rows: list[tuple[str, str, str]] = []
    for d in defs:
        try:
            obj = json.loads(d.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:  # noqa: BLE001
            print(f"[警告] 读取失败 {d.name}: {e}", file=sys.stderr)
            continue
        titles: list[str] = []
        descs: list[str] = []
        walk(obj, titles, descs)
        for kind, seq in (("title", titles), ("desc", descs)):
            for s in dict.fromkeys(seq):          # 去重且保序
                if not looks_translatable(s):
                    continue
                rows.append((d.name, kind, s))

    # 按英文原文去重，合并来源
    merged: dict[str, dict] = {}
    for f, kind, s in rows:
        e = merged.setdefault(s, {"kinds": set(), "files": set()})
        e["kinds"].add(kind)
        e["files"].add(f)

    miss = {s: v for s, v in merged.items() if s not in known}

    print(f"描述符文件: {len(defs)} 个")
    print(f"可翻译文案（去重后）: {len(merged)} 条")
    print(f"  其中标题/标签: {sum(1 for v in merged.values() if 'title' in v['kinds'])} 条")
    print(f"  其中说明/提示: {sum(1 for v in merged.values() if 'desc' in v['kinds'])} 条")
    print(f"尚未收录: {len(miss)} 条（已收录 {len(merged) - len(miss)} 条）")

    out = Path(args.out)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["en", "zh", "kind", "files", "covered"])
        for s in sorted(merged):
            v = merged[s]
            w.writerow([
                s,
                "",
                "/".join(sorted(v["kinds"])),
                " ".join(sorted(v["files"])),
                "yes" if s in known else "",
            ])
    print(f"已写出: {out}")

    if args.missing:
        print()
        for s in sorted(miss):
            print(s if len(s) <= 100 else s[:97] + "...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
