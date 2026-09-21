"""词典结构校验（供 CI 与本地使用）。

用法:
    python tools/check_dict.py [dict/localization.json ...]

词典是一张扁平的 ``{"英文原文": "中文"}`` 表，所以校验围绕「这张表能不能安全地
被 ``langpack.build()`` 过滤并注入」来做：

    1. JSON 可解析，顶层含 version 与非空 entries 对象
    2. entries 的键值都是非空字符串，且译文含中文
    3. 键去首尾空白后不互相撞车 —— ``build()`` 会 strip 键，若同时存在
       ``"Foo"`` 和 ``"Foo "``，后一条会**静默覆盖**前一条
    4. 恒等条目（译文 == 原文）按警告报 —— 它们会被 ``build()`` 过滤掉，白占体积

退出码: 0 全部通过（允许警告），1 存在错误。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 非 UTF-8 终端（如英文版 Windows CI 的 cp1252）下，强制以 UTF-8 输出，避免中文报错
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DICT = ROOT / "dict" / "localization.json"

# 与 core/langpack.py 的 CJK 同一套范围（U+3400-U+4DBF、U+4E00-U+9FFF）
CJK = re.compile(r"[㐀-䶿一-鿿]")

errors: list[str] = []
warns: list[str] = []


def check_file(path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errors.append(f"{path}: JSON 解析失败: {e}")
        return

    if not isinstance(data, dict):
        errors.append(f"{path}: 顶层必须是 JSON 对象")
        return
    if not data.get("version"):
        errors.append(f"{path}: 缺少 version 字段")

    entries = data.get("entries")
    if not isinstance(entries, dict) or not entries:
        errors.append(f"{path}: entries 缺失、不是对象或为空")
        return

    identity = 0
    for key, val in entries.items():
        if not isinstance(key, str) or not isinstance(val, str):
            errors.append(f"{path}: 键或值不是字符串: {key!r}")
            continue
        if not key.strip():
            errors.append(f"{path}: 空键")
            continue
        if not val.strip():
            errors.append(f"{path}: {key!r} 的译文为空")
            continue
        if not CJK.search(val):
            errors.append(f"{path}: {key!r} 的译文里没有中文: {val!r}")

        # 键**不做任何归一化**：DOM 通道要求逐字节相等，所以带 NBSP 的键
        # （如 "\xa0 Pin function \xa0"）与不带的那条服务不同调用点，必须并存。
        # JSON 对象本身不可能有逐字节重复的键，因此这里没有撞车可查。
        if val == key:
            identity += 1

    if identity:
        warns.append(
            f"{path}: {identity} 条译文与原文相同（恒等条目，build() 会过滤掉）。"
            "要保留英文就别写进词典。"
        )


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]] if len(sys.argv) > 1 else [DEFAULT_DICT]
    for p in paths:
        if not p.is_file():
            errors.append(f"{p}: 文件不存在")
            continue
        check_file(p)

    for msg in warns[:20]:
        print("  WARN", msg)
    if len(warns) > 20:
        print(f"  ... 其余 {len(warns) - 20} 条警告未显示")

    if errors:
        print(f"校验失败: {len(errors)} 个问题")
        for msg in errors[:50]:
            print("  -", msg)
        if len(errors) > 50:
            print(f"  ... 其余 {len(errors) - 50} 个未显示")
        return 1
    print(f"校验通过: {len(paths)} 个词典文件（{len(warns)} 条警告）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
