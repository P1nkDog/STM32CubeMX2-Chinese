"""术语门禁的离线测试：证明它拦得住，而不是只会绿。

    python tools/test_glossary.py

门禁站在「写盘前」那道口上。它一旦静默放行，错译就直接进用户界面，而且再也不会
有人回头查 —— v0.1.0 的 EXE 里它就因为被 PyInstaller 漏掉而全程没生效过。
所以这里每一组都配了**对照组**：先证明改错会被抓，再证明正常输入不误伤。
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):  # 英文系统下控制台可能是 GBK
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core import dictionary, glossary, i18n, paths  # noqa: E402

PASSED = 0
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASSED
    if cond:
        PASSED += 1
    else:
        FAILED.append(f"{name}{('：' + detail) if detail else ''}")
        print(f"  [FAIL] {name}{('：' + detail) if detail else ''}")


def main() -> int:
    pack, src = dictionary.current_pack()
    gp = paths.glossary_path()
    if gp is None:
        print("找不到术语表，测试无从跑起")
        return 2
    gloss = json.loads(gp.read_text(encoding="utf-8"))
    dom_src = glossary.unescape_js(
        i18n.DOM_SCRIPT.read_text(encoding="utf-8", errors="replace")
    )

    # --- 1. 基线：真词典 + 真术语表 ----------------------------------------
    base = glossary.check(pack, gloss, dom_src)
    check("基线：真词典零违规", base.ok, "; ".join(base.errors[:3]))
    check("基线：零告警（核对项没有落空的）", not base.warns, "; ".join(base.warns[:3]))
    n_terms = sum(1 for k in gloss["terms"] if not k.startswith("_"))
    n_pass_terms = sum(1 for p in base.passes if p.startswith("术语 "))
    check(f"基线：terms 里 {n_terms} 条非注释项全部核对到", n_pass_terms == n_terms,
          f"实际核对 {n_pass_terms}")
    print(f"  [基线] {src} -> {len(pack):,} 条；{base.brief().splitlines()[-2]}")

    # --- 2. 对照组：改错一条译法必须被拦 ------------------------------------
    bad = dict(pack)
    bad["Push pull"] = "推挽式"
    rep = glossary.check(bad, gloss, dom_src)
    check("故意把 'Push pull' 译成「推挽式」→ 拦下",
          not rep.ok and any("译法不符" in e for e in rep.errors), rep.brief())

    # --- 3. 专有名词的反向断言 ---------------------------------------------
    bad = dict(pack)
    bad["GPIO"] = "通用输入输出"
    rep = glossary.check(bad, gloss, dom_src)
    check("把 GPIO 翻成中文 → 拦下",
          not rep.ok and any("专有名词" in e for e in rep.errors), rep.brief())

    # --- 4. 形状不对要拒绝，不能猜 ------------------------------------------
    wrapped = {"languageId": "zh-cn", "replacements": {"Push pull": "彻底错译"}}
    rep = glossary.check(wrapped, gloss, dom_src)
    check("传进 {languageId, replacements} 包装形态 → 明确拒绝而非静默放行",
          not rep.ok and any("扁平" in e for e in rep.errors), rep.brief())
    rep = glossary.check({"Cancel": 123}, gloss, dom_src)
    check("值不是字符串 → 同样拒绝", not rep.ok and any("扁平" in e for e in rep.errors))

    # --- 5. 回归：词典里出现一条英文原文正好叫 replacements -----------------
    # 旧实现写的是 `pack.get("replacements", pack)`，那种情况下查表对象会变成
    # 一个字符串，门禁要么当场 AttributeError 崩掉，要么退化成「全告警零违规」。
    tricky = dict(pack)
    tricky["replacements"] = "替换项"
    tricky["Push pull"] = "推挽式（故意改错）"
    try:
        rep = glossary.check(tricky, gloss, dom_src)
    except Exception as e:  # noqa: BLE001
        check("出现叫 replacements 的词条时门禁不崩", False, f"{type(e).__name__}: {e}")
    else:
        check("出现叫 replacements 的词条时门禁不崩", True)
        check("同一次调用里错译仍然被抓",
              not rep.ok and any("译法不符" in e for e in rep.errors), rep.brief())

    # 这个键不再特殊：其它译法都对时照样全绿，核对项一条不少
    tricky_ok = dict(pack)
    tricky_ok["replacements"] = "替换项"
    rep = glossary.check(tricky_ok, gloss, dom_src)
    check("叫 replacements 不影响其它核对项（通过数与基线相同）",
          rep.ok and len(rep.passes) == len(base.passes),
          f"{len(rep.passes)} vs {len(base.passes)}")

    # --- 6. 作用域的两类失效 -------------------------------------------------
    conflict = dict(pack)
    conflict["Low"] = gloss["scope"]["Speed"]["Low"]
    rep = glossary.check(conflict, gloss, dom_src)
    check("全局译法与作用域译法撞车 → 拦下（否则作用域形同虚设）",
          not rep.ok and any("形同虚设" in e for e in rep.errors), rep.brief())
    rep = glossary.check(pack, gloss, "")
    check("作用域译法没写进 dom-translate.js → 拦下",
          not rep.ok and any("没进 dom-translate.js" in e for e in rep.errors),
          rep.brief())

    # --- 7. 纯函数：不许改动入参 --------------------------------------------
    p_copy, g_copy = copy.deepcopy(pack), copy.deepcopy(gloss)
    glossary.check(p_copy, g_copy, dom_src)
    check("check() 确实不改动传进来的词典与术语表", p_copy == pack and g_copy == gloss)

    # --- 8. 结论文案不许在跳过核对时说「全部一致」 ---------------------------
    only_warns = glossary.Report(warns=["术语未出现在语言包: 'X'"])
    check("只有告警时，结论不许写「全部术语与术语表一致」",
          "全部术语与术语表一致" not in only_warns.brief())

    # --- 9. run() 与 CLI 走的是同一份逻辑 -----------------------------------
    r = glossary.run(pack)
    check("run() 与 check() 结论一致（CI 与 --patch 同一套规则）",
          r is not None and r.ok and len(r.passes) == len(base.passes))

    # --- 10. 术语表自己出问题时：报出来，别甩 traceback，也别假装核对过 ------
    real_gp = paths.glossary_path
    with tempfile.TemporaryDirectory() as td:
        broken = Path(td) / "glossary.zh.json"
        broken.write_text("{ 少个引号", encoding="utf-8")
        try:
            for label, p in (
                ("不存在", Path("Z:/不存在/glossary.zh.json")),
                ("不是合法 JSON", broken),
            ):
                paths.glossary_path = lambda p=p: p
                try:
                    rep = glossary.run(pack)
                except Exception as e:  # noqa: BLE001
                    check(f"术语表{label} → 不抛异常", False, f"{type(e).__name__}: {e}")
                    continue
                check(
                    f"术语表{label} → 告警放行，且不假装核对过任何一项",
                    rep is not None and rep.ok and len(rep.warns) == 1 and not rep.passes,
                    rep.brief() if rep else "None",
                )
                check(
                    f"术语表{label} → 结论不许写「全部术语与术语表一致」",
                    rep is not None and "全部术语与术语表一致" not in rep.brief(),
                )
        finally:
            paths.glossary_path = real_gp

    # --- 11. --patch 里的可见性：全过要安静，有错必须吵 ----------------------
    import main as tool

    def run_gate(pack_arg: dict, verbose: bool = False) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = tool._check_glossary(pack_arg, verbose)
        return rc, buf.getvalue()

    bad_pack = dict(pack)
    bad_pack["Push pull"] = "推挽式（故意改错）"
    rc, out = run_gate(pack)
    check("全过时 --patch 不打门禁报告（返回 0 且零输出）",
          rc == 0 and out == "", f"rc={rc} 输出={out!r}")
    rc, out = run_gate(pack, verbose=True)
    check("-v 时全过也要打出来（让人确认门禁真跑过）",
          rc == 0 and "术语门禁" in out, out[:60])
    rc, out = run_gate(bad_pack)
    check(
        "有违规时默认必须吵：返回非 0、打出 FAIL 行、不许被静默吞掉",
        rc == 1 and "FAIL" in out and "推挽" in out,
        f"rc={rc} 输出={out[:80]!r}",
    )

    # --- 12. 词族断言：terms 管不到的散文由它守 ------------------------------
    # 存在的理由就是这次真实事故：'Activate' 早就钉成「启用」，同一屏里的
    # 'Part cannot be activated' 却还写着「无法激活部件」，门禁 108 项全过。
    fam = [r for r in gloss.get("family") or [] if isinstance(r, dict)]
    check("术语表里配了词族规则", len(fam) >= 1)
    check(
        "基线：词族规则核对过并计入通过项（含命中条数）",
        any(p.startswith("词族") and "命中" in p for p in base.passes),
        "; ".join(base.passes[-3:]),
    )

    def fam_gloss(**patch) -> list:
        rule = dict(fam[0])
        rule.update(patch)
        return [rule]

    bad = dict(pack)
    bad["Part cannot be activated"] = "无法激活部件"
    rep = glossary.check(bad, {**gloss, "family": fam_gloss()}, dom_src)
    check(
        "把 'Part cannot be activated' 译回「激活」→ 拦下，并说清该译成什么",
        not rep.ok
        and any("词族" in e and "启用" in e for e in rep.errors),
        rep.brief(),
    )
    # --patch 走的是同一道口子：违规要变成非 0，否则汉化照样落盘
    rc, out = run_gate(bad)
    check("同一份回退词典经 --patch 的门禁 → 返回非 0", rc == 1, f"rc={rc} 输出={out[:60]!r}")

    # 不误伤：不命中正则的条目不归这条管（词族断言的边界，写死在这里）
    rep = glossary.check({"Zoom to fit": "激活视图"}, {**gloss, "family": fam_gloss()}, dom_src)
    check("不命中 activate/active 的条目不因「激活」被这条误伤", rep.ok, rep.brief())

    # 规则自己坏掉的四种形状，全部要出声（悄悄跳过 = 从此永远通过）
    rep = glossary.check(pack, {**gloss, "family": fam_gloss(en="activat(")}, dom_src)
    check("正则写坏 → 报 Error 而不是跳过", not rep.ok and any("正则写坏" in e for e in rep.errors), rep.brief())
    rep = glossary.check(pack, {**gloss, "family": fam_gloss(en="zzz_没有这个词")}, dom_src)
    check("一条都没命中 → 报 Warn（规则已失效）", bool(rep.warns) and any("没命中" in w for w in rep.warns), rep.brief())
    rep = glossary.check(pack, {**gloss, "family": fam_gloss(en="", ban=[])}, dom_src)
    check("没写 en 正则 → 报 Error", not rep.ok and any("没写 en" in e for e in rep.errors), rep.brief())
    rep = glossary.check(pack, {**gloss, "family": fam_gloss(ban=[])}, dom_src)
    check("命中了却没写 ban → 报 Warn，不说「无一处回退」",
          bool(rep.warns) and any("没写 ban" in w for w in rep.warns)
          and not any("回退" in p for p in rep.passes),
          rep.brief())
    rep = glossary.check(pack, {**gloss, "family": ["activat"]}, dom_src)
    check("规则不是对象 → 报 Error", not rep.ok and any("词族规则必须是对象" in e for e in rep.errors), rep.brief())

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项 / 通过 {PASSED} 项")
        for f in FAILED:
            print("  -", f)
        return 1
    print(f"结论: 通过（{PASSED} 项断言）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
