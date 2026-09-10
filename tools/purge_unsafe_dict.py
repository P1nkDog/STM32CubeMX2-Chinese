"""彻底清理词典中会弄坏 JS 的条目，只保留可安全替换的。"""
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

DROP_SUBSTR = [
    "and move left/right to scroll horizontally",
    "and move up/down to scroll vertically",
    "to zoom out/in",
    "Hold 2 fingers",
    "Hold Ctrl key and hold 2 fingers",
    "`Search for any",
    "Press any of Page",
    "Press Tab key",
    "Press Enter key",
    "Press Escape key",
    "Press Home key",
    "Press ←Backspace",
    "Hold Space key",
    "Hold Middle mouse",
    "Click and Hold Middle",
    "Pinch open",
    "Pinch close",
    "Press Ctrl Alt",
    "Press Alt Ctrl",
    "Use Mouse wheel",
    "Hold Shift key and use Mouse",
]

def is_unsafe(en: str, zh: str) -> str | None:
    blob = en + " " + zh
    for s in DROP_SUBSTR:
        if s in en:
            return f"drop-substr:{s[:30]}"
    # 裸英文短语（无引号无前缀）却包了 label/title
    if (
        '"' not in en
        and " " in en
        and not en.startswith("localizeByDefault(")
        and not en.startswith("registerSubmenu(")
        and not en.startswith("nls.localize(")
        and not en.startswith("static LABEL")
        and zh.startswith(('label:"', 'title:"', 'header:"', 'tooltip:"', 'placeholder:"'))
    ):
        return "bare-phrase-wrapped"
    # en 含引号数与 zh 不一致，且不是已知合法包装
    if en.count('"') != zh.count('"'):
        # 三元 ?"A":"B" -> ?"中文":"中文" 引号数应相等
        return f"quote-mismatch en={en.count(chr(34))} zh={zh.count(chr(34))}"
    # 模板
    if "${" in en or en.startswith("`"):
        return "template"
    found = orig.count(en.encode("utf-8"))
    if found == 0:
        return "not-in-orig"
    if found > 30 and len(en) < 20:
        return f"too-broad({found})"
    return None

keep, drop = [], []
for e in entries:
    reason = is_unsafe(e["en"], e["zh"])
    if reason:
        drop.append((e["id"], reason, e["en"][:55], e["zh"][:40]))
    else:
        keep.append(e)

print(f"drop {len(drop)} keep {len(keep)}")
for x in drop[:30]:
    print(" DROP", x)
d["files"]["lib/frontend/bundle.js"]["entries"] = keep
DICT.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("saved", DICT)
