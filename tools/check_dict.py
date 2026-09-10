"""词典结构校验（供 CI 与本地使用）。

用法:
    python tools/check_dict.py [dict/localization.json ...]

校验项:
    1. JSON 可解析，顶层含 version、files
    2. 每个文件配置含 entries 列表
    3. 每条 entry 含 id / en / zh / expect，mode 合法
    4. en 与 zh 引号数量一致（防破坏 JS 结构）

退出码: 0 全部通过，1 存在错误。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DICT = ROOT / "dict" / "localization.json"
VALID_MODES = {"literal"}

errors: list[str] = []


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
    if not isinstance(data.get("files"), dict):
        errors.append(f"{path}: 缺少 files 对象")
        return

    for rel, file_cfg in data["files"].items():
        if not isinstance(file_cfg, dict):
            errors.append(f"{path}: files.{rel} 不是对象")
            continue
        entries = file_cfg.get("entries")
        if not isinstance(entries, list) or not entries:
            errors.append(f"{path}: files.{rel}.entries 缺失或为空")
            continue
        for i, e in enumerate(entries):
            loc = f"{path}: files.{rel}.entries[{i}]"
            if not isinstance(e, dict):
                errors.append(f"{loc} 不是对象")
                continue
            if not e.get("id"):
                errors.append(f"{loc} 缺少 id")
            if not e.get("en"):
                errors.append(f"{loc} 缺少 en")
            if not e.get("zh"):
                errors.append(f"{loc} 缺少 zh")
            if "expect" not in e or not isinstance(e.get("expect"), int):
                errors.append(f"{loc} expect 缺失或非整数")
            if e.get("mode", "literal") not in VALID_MODES:
                errors.append(f"{loc} mode 非法: {e.get('mode')!r}")
            if e.get("en") and e.get("zh") and e["en"].count('"') != e["zh"].count('"'):
                errors.append(f"{loc} en/zh 引号数量不一致: {e.get('id')!r}")


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]] if len(sys.argv) > 1 else [DEFAULT_DICT]
    for p in paths:
        if not p.is_file():
            errors.append(f"{p}: 文件不存在")
            continue
        check_file(p)

    if errors:
        print(f"校验失败: {len(errors)} 个问题")
        for msg in errors[:50]:
            print("  -", msg)
        if len(errors) > 50:
            print(f"  ... 其余 {len(errors) - 50} 个未显示")
        return 1
    print(f"校验通过: {len(paths)} 个词典文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
