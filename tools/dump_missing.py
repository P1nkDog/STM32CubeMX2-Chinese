#!/usr/bin/env python
"""把「未覆盖文案」导出成 CSV，供人工翻译。

未覆盖清单是按 i18n 调用点统计的**真实英文原文**，所以这份表可以直接翻，
填完并进词典的 entries 即可，不需要再猜正则。

用法::

    python tools/dump_missing.py -g C:/mysoftware/cubemx2 -o missing.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import dictionary, locate  # noqa: E402
from core import i18n as i18n_mod  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="导出未覆盖的 i18n 文案")
    ap.add_argument("-g", "--path", required=True,
                  help="CubeMX2 安装目录（指到 dist/app 那一层也行）")
    ap.add_argument("-o", "--out", default="missing.csv", help="输出 CSV 路径")
    ap.add_argument("--limit", type=int, default=0, help="只导出前 N 条（0=全部）")
    args = ap.parse_args(argv)

    root = locate.root_from_arg(args.path)
    if root is None:
        print(f"[错误] 不是有效的安装目录: {args.path}")
        return 1
    app = locate.app_dir(root)
    if not app:
        print("[错误] 未找到 app 目录")
        return 1

    try:
        pack, src = dictionary.current_pack()
        print(f"词典: {src} -> 语言包 {len(pack):,} 条")
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 取语言包失败: {e}")
        return 1

    rows = i18n_mod.missing_report(app, pack)
    if args.limit:
        rows = rows[: args.limit]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["en", "zh", "hits", "len", "has_placeholder", "skip", "note"])
        for lit, hits in rows:
            w.writerow(
                [
                    lit,
                    "",
                    hits,
                    len(lit),
                    1 if "{" in lit else 0,
                    "",
                    "",
                ]
            )
    print(f"已导出 {len(rows)} 条未覆盖文案: {out}")
    print("填好 zh 列后，把非空行并进 dict/localization.json 的 entries，")
    print("再执行 --patch 即可生效（语言包每次汉化现场构建，没有单独的构建步骤）。")
    print("也可以先 --export-dict 导出工作副本，改完 --import-dict 固化回仓库。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
