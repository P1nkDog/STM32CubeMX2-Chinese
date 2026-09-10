"""全量 CSV 导出 / 回灌（人工翻译工作流）。"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .locate import bundle_js_path
from . import paths as app_paths

PATTERNS = [
    ("localizeByDefault", re.compile(r'localizeByDefault\("([^"\\]{1,120})"\)')),
    ("registerSubmenu", re.compile(r'registerSubmenu\([^,]{0,80},\s*"([^"\\]{1,60})"\)')),
    ("label", re.compile(r'\blabel\s*:\s*"([^"\\]{1,120})"')),
    ("title", re.compile(r'\btitle\s*:\s*"([^"\\]{1,120})"')),
    ("tooltip", re.compile(r'\btooltip\s*:\s*"([^"\\]{1,140})"')),
    ("header", re.compile(r'\bheader\s*:\s*"([^"\\]{1,140})"')),
    ("placeholder", re.compile(r'\bplaceholder\s*:\s*"([^"\\]{1,100})"')),
    ("ariaLabel", re.compile(r'\bariaLabel\s*:\s*"([^"\\]{1,100})"')),
    ("description", re.compile(r'\bdescription\s*:\s*"([^"\\]{1,160})"')),
    ("message", re.compile(r'\bmessage\s*:\s*"([^"\\]{1,160})"')),
    ("content", re.compile(r'\bcontent\s*:\s*"([^"\\]{1,100})"')),
    ("LABEL", re.compile(r'static LABEL\s*=\s*"([^"\\]{1,80})"')),
    ("LABEL", re.compile(r'\bLABEL\s*=\s*"([^"\\]{1,80})"')),
    ("nls.localize", re.compile(r'nls\.localize\(\s*"[^"]+"\s*,\s*"([^"\\]{1,120})"\s*[,)]')),
    # React 子节点：,"Some UI text")
    ("text", re.compile(r',\s*"([^"\\]{2,100})"\s*\)')),
    # 双标签切换
    ("leftLabel", re.compile(r'\bleftLabel\s*:\s*"([^"\\]{2,80})"')),
    ("rightLabel", re.compile(r'\brightLabel\s*:\s*"([^"\\]{2,80})"')),
    # 三元 tooltip：?"Close X":"Open X"
    ("ternary", re.compile(r'\?\s*"([^"\\]{2,60})"\s*:\s*"([^"\\]{2,60})"')),
]

# 子节点/三元的噪声过滤
TEXT_NOISE = re.compile(
    r"https?://|@prg-cube|theia/|vscode\.|webpack|Error:|node_modules|"
    r"background color|border color|foreground|ansi |"
    r"breakpoint|call stack|source control|marketplace|keybinding|telemetry|"
    r"activity bar|high contrast|color theme|"
    r"\.js$|\.json$|\.png$|data-testid|codicon|\$\{|"
    r"^Mui[A-Z]|^(true|false|null|undefined)$|"
    r"icon_|surface_|text_|primary_|secondary_|"
    r"^(left|right|top|bottom|width|height|string|hash|tap|thru)$|"
    r"^(enabled|registered|changed|many-changed|decrement|increment)$|"
    r"^(error|warn|info|debug)$|"
    r"^Group [0-9]|^Input [0-9]",
    re.I,
)

CJK = re.compile(r"[一-鿿]")
HAS_EN = re.compile(r"[A-Za-z]{2,}")

CSV_NAME = "manual-translate.csv"


def project_root() -> Path:
    return app_paths.exe_dir()


def dict_path() -> Path:
    """可写词典路径（用户目录）。"""
    return app_paths.user_dict_path()


def bundled_dict_source() -> Path:
    return app_paths.bundled_dict_path()


def default_csv_path() -> Path:
    return app_paths.csv_path()


def extract_inner_from_en(en: str) -> str:
    # React 子节点片段: ,"English")
    m = re.fullmatch(r'(?:,\s*)"([^"]+)"(?:\s*\))', en)
    if m:
        return m.group(1)
    # 三元: ?"Close X":"Open X" -> 取 Open X 作展示
    m = re.fullmatch(r'\?"([^"]+)"\s*:\s*"([^"]+)"', en)
    if m:
        return f"{m.group(1)} / {m.group(2)}"
    m = re.fullmatch(r':"([^"]+)"\s*:\s*"([^"]+)"', en)
    if m:
        return f"{m.group(1)} / {m.group(2)}"
    for rx in (
        r'localizeByDefault\("([^"]+)"\)',
        r'registerSubmenu\([^,]+,\s*"([^"]+)"\)',
        r'nls\.localize\(\s*"[^"]+"\s*,\s*"([^"]+)"\s*[,)]',
        r'static LABEL\s*=\s*"([^"]+)"',
        r'\bLABEL\s*=\s*"([^"]+)"',
        r'\b(?:label|title|tooltip|header|placeholder|ariaLabel|description|message|content)\s*=\s*"([^"]+)"',
        r'\b(?:label|title|tooltip|header|placeholder|ariaLabel|description|message|content)\s*:\s*"([^"]+)"',
    ):
        m = re.search(rx, en)
        if m:
            return m.group(1)
    if en.startswith('"') and en.endswith('"'):
        return en[1:-1]
    return en


def extract_inner_from_zh(zh: str) -> str:
    m = re.fullmatch(r'(?:,\s*)"([^"]+)"(?:\s*\))', zh)
    if m:
        return m.group(1)
    m = re.fullmatch(r'\?"([^"]+)"\s*:\s*"([^"]+)"', zh)
    if m:
        return f"{m.group(1)} / {m.group(2)}"
    m = re.fullmatch(r':"([^"]+)"\s*:\s*"([^"]+)"', zh)
    if m:
        return f"{m.group(1)} / {m.group(2)}"
    for rx in (
        r'localizeByDefault\("([^"]+)"\)',
        r'registerSubmenu\([^,]+,\s*"([^"]+)"\)',
        r'nls\.localize\(\s*"[^"]+"\s*,\s*"([^"]+)"\s*[,)]',
        r'static LABEL\s*=\s*"([^"]+)"',
        r'\bLABEL\s*=\s*"([^"]+)"',
        r'\b(?:label|title|tooltip|header|placeholder|ariaLabel|description|message|content)\s*=\s*"([^"]+)"',
        r'\b(?:label|title|tooltip|header|placeholder|ariaLabel|description|message|content)\s*:\s*"([^"]+)"',
    ):
        m = re.search(rx, zh)
        if m:
            return m.group(1)
    if zh.startswith('"') and zh.endswith('"'):
        return zh[1:-1]
    return zh


def wrap_zh(kind: str, en: str, zh: str) -> str | None:
    zh = zh.strip()
    if not zh:
        return None
    # zh 已是完整替换结构（带前缀/片段），直接使用
    if re.match(r'(,|\?|:)\s*"', zh) or zh.startswith(
        ("localizeByDefault(", "registerSubmenu(", "nls.localize(", "static LABEL")
    ):
        if zh.count('"') == en.count('"') or zh.startswith(
            ("localizeByDefault(", "registerSubmenu(", "nls.localize(", "static LABEL")
        ):
            return zh
    if re.search(r"(localizeByDefault|registerSubmenu|nls\.localize)\(", zh) or (
        '"' in zh and zh.endswith('"') and en.count('"') == zh.count('"')
    ):
        return zh
    if kind == "localizeByDefault":
        return f'localizeByDefault("{zh}")'
    if kind == "nls.localize":
        m = re.fullmatch(r'nls\.localize\(\s*("[^"]+")\s*,\s*"[^"]+"\s*[,)]', en)
        if m:
            return f'nls.localize({m.group(1)},"{zh}")'
        return None
    if kind == "registerSubmenu":
        m = re.fullmatch(r'(registerSubmenu\([^,]+,\s*)"[^"]+"\)', en)
        if m:
            return f'{m.group(1)}"{zh}")'
        return None
    if kind == "LABEL" or en.startswith("static LABEL"):
        if en.startswith("static LABEL"):
            return f'static LABEL="{zh}"'
        if en.startswith("LABEL="):
            return f'LABEL="{zh}"'
        return f'static LABEL="{zh}"'
    m = re.fullmatch(r'LABEL\s*=\s*"([^"]+)"', en)
    if m:
        return f'LABEL="{zh}"'
    # label="X" / title.label="X" / this.label="X"
    m = re.fullmatch(r'((?:[\w.]+\.)?label)\s*=\s*"([^"]+)"', en)
    if m:
        return f'{m.group(1)}="{zh}"'
    # 片段：,"English")  -> ,"中文")  （须在 kind 包装之前判断）
    m = re.fullmatch(r'(,\s*)"([^"]+)"(\s*\))', en)
    if m:
        return f'{m.group(1)}"{zh}"{m.group(3)}'
    # 纯引号字符串："English" -> "中文"
    m = re.fullmatch(r'"([^"]+)"', en)
    if m:
        return f'"{zh}"'
    # 片段：?"A":"B" 三元（源码里常见）
    m = re.fullmatch(r'(\?")([^"]+)("\s*:\s*")([^"]+)(")', en)
    if m:
        # zh 支持 关闭|打开 或 关闭 / 打开
        pair = zh
        if " / " in pair:
            pair = pair.replace(" / ", "|", 1)
        if "|" in pair:
            a, b = pair.split("|", 1)
            return f'{m.group(1)}{a.strip()}{m.group(3)}{b.strip()}{m.group(5)}'
    # 片段：:"A":"B" 三元（zh 格式：关闭|打开）
    m = re.fullmatch(r'(:")([^"]+)("\s*:\s*")([^"]+)(")', en)
    if m:
        pair = zh
        if " / " in pair:
            pair = pair.replace(" / ", "|", 1)
        if "|" in pair:
            a, b = pair.split("|", 1)
            return f'{m.group(1)}{a.strip()}{m.group(3)}{b.strip()}{m.group(5)}'
    # 模板/反引号：不安全，拒绝
    if "${" in en or en.startswith("`"):
        return None
    # 优先按 match/en 的真实前缀还原（如 leftLabel / tooltip / title）
    m = re.match(
        r'(leftLabel|rightLabel|leftLabelTooltip|rightLabelTooltip|label|title|tooltip|header|placeholder|ariaLabel|description|message|content)\s*:\s*"',
        en,
    )
    if m:
        return f'{m.group(1)}:"{zh}"'
    if kind in {
        "label",
        "title",
        "tooltip",
        "header",
        "placeholder",
        "ariaLabel",
        "description",
        "message",
        "content",
    }:
        # 无前缀时不要凭 kind 硬包 label:"..."，避免把裸片段弄坏
        if '"' in en or ":" in en[:40]:
            return None
        return f'{kind}:"{zh}"'
    if en.startswith("localizeByDefault("):
        return f'localizeByDefault("{zh}")'
    m = re.match(r'(label|title|tooltip|header|placeholder|ariaLabel|description|message|content):"', en)
    if m:
        return f'{m.group(1)}:"{zh}"'
    # 片段：,"English")  -> ,"中文")
    m = re.fullmatch(r'(,\s*)"([^"]+)"(\s*\))', en)
    if m:
        return f'{m.group(1)}"{zh}"{m.group(3)}'
    # 片段：:"A":"B" 三元（zh 仅替换整段时需完整；此处 en 为完整三元）
    m = re.fullmatch(r'(:")([^"]+)("\s*:\s*")([^"]+)(")', en)
    if m and "|" in zh:
        # zh 格式: 关闭|打开
        a, b = zh.split("|", 1)
        return f'{m.group(1)}{a}{m.group(3)}{b}{m.group(5)}'
    # 片段：`Search for any ${  （模板前缀，无法单独安全替换时返回 None）
    if en.startswith("`") or "${" in en:
        return None
    # 裸英文（无 title:/label: 等前缀）：中英文都是纯文案，原样替换
    if kind in ("dict", "", "bare", "text") or (
        not en.startswith("localizeByDefault(")
        and not en.startswith("registerSubmenu(")
        and not en.startswith("nls.localize(")
        and not en.startswith("static LABEL")
        and ":" not in en[:30]
    ):
        return zh
    return None


def _kind_from_en(en: str) -> str:
    if en.startswith("static LABEL"):
        return "LABEL"
    for k in (
        "localizeByDefault",
        "registerSubmenu",
        "nls.localize",
        "label",
        "title",
        "tooltip",
        "header",
        "placeholder",
        "ariaLabel",
        "description",
        "message",
        "content",
    ):
        if en.startswith(k) or en.startswith(f"{k}:"):
            return k
    return "dict"


def _build_match(kind: str, inner_en: str) -> str:
    """用 kind + 纯英文构造完整可替换字面量。"""
    if not inner_en:
        return ""
    if kind == "localizeByDefault":
        return f'localizeByDefault("{inner_en}")'
    if kind == "LABEL":
        return f'static LABEL="{inner_en}"'
    if kind in {
        "label",
        "title",
        "tooltip",
        "header",
        "placeholder",
        "ariaLabel",
        "description",
        "message",
        "content",
    }:
        return f'{kind}:"{inner_en}"'
    # registerSubmenu / nls.localize 无法只凭 inner 唯一还原，需 match 列
    return inner_en


def export_full_csv(root: Path, out_path: Path | None = None) -> tuple[Path, int, int, int]:
    """导出全量英文 + 预填词典中文。返回 (路径, 总行, 已填, 空)。

    排序：按 match 在 bundle.js.orig 中首次出现位置，保证多次导出顺序稳定。
    """
    js = bundle_js_path(root)
    if not js:
        raise FileNotFoundError("未找到 bundle.js")
    orig = js.with_name(js.name + ".orig")
    src = orig if orig.is_file() else js
    text = src.read_text(encoding="utf-8", errors="replace")
    cur_text = js.read_text(encoding="utf-8", errors="replace")

    dp = dict_path()
    if dp.is_file():
        d = json.loads(dp.read_text(encoding="utf-8"))
    else:
        bundled = bundled_dict_source()
        d = (
            json.loads(bundled.read_text(encoding="utf-8"))
            if bundled.is_file()
            else {"files": {}}
        )
    dict_entries = d.get("files", {}).get("lib/frontend/bundle.js", {}).get("entries") or []
    dict_by_en = {e["en"]: e for e in dict_entries}

    # 先扫描源文件，按出现顺序收集
    # pos -> row
    collected: dict[str, dict] = {}
    order_pos: dict[str, int] = {}

    for kind, rx in PATTERNS:
        for m in rx.finditer(text):
            snippet = m.group(0)
            if kind == "ternary":
                a, b = m.group(1), m.group(2)
                if TEXT_NOISE.search(a) or TEXT_NOISE.search(b):
                    continue
                if CJK.search(a) or CJK.search(b):
                    continue
                if not (HAS_EN.search(a) and HAS_EN.search(b)):
                    continue
                inner = f"{a} / {b}"
            else:
                inner = m.group(1)
                if kind in ("text", "leftLabel", "rightLabel", "LABEL") and TEXT_NOISE.search(inner):
                    continue
                if CJK.search(inner) or not HAS_EN.search(inner):
                    continue
            if snippet in collected:
                continue
            pos = m.start()
            collected[snippet] = {
                "kind": kind,
                "en": inner,
                "match": snippet,
                "count": text.count(snippet),
            }
            order_pos[snippet] = pos

    # 词典里有、但源文件当前扫不到的（例如 en 已被替换成中文），仍导出
    # 位置：能用 .orig 找到就用，否则放在文件末尾（稳定）
    extra_i = 0
    for e in dict_entries:
        match = e["en"]
        if match in collected:
            continue
        if match in dict_by_en and match not in collected:
            pos = text.find(match)
            if pos < 0:
                pos = len(text) + extra_i
                extra_i += 1
            kind = _kind_from_en(match)
            # React 子节点片段
            if re.fullmatch(r'(?:,\s*)"[^"]+"(?:\s*\))', match):
                kind = "text"
            collected[match] = {
                "kind": kind,
                "en": extract_inner_from_en(match),
                "match": match,
                "count": cur_text.count(match) or text.count(match),
            }
            order_pos[match] = pos

    rows = []
    for match, info in collected.items():
        e = dict_by_en.get(match)
        zh = extract_inner_from_zh(e["zh"]) if e else ""
        slug_src = info["en"] or match
        slug = re.sub(r"[^a-zA-Z0-9]+", ".", slug_src.strip().lower()).strip(".")
        slug = re.sub(r"\.+", ".", slug)[:48] or "x"
        kind = info["kind"]
        prefix = {
            "localizeByDefault": "lbd",
            "registerSubmenu": "sub",
            "nls.localize": "nls",
            "LABEL": "panel",
        }.get(kind, kind)
        rows.append(
            {
                "id": e["id"] if e else f"{prefix}.{slug}",
                "kind": kind,
                "count": info["count"],
                "en": info["en"],
                "zh": zh,
                "from_dict": "1" if e else "0",
                "skip": "",
                "note": "",
                "match": match,
                "_pos": order_pos.get(match, 10**12),
            }
        )

    # 稳定排序：源文件位置 → en（同位置兜底）
    rows.sort(key=lambda r: (r["_pos"], r["en"].lower()))
    for r in rows:
        del r["_pos"]

    out = out_path or default_csv_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    # en/zh 为纯文案；match 为完整可替换字面量（脚本用，一般不用改）
    fields = ["id", "kind", "count", "en", "zh", "from_dict", "skip", "note", "match"]
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    filled = sum(1 for r in rows if r["zh"].strip())
    empty = sum(1 for r in rows if not r["zh"].strip())
    return out, len(rows), filled, empty


def import_csv_to_dict(root: Path, csv_path: Path | None = None) -> tuple[int, int, int]:
    """按 CSV 重建词典 bundle 条目。返回 (added, skipped, bad)。"""
    path = csv_path or default_csv_path()
    if not path.is_file():
        raise FileNotFoundError(f"未找到 CSV: {path}")
    js = bundle_js_path(root)
    if not js:
        raise FileNotFoundError("未找到 bundle.js")
    orig = js.with_name(js.name + ".orig")
    data = (orig if orig.is_file() else js).read_bytes()

    dp = dict_path()
    if dp.is_file():
        d = json.loads(dp.read_text(encoding="utf-8"))
    else:
        bundled = bundled_dict_source()
        if bundled.is_file():
            d = json.loads(bundled.read_text(encoding="utf-8"))
        else:
            d = {
                "version": 1,
                "minToolVersion": "0.1.0",
                "targetApp": {"name": "STM32CubeMX2", "testedVersions": []},
                "files": {},
            }
    new_entries = []
    used_id: set[str] = set()
    used_en: set[str] = set()
    added = skipped = bad = 0

    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("skip") or "").strip() == "1":
                skipped += 1
                continue
            zh_raw = (row.get("zh") or "").strip()
            match = (row.get("match") or "").strip()
            en_plain = (row.get("en") or "").strip()
            kind = (row.get("kind") or "").strip()
            if not zh_raw:
                skipped += 1
                continue
            if not match:
                # 旧表：en 可能已是完整结构
                if en_plain and (
                    en_plain.startswith("localizeByDefault(")
                    or en_plain.startswith("registerSubmenu(")
                    or en_plain.startswith("nls.localize(")
                    or en_plain.startswith("static LABEL")
                    or re.match(
                        r"(label|title|tooltip|header|placeholder|ariaLabel|description|message|content):",
                        en_plain,
                    )
                ):
                    match = en_plain
                else:
                    match = _build_match(kind, en_plain)
            if not match or match in used_en:
                skipped += 1
                continue
            full_zh = wrap_zh(kind or _kind_from_en(match), match, zh_raw)
            if not full_zh:
                bad += 1
                print(f"  [结构错误] id={row.get('id')} kind={kind} en={match[:60]} zh={zh_raw[:30]}")
                continue
            # 安全闸：禁止把「无引号的英文短语」替换成带引号包装的中文（会弄坏 JS）
            if (
                '"' not in match
                and " " in match
                and not match.startswith("localizeByDefault(")
                and not match.startswith("registerSubmenu(")
                and not match.startswith("nls.localize(")
                and full_zh.startswith(('label:"', 'title:"', 'header:"', 'tooltip:"'))
            ):
                bad += 1
                print(f"  [危险跳过] bare-phrase en={match[:50]} zh={full_zh[:40]}")
                continue
            expect = data.count(match.encode("utf-8"))
            if expect < 1:
                skipped += 1
                continue
            eid = (row.get("id") or "m.x").strip() or "m.x"
            n = 2
            base = eid
            while eid in used_id:
                eid = f"{base}.{n}"
                n += 1
            new_entries.append(
                {"id": eid, "en": match, "zh": full_zh, "mode": "literal", "expect": expect}
            )
            used_id.add(eid)
            used_en.add(match)
            added += 1

    d.setdefault("files", {}).setdefault("lib/frontend/bundle.js", {})
    d["files"]["lib/frontend/bundle.js"]["gz"] = True
    d["files"]["lib/frontend/bundle.js"]["entries"] = new_entries
    dp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return added, skipped, bad
