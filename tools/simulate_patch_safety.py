"""模拟替换：检查每条是否破坏 JS 结构。"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(r"D:\project\python\STM32CubeMX2-Chinese")
DICT = ROOT / "localization.json"
ORIG = Path(
    r"C:\mysoftware\cubemx2\resources\stm32cubemx-application\1.1.1\dist\resources\app\lib\frontend\bundle.js.orig"
)
orig = ORIG.read_bytes()
d = json.loads(DICT.read_text(encoding="utf-8"))
entries = d["files"]["lib/frontend/bundle.js"]["entries"]

# 结构指标
def metrics(b: bytes) -> tuple[int, int, int, int]:
    return (
        b.count(b"("),
        b.count(b")"),
        b.count(b'"'),
        len(b),
    )

base = metrics(orig)
print("orig", base)

bad = []
for e in entries:
    en = e["en"].encode("utf-8")
    zh = e["zh"].encode("utf-8")
    if orig.count(en) == 0:
        continue
    # 单条替换后括号/引号变化是否合理
    # en 和 zh 的引号数应一致（或 zh 多/少 0）
    if en.count(b'"') != zh.count(b"\""):
        bad.append((e["id"], "quote-delta", en[:50], zh[:50]))
    # 替换后括号差
    # 模拟
    out = orig.replace(en, zh)
    m = metrics(out)
    if (m[0] - m[1]) != (base[0] - base[1]):
        bad.append((e["id"], "paren-diff", (m[0]-m[1]), (base[0]-base[1]), en[:40]))

print("bad", len(bad))
for x in bad[:40]:
    print(x)

# 列出全部 shot.*
print("=== shot.* ===")
for e in entries:
    if e["id"].startswith("shot."):
        print(e["id"], "|", e["en"][:60], "|", e["zh"][:50])
