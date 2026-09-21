#!/usr/bin/env python
"""i18n 注入片段的离线自检——不接触安装目录，纯本地。

用合成的小样本验证四类注入生成的 JS 是否合法，并验证四个锚点
在真实 bundle 上仍唯一命中。已经踩过两次坑（f-string 花括号、
三元分支缺括号、try 块提前闭合），所以把它固化下来：

    python tools/selftest_i18n.py            # 片段语法自检
    python tools/selftest_i18n.py -g <目录>  # 再跑一遍真实锚点探测
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import i18n, langpack  # noqa: E402

# 合成样本：模仿真实 bundle 里 nls 模块的结构（变量名与真实一致）
SAMPLES = {
    "lib/frontend/bundle.js": (
        'var l;(function(r){r.defaultLocale="en",r.localeId="localeId",'
        'r.locale=typeof window=="object"&&window&&window.localStorage.getItem(r.localeId)||void 0;'
        "let s;function i(d,...u){if(r.localization){const p=a(d);if(p)return c(p,d,...u);"
        'console.warn(`nope ${d}`)}return n.Localization.format(d,u)}r.localizeByDefault=i;'
        "function c(d,u,...p){return n.Localization.localize(r.localization,d,u,...p)}r.localize=c;"
        'function h(d){window.localStorage.setItem(r.localeId,d)}r.setLocale=h})'
        "(l||(e.nls=l={}));class o{constructor(){this.preferredKeys=new Set([])}}"
        "// ...此处是 I18nPreloadContribution 模块...\n"
        "p.languagePack?o.nls.localization=p:d!==o.nls.defaultLocale&&(x=1);"
    ),
    "lib/backend/main.js": (
        'var g;(function(c){c.defaultLocale="en",c.localeId="localeId",'
        "c.locale=typeof window==\"object\"&&window&&window.localStorage.getItem(c.localeId)||void 0;"
        "let d;function u(t,...r){if(c.localization){const l=n(t);if(l)return o(l,t,...r);"
        "console.warn(`nope ${t}`)}return p.Localization.format(t,r)}c.localizeByDefault=u;"
        "function o(t,r,...l){return p.Localization.localize(c.localization,t,r,...l)}c.localize=o;"
        'function a(t){window.localStorage.setItem(c.localeId,t)}c.setLocale=a})'
        "(g||(e.nls=g={}));d.registerLocalizationFromRequire(\"zh-cn\",s(897836));"
    ),
    "lib/frontend/secondary-window.js": (
        'var S;(function(f){f.defaultLocale="en",f.localeId="localeId",'
        "f.locale=typeof window==\"object\"&&window&&window.localStorage.getItem(f.localeId)||void 0;"
        "let v;function u(c,...o){if(f.localization){const n=g(c);if(n)return d(n,c,...o);"
        "console.warn(`nope ${c}`)}return i.Localization.format(c,o)}f.localizeByDefault=u;"
        "function d(c,o,...n){return i.Localization.localize(f.localization,c,o,...n)}f.localize=d;"
        'function l(c){window.localStorage.setItem(f.localeId,c)}f.setLocale=l})'
        "(S||(e.nls=S={}));class y{constructor(){this.preferredKeys=new Set([])}}"
    ),
}

VAR = {
    "lib/frontend/bundle.js": "l",
    "lib/frontend/secondary-window.js": "S",
    "lib/backend/main.js": "g",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="i18n 注入片段自检")
    ap.add_argument("-g", "--path", default=None,
                  help="可选：CubeMX2 安装目录（指到 dist/app 那一层也行），给了就跑真实锚点探测")
    args = ap.parse_args(argv)

    node = i18n.find_node()
    if not node:
        print("[错误] 未找到 node，无法做语法自检")
        return 1

    pack = {
        "Accept": "接受",
        "Create New File ({0})": "新建文件（{0}）",
        'He said "hi" \\ ok': "带引号和反斜杠",
        "换行": "x",
    }
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="cubemx2zh_selftest_") as td:
        for rel, sample in SAMPLES.items():
            target = next(t for t in i18n.TARGETS if t.rel == rel)
            print(f"=== {rel}")
            try:
                out, logs = i18n.inject_text(sample, target, pack)
            except Exception as e:  # noqa: BLE001
                print(f"    [问题] 注入抛错: {e}")
                ok_all = False
                continue
            for line in logs:
                print(f"   {line}")
            f = Path(td) / (Path(rel).name + ".js")
            f.write_text(out, encoding="utf-8")
            proc = subprocess.run(
                [node, "--check", str(f)],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=120,
            )
            if proc.returncode == 0:
                print("    语法: 通过")
            else:
                print(f"    语法: 失败 -> {(proc.stderr or '').strip()[:200]}")
                ok_all = False
            # 幂等
            try:
                i18n.inject_text(out, target, pack)
                print("    [问题] 重复注入未报错")
                ok_all = False
            except ValueError:
                print("    幂等: 通过")
            # 语言包字面量必须能被 JSON.parse
            try:
                import json as _json

                _json.loads(langpack.js_literal(pack))
            except ValueError as e:  # noqa: BLE001
                print(f"    [问题] 语言包字面量不是合法 JSON: {e}")
                ok_all = False
        # 空包 / 诡异字符
        for special in ({}, {"</script>": "x", "a\u2028b": "y", "\\": "z"}):
            lit = langpack.js_literal(special)
            f = Path(td) / "lit.js"
            f.write_text("var x=" + lit + ";", encoding="utf-8")
            proc = subprocess.run(
                [node, "--check", str(f)], capture_output=True, text=True, timeout=60
            )
            if proc.returncode != 0:
                print(f"    [问题] 特殊字符语言包语法失败: {special}")
                ok_all = False
        print("特殊字符语言包: 通过")

    print()
    print("=== 未覆盖清单的排序稳定性")
    # 同次数的并列项必须有确定次序。set 迭代序受 PYTHONHASHSEED 影响，所以
    # 只要谁把它退回 Counter.most_common()，这段就会（几乎每次）报问题。
    words = ["zeta", "alpha", "Mike", "bravo", "yankee", "charlie", "delta"]
    with tempfile.TemporaryDirectory() as td2:
        app2 = Path(td2)
        for rel in [t.rel for t in i18n.TARGETS][:3]:
            f = app2 / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(
                "".join(f'nls.localize("k","{w}")' for w in words), encoding="utf-8"
            )
        got = i18n.missing_report(app2, {})
        want = [(w, 3) for w in sorted(words)]
        if got == want:
            print(f"    通过（{len(want)} 条同次数条目按文本升序，命中文件数=3）")
        else:
            print(f"    [问题] 顺序或计数不对：{got} != {want}")
            ok_all = False

    if args.path:
        from core import locate

        root = Path(args.path)
        app = locate.app_dir(root)
        print()
        print(f"=== 真实锚点探测: {app}")
        for p in i18n.probe(app):
            flag = "OK" if p.ok else "!!"
            state = "已注入" if p.injected else "未注入"
            print(f"[{flag}] {p.rel} ({state}) {p.hits}")
            for x in p.notes:
                print(f"       [提示] {x}")
            for x in p.problems:
                print(f"       [问题] {x}")
            ok_all = ok_all and p.ok

    print()
    print("结论:", "自检通过" if ok_all else "自检失败")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
