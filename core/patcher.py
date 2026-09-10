from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReplaceResult:
    entry_id: str
    en: str
    zh: str
    found: int
    replaced: int
    expect: int | None
    ok: bool
    message: str = ""


def count_occurrences(data: bytes, needle: bytes) -> int:
    if not needle:
        return 0
    count = 0
    start = 0
    n = len(needle)
    while True:
        idx = data.find(needle, start)
        if idx < 0:
            break
        count += 1
        start = idx + n
    return count


def replace_literal(data: bytes, old: bytes, new: bytes) -> tuple[bytes, int]:
    """字节级全量替换。从后往前拼接，避免偏移问题。"""
    if not old:
        return data, 0
    positions: list[int] = []
    start = 0
    while True:
        idx = data.find(old, start)
        if idx < 0:
            break
        positions.append(idx)
        start = idx + len(old)
    if not positions:
        return data, 0
    out = data
    n_old, n_new = len(old), len(new)
    for pos in reversed(positions):
        out = out[:pos] + new + out[pos + n_old :]
    return out, len(positions)


def apply_entries(
    data: bytes,
    entries: list[dict],
) -> tuple[bytes, list[ReplaceResult]]:
    results: list[ReplaceResult] = []
    out = data
    for e in entries:
        eid = e.get("id") or e.get("en", "")[:40]
        en = e.get("en", "")
        zh = e.get("zh", "")
        mode = e.get("mode", "literal")
        expect = e.get("expect")
        if mode != "literal":
            results.append(
                ReplaceResult(eid, en, zh, 0, 0, expect, False, f"暂不支持 mode={mode}")
            )
            continue
        old_b = en.encode("utf-8")
        new_b = zh.encode("utf-8")
        found = count_occurrences(out, old_b)
        if found == 0:
            results.append(
                ReplaceResult(eid, en, zh, 0, 0, expect, False, "未命中（可能已汉化或版本变化）")
            )
            continue
        if expect is not None and found != expect:
            results.append(
                ReplaceResult(
                    eid,
                    en,
                    zh,
                    found,
                    0,
                    expect,
                    False,
                    f"命中数 {found} != expect {expect}，已跳过",
                )
            )
            continue
        out, replaced = replace_literal(out, old_b, new_b)
        results.append(
            ReplaceResult(eid, en, zh, found, replaced, expect, True)
        )
    return out, results
