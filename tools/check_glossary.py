"""术语门禁的命令行入口（本地核对用）。

检查逻辑在 `core/glossary.py` —— 那也是 `main.py --patch` 落盘前调用的同一份。
本文件只负责「取到即将注入的语言包 -> 打印报告 -> 决定退出码」，这样命令行核对的
和 EXE 里跑的不是两套规则。

用法::

    python tools/check_glossary.py            # 检查当前词典构建出的语言包，违规即非零退出
    python tools/check_glossary.py -v         # 连通过项一起打印
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import dictionary, glossary, paths  # noqa: E402


def main(argv: list[str]) -> int:
    verbose = "-v" in argv or "--verbose" in argv

    try:
        pack, src = dictionary.current_pack()
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] 取语言包失败: {e}")
        return 2

    rep = glossary.run(pack)
    if rep is None:
        print(f"[FAIL] 缺少术语表: {paths.bundled_glossary_path()}")
        return 2

    print(f"词典: {src} -> 语言包 {len(pack):,} 条")
    print(rep.brief(verbose))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
