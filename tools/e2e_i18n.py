#!/usr/bin/env python
"""真·端到端验证：把框架**自己的**代码在 node 里跑起来。

verify_i18n.py 用的是「复刻」的 localize，只能证明数据对；
这个工具更进一步：从**已注入的真实 bundle** 里把三个原始模块抠出来，
原封不动地在 node 里执行，然后调用**框架自己的** ``nls.localizeByDefault``：

    249401  @theia/core/lib/common/i18n      → Localization.localize / format
    448496  VS Code nls 元数据（keys+messages） → 反查 key 的唯一依据
    152985  @theia/core/lib/common/nls       → localizeByDefault / getDefaultKey
                                              （★ 我们注入的代码就在这个模块里）

于是「英文原文 → 反查 key → 查 replacements → format 占位符」整条链
都是框架的真实实现，我们只提供输入和断言。

最有价值的一项输出是 ``viaKey`` 占比：有多少文案是靠元数据反查到 key 走
正规路，有多少是反查不到、靠我们改写过的 fallback 兜底命中。
这个比例直接告诉我们 fallback 那个补丁是不是必需品。

用法::

    python tools/e2e_i18n.py -g C:/mysoftware/cubemx2
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import dictionary, i18n, locate  # noqa: E402
from jsmod import extract_module  # noqa: E402

MOD_I18N = 249401      # Localization
MOD_META = 448496      # VS Code nls 元数据
MOD_NLS = 152985       # nls（含我们的注入块）


HARNESS = r"""
const fs = require('fs');
const [modPath, packPath, nlsVar, appArg] = process.argv.slice(2);
const mods = JSON.parse(fs.readFileSync(modPath, 'utf8'));
const pack = JSON.parse(fs.readFileSync(packPath, 'utf8'));

const make = (src, nparams) => new Function('return ' + src)();

// 448496: (module) => module.exports = JSON.parse(...)
const metaMod = { exports: {} };
make(mods.meta)(metaMod);
const meta = metaMod.exports;

// 249401: (module, exports)
const locMod = { exports: {} };
make(mods.loc)(locMod, locMod.exports);
const loc = locMod.exports;

const requireStub = (id) => {
  if (id === 249401) return loc;
  if (id === 448496) return meta;
  throw new Error('unexpected require: ' + id);
};

function loadNls(withLocale) {
  const saved = global.window;
  if (withLocale !== undefined) {
    global.window = { localStorage: { getItem: () => withLocale, setItem: () => {} } };
  } else {
    global.window = undefined;
  }
  const mod = { exports: {} };
  make(mods.nls)(mod, mod.exports, requireStub);
  global.window = saved;
  // 模块通过 `e.nls = l = {}` 导出，所以取 exports.nls（不是局部变量名）
  const ns = mod.exports.nls;
  if (!ns) throw new Error('nls 模块没有导出 exports.nls');
  return ns;
}

const nls = loadNls();

// ---- 主断言：框架自己的 localizeByDefault ----
const keys = Object.keys(pack);
const step = Math.max(1, Math.floor(keys.length / 400));
const wrong = [], notApplied = [];
let checked = 0, viaKey = 0, viaFallback = 0;

for (let k = 0; k < keys.length; k += step) {
  const en = keys[k];
  const want = pack[en];
  const dk = nls.getDefaultKey(en);
  if (dk) viaKey++; else viaFallback++;
  const got = nls.localizeByDefault(en);
  checked++;
  if (got === undefined || got === null) { notApplied.push(en); continue; }
  if (got !== want) wrong.push([en, want, got]);
}

// ---- 占位符：框架自己的 format ----
const phEn = keys.filter((k) => /\{0\}/.test(k)).slice(0, 5);
const phBad = [];
for (const en of phEn) {
  const got = nls.localizeByDefault(en, 'ARG0');
  const want = pack[en].replace(/\{0\}/g, 'ARG0');
  if (got !== want) phBad.push([en, want, got]);
}

// ---- 未收录文案原样返回 ----
const unknown = nls.localizeByDefault('ZZZ_NOT_IN_PACK_ZZZ_42');

// ---- 用户在设置里选了别的语言时不能强推中文 ----
const nlsEn = loadNls('en');
const enKept = nlsEn.locale === 'en' && !nlsEn.localization;

console.log(JSON.stringify({
  locale: nls.locale,
  languageId: nls.localization && nls.localization.languageId,
  languagePack: nls.localization && nls.localization.languagePack,
  replCount: nls.localization ? Object.keys(nls.localization.replacements).length : 0,
  packCount: keys.length,
  checked, viaKey, viaFallback,
  wrongCount: wrong.length, wrong: wrong.slice(0, 5),
  notApplied: notApplied.slice(0, 5), notAppliedCount: notApplied.length,
  phChecked: phEn.length, phBadCount: phBad.length, phBad: phBad.slice(0, 3),
  unknownOk: unknown === 'ZZZ_NOT_IN_PACK_ZZZ_42',
  enKept,
  metaKeys: Object.keys(meta.keys || {}).length,
  metaMessages: Object.keys(meta.messages || {}).length,
}));
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="用框架自己的代码做端到端验证")
    ap.add_argument("-g", "--path", required=True,
                  help="CubeMX2 安装目录（指到 dist/app 那一层也行）")
    ap.add_argument(
        "--dict", default=None, help="词典路径（默认按 resolve_dictionary 的优先级取）"
    )
    args = ap.parse_args(argv)

    try:
        pack, src = dictionary.current_pack(Path(args.dict) if args.dict else None)
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 取语言包失败: {e}")
        return 1

    root = locate.root_from_arg(args.path)
    if root is None:
        print(f"[错误] 不是有效的安装目录: {args.path}")
        return 1
    app = locate.app_dir(root)
    if not app:
        print(f"[错误] 未找到 app 目录: {root}")
        return 1

    bundle = app / "lib/frontend/bundle.js"
    text = bundle.read_text(encoding="utf-8", errors="replace")
    if i18n.MARKER not in text:
        print(f"[错误] {bundle.name} 未注入（先跑 main.py --patch）")
        return 1

    print(f"词典: {src} -> 语言包 {len(pack):,} 条")
    print(f"bundle: {bundle}（{len(text):,} 字符）")
    print()

    srcs = {}
    for name, mid in (("loc", MOD_I18N), ("meta", MOD_META), ("nls", MOD_NLS)):
        s = extract_module(text, mid)
        if not s:
            print(f"[错误] 未能从 bundle 提取模块 {mid}（{name}）")
            return 1
        srcs[name] = s
        print(f"  提取模块 {mid} ({name}): {len(s):,} 字符")

    # nls 模块里的 nls 变量名（tail 锚点用的那个）
    m = i18n.A_TAIL.search(text)
    nls_var = m.group("a") if m else "l"
    print(f"  nls 变量名: {nls_var}")
    print()

    node = i18n.find_node()
    if not node:
        print("[错误] 未找到 node")
        return 1

    with tempfile.TemporaryDirectory(prefix="cubemx2zh_e2e_") as td:
        mp = Path(td) / "mods.json"
        mp.write_text(json.dumps(srcs), encoding="utf-8")
        pk = Path(td) / "pack.json"
        pk.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
        hs = Path(td) / "e2e.js"
        hs.write_text(HARNESS, encoding="utf-8")

        proc = subprocess.run(
            [node, str(hs), str(mp), str(pk), nls_var, str(app)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=900,
        )

    line = ""
    for ln in (proc.stdout or "").strip().splitlines():
        if ln.strip().startswith("{"):
            line = ln.strip()
    if not line:
        print("[错误] 端到端脚本没有输出结果")
        print((proc.stderr or "")[:1500])
        return 1

    res = json.loads(line)
    print(f"框架冷启动后的 locale = {res['locale']}，languageId = {res['languageId']}")
    print(f"框架元数据: keys={res['metaKeys']:,}  messages={res['metaMessages']:,}")
    print()

    total = res["viaKey"] + res["viaFallback"]
    checks = [
        ("locale 被设为 zh-cn", res["locale"] == "zh-cn"),
        ("languagePack = true", res["languagePack"] is True),
        (
            f"replacements 条目 = {res['replCount']}",
            res["replCount"] == res["packCount"],
        ),
        (
            f"抽查 {res['checked']} 条，框架返回的译文全部正确",
            res["wrongCount"] == 0,
        ),
        (
            f"占位符 {res['phChecked']} 条经框架 format 正确替换",
            res["phBadCount"] == 0,
        ),
        ("未收录文案原样返回（不炸、不乱译）", res["unknownOk"] is True),
        ("用户在设置里选英文时保持英文", res["enKept"] is True),
    ]
    for name, good in checks:
        print(f"  {'OK ' if good else '!! '} {name}")
    if res["wrong"]:
        print(f"     不一致样例: {res['wrong']}")
    if res["phBad"]:
        print(f"     占位符样例: {res['phBad']}")

    print()
    if total:
        pct = res["viaKey"] / total * 100
        print(
            f"解析路径占比: 反查到 key 走正规路 {res['viaKey']}/{total} "
            f"({pct:.0f}%)，靠 fallback 兜底 {res['viaFallback']}/{total} "
            f"({100 - pct:.0f}%)"
        )
        print("  → 兜底那部分正是「不加 fallback 补丁就永远是英文」的文案。")

    ok = all(g for _, g in checks)
    print()
    print("结论:", "端到端通过（框架真实代码路径）" if ok else "端到端失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
