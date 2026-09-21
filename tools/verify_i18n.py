#!/usr/bin/env python
"""汉化落盘后的验证：语法门禁 + 注入块运行期语义自检。

这是 i18n 通道的安全闸门。它做四件事：

1. 每个目标文件是否都带注入标记；
2. ``node --check`` 语法校验（28MB 的大文件也能过）；
3. 把注入块抽出来在 node 里真实执行，断言
   replacements 条目数与语言包一致、locale 缺省为 zh-cn、
   用户已选其它语言时不注入中文；
4. 用复刻的框架 ``Localization.localize`` 抽 200 条做译文抽查，
   并验证 ``{0}`` 占位符仍按框架语义替换。

用法::

    python tools/verify_i18n.py -g C:/mysoftware/cubemx2
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import dictionary, i18n, locate  # noqa: E402

HARNESS = r"""
const fs = require('fs');
const [file, nlsVar, packPath] = process.argv.slice(2);
const text = fs.readFileSync(file, 'utf8');
const START = '/*__CUBEMX2ZH__*/', END = '/*__CUBEMX2ZH_END__*/';
const i = text.indexOf(START);
if (i < 0) { console.log(JSON.stringify({ error: '未找到注入标记' })); process.exit(0); }
const j = text.indexOf(END, i);
const block = text.slice(i + START.length, j);
const before = text.slice(0, i);
const pack = JSON.parse(fs.readFileSync(packPath, 'utf8'));

const runBlock = (initial) => {
  const nls = Object.assign({}, initial);
  const fn = new Function(nlsVar, block + '\nreturn ' + nlsVar + ';');
  return fn(nls);
};

const out = runBlock({});
const repl = (out.localization && out.localization.replacements) || {};
const en = runBlock({ locale: 'en' });

const fmt = (t, a) => t.replace(/{([^}]+)}/g, (m, k) => (a && a[k] !== undefined ? a[k] : m));
const norm = (s) => s.replace(/&&/g, '');
const localize = (loc, key, value, ...a) => {
  let t = value;
  if (loc) {
    const r = loc.replacements && loc.replacements[value];
    if (typeof r === 'string') t = r;
    else { const l = loc.translations[key]; if (l) t = norm(l); }
  }
  return fmt(t, a);
};
const loc = (v, ...a) => localize(out.localization, '', v, ...a);

const keys = Object.keys(repl);
const step = Math.max(1, Math.floor(keys.length / 200));
const mismatches = [];
let checked = 0;
for (let k = 0; k < keys.length; k += step) {
  const src = keys[k];
  if (loc(src) !== repl[src]) mismatches.push(src);
  checked++;
}
const phKey = keys.find((k) => /\{0\}/.test(k));
let phOk = null;
if (phKey) {
  const zh = repl[phKey];
  const expected = zh.replace(/{([^}]+)}/g, (m, k) => (k === '0' ? 'X' : m));
  phOk = loc(phKey, 'X') === expected;
}

console.log(JSON.stringify({
  markerOk: true,
  fallbackRewritten: /return [A-Za-z_$][\w$]*\("",/.test(before),
  fallbackResidual: /return [A-Za-z_$][\w$]*\.Localization\.format\([^)]*\)\}[A-Za-z_$][\w$]*\.localizeByDefault=/.test(before),
  locale: out.locale,
  languageId: out.localization && out.localization.languageId,
  languagePack: out.localization && out.localization.languagePack,
  replCount: keys.length,
  packCount: Object.keys(pack).length,
  localeEnUntouched: !en.localization,
  missingTranslations: keys.filter((k) => !(k in pack)).length,
  extraTranslations: Object.keys(pack).filter((k) => !(k in repl)).length,
  checked, mismatches: mismatches.slice(0, 5), mismatchCount: mismatches.length,
  phKey, phOk,
  unknownReturnsSource: loc('ZZZ_NOT_IN_PACK_ZZZ') === 'ZZZ_NOT_IN_PACK_ZZZ',
  packkeep: packkeepTest(text),
}));

// packkeep：语言包从 localizationServer 到达时会整体覆盖 nls.localization，
// 若不改成合并，我们注入的 3000+ 条 replacements 会被冲掉，界面直接退回英文。
// 这里把 then 分支从**真实文件**里抠出来执行，验证「合并且不炸」。
function packkeepTest(src) {
  // then 分支自身不含 ':'，所以用 `?...(...):` 抓取最短匹配即可
  const RX = /([A-Za-z_$][\w$]*)\.languagePack\?\(([^:]*?)\):/;
  const m = RX.exec(src);
  if (!m) return { present: false };
  const flag = m[1];
  const then = m[2];
  const mv = /([A-Za-z_$][\w$]*)\.nls\.localization=/.exec(then);
  const nls = mv ? mv[1] : null;
  let mergeOk = /Object\.assign/.test(then);

  let keepsOurReplacements = false, survivesMissingLocalization = false;
  let e1 = null, e2 = null;
  if (nls) {
    const expr = 'return (' + then + ')';
    // 场景 1：我们已注入中文表，语言包随后到达 —— 中文表必须活下来
    const o1 = { nls: { localization: { replacements: { ZZZ_KEEP: '中文' } } } };
    const p1 = { languagePack: true, replacements: { PACK_KEEP: '自带' } };
    try { new Function('o', 'p', expr)(o1, p1); } catch (e) { e1 = String(e); }
    keepsOurReplacements =
      !e1 && o1.nls.localization === p1 &&
      p1.replacements && p1.replacements.ZZZ_KEEP === '中文' &&
      p1.replacements.PACK_KEEP === '自带';

    // 场景 2：此前没有 localization（未注入的原状）—— 不能抛异常、不能抹掉语言包自带表
    const o2 = { nls: {} };
    const p2 = { languagePack: true, replacements: { X: 'Y' } };
    try { new Function('o', 'p', expr)(o2, p2); } catch (e) { e2 = String(e); }
    survivesMissingLocalization = !e2 && !!p2.replacements && p2.replacements.X === 'Y';
  }

  return {
    present: true,
    flag: flag, nls: nls, mergeOk: mergeOk,
    keepsOurReplacements: keepsOurReplacements,
    survivesMissingLocalization: survivesMissingLocalization,
    err1: e1, err2: e2,
  };
}
"""


def verify(root: Path, pack: dict[str, str], verbose: bool = True) -> bool:
    app = locate.app_dir(root)
    if not app:
        print("[错误] 未找到 app 目录")
        return False
    node = i18n.find_node()
    if not node:
        print("[错误] 未找到 node，无法做运行期验证")
        return False

    with tempfile.TemporaryDirectory(prefix="cubemx2zh_verify_") as td:
        pack_file = Path(td) / "pack.json"
        pack_file.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
        harness = Path(td) / "harness.js"
        harness.write_text(HARNESS, encoding="utf-8")

        all_ok = True
        for target in i18n.TARGETS:
            path = app / target.rel
            print(f"=== {target.rel}")
            if not path.is_file():
                print("    [问题] 文件不存在")
                all_ok = False
                continue

            text = path.read_text(encoding="utf-8", errors="replace")
            if i18n.MARKER not in text:
                print("    [问题] 未找到注入标记（未汉化？）")
                all_ok = False
                continue
            print("    注入标记: 存在")

            ok, msg = i18n.node_check(path)
            print(f"    语法门禁: {msg}")
            all_ok = all_ok and ok

            proc = subprocess.run(
                [node, str(harness), str(path), target_nls_var(target, text), str(pack_file)],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=600,
            )
            try:
                res = json.loads((proc.stdout or "").strip().splitlines()[-1])
            except (ValueError, IndexError):
                print(f"    [问题] 运行期自检未返回结果: {(proc.stderr or '')[:200]}")
                all_ok = False
                continue

            checks = [
                ("fallback 已改写", res.get("fallbackRewritten") is True),
                ("fallback 无残留", res.get("fallbackResidual") is False),
                (f"locale = zh-cn", res.get("locale") == "zh-cn"),
                ("languagePack = true", res.get("languagePack") is True),
                (
                    f"replacements 条目 = {res.get('replCount')}",
                    res.get("replCount") == res.get("packCount"),
                ),
                ("已选其它语言时不注入中文", res.get("localeEnUntouched") is True),
                (
                    f"抽查 {res.get('checked')} 条译文一致",
                    res.get("mismatchCount") == 0,
                ),
                ("{0} 占位符仍可用", res.get("phOk") in (True, None)),
                ("未收录英文原样返回", res.get("unknownReturnsSource") is True),
            ]
            pk = res.get("packkeep") or {}
            if pk.get("present"):
                checks.append(("packkeep 用 Object.assign 合并", pk.get("mergeOk") is True))
                checks.append(
                    ("packkeep 保住自建中文表", pk.get("keepsOurReplacements") is True)
                )
                checks.append(
                    ("packkeep 不抹掉语言包自带表", pk.get("survivesMissingLocalization") is True)
                )
            elif "packkeep" in target.edits:
                checks.append(("packkeep 锚点存在", False))
            for name, good in checks:
                print(f"      {'OK ' if good else '!! '} {name}")
                all_ok = all_ok and good
            if res.get("mismatchCount"):
                print(f"      不一致样例: {res.get('mismatches')}")
            if verbose:
                print(f"      languageId={res.get('languageId')} 占位符样例={res.get('phKey')}")
        return all_ok


def target_nls_var(target: i18n.Target, text: str) -> str:
    """从文件里直接读出 nls 变量名。

    注入是「tail 锚点原文 + 注入块」的追加式，所以 tail 锚点在**已注入的文件里
    依然存在**，捕获组 a 就是 nls 变量名。这样新增目标文件时这里不用改，
    也不会因为变量名写错而误报（踩过：硬编码映射表漏了新增的 7 个文件，
    结果 harness 拿不到 nls 变量，报 "Cannot read properties"）。
    """
    m = i18n.A_TAIL.search(text)
    if m:
        return m.group("a")
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="验证 i18n 汉化结果")
    ap.add_argument("-g", "--path", required=True,
                  help="CubeMX2 安装目录（指到 dist/app 那一层也行）")
    ap.add_argument(
        "--dict",
        default=None,
        help="词典路径（默认按 resolve_dictionary 的优先级取当前生效那份）",
    )
    args = ap.parse_args(argv)

    try:
        pack, src = dictionary.current_pack(Path(args.dict) if args.dict else None)
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 取语言包失败: {e}")
        return 1
    print(f"词典: {src} -> 语言包 {len(pack):,} 条")
    print()

    root = locate.root_from_arg(args.path)
    if root is None:
        print(f"[错误] 不是有效的安装目录: {args.path}")
        return 1

    ok = verify(root, pack)
    print()
    print("结论:", "验证通过" if ok else "验证失败（建议立即回滚）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
