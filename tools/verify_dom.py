"""DOM 通道（DOM 兜底）的落盘后验证：用真实 DOM 跑真实注入块。

和 ``tools/verify_i18n.py`` 的分工：
  · verify_i18n.py —— 验证 i18n 通道的注入块（语法 + 运行期语义 + 译文抽查）；
  · verify_dom.py  —— 验证 DOM 通道的追加块（真实 DOM 下的翻译行为 + 安全边界）。

验证对象是**从已注入的 bundle 里原样抠出来的代码**，不是 assets 里的源文件，
所以「注入过程改坏了」这种情况也会被抓住。加 ``--asset`` 则改测源文件，
用于注入之前的自检。

依赖 jsdom（仅验证需要，工具本体不依赖）：
    npm i jsdom
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import dictionary, i18n, locate  # noqa: E402

HARNESS = Path(__file__).resolve().parent / "dom_harness.js"


def modules_candidates() -> list[str | None]:
    """jsdom 可能所在的 node_modules 目录，按优先级。

    刻意**不含任何具体机器上的路径** —— 以前第二项写着
    ``C:\\Users\\<用户名>\\.workbuddy\\...\\node_modules``，那是维护者机器上的
    目录，既把用户名发布进公开仓库，对别人也没有意义。自己的非标准位置用
    ``CUBEMX2ZH_NODE_MODULES`` 指。
    """
    root = Path(__file__).resolve().parent.parent
    out: list[str | None] = [
        os.environ.get("CUBEMX2ZH_NODE_MODULES"),
        str(root / "node_modules"),
        str(root / "tools" / "node_modules"),
    ]
    # NODE_PATH 是 Node 自己找全局模块用的变量，装了全局 jsdom 的人这里就有
    out += [c for c in (os.environ.get("NODE_PATH") or "").split(os.pathsep) if c.strip()]
    return out


def find_modules() -> str | None:
    for c in modules_candidates():
        if c and (Path(c) / "jsdom").is_dir():
            return c
    return None


def extract_dom_block(text: str) -> str | None:
    i = text.find(i18n.DOM_MARKER)
    if i < 0:
        return None
    j = text.find(i18n.DOM_MARKER_END, i)
    if j < 0:
        return None
    return text[i : j + len(i18n.DOM_MARKER_END)]


def main() -> int:
    ap = argparse.ArgumentParser(description="DOM 通道（DOM 兜底）验证")
    ap.add_argument(
        "-g",
        "--path",
        help="CubeMX2 安装目录（指到 dist/app 那一层也行）",
    )
    ap.add_argument("--asset", action="store_true", help="改测 assets/dom-translate.js 源文件")
    args = ap.parse_args()

    if not HARNESS.is_file():
        print(f"缺少测试夹具: {HARNESS}")
        return 2

    node = i18n.find_node()
    if not node:
        print("未找到 node，无法执行 DOM 验证")
        return 2

    mods = find_modules()
    if not mods:
        print("未找到 jsdom。DOM 验证需要它，请先安装：")
        print("  npm i jsdom        （装进仓库根的 node_modules/，本工具会自动找到）")
        print("  或 npm i -g jsdom  （然后设 NODE_PATH，或直接设下面这个变量）")
        print("  set CUBEMX2ZH_NODE_MODULES=<含 jsdom 的 node_modules 目录>")
        tried = "、".join(str(c) for c in modules_candidates() if c)
        print(f"已试过：{tried}")
        return 2

    block: str | None
    source: str
    if args.asset:
        block = i18n.DOM_SCRIPT.read_text(encoding="utf-8")
        source = str(i18n.DOM_SCRIPT)
    else:
        picked = locate.pick_root(args.path)
        if picked.root is None:
            print(picked.problem())
            print("（也可以加 --asset 直接测 assets/dom-translate.js 源文件）")
            return 2
        root = picked.root
        print(f"安装目录: {root}  ({picked.source})")
        app = locate.app_dir(root)
        if not app:
            print(f"[错误] 未找到 app 目录: {root}")
            return 2
        bundle = app / "lib/frontend/bundle.js"
        if not bundle.is_file():
            print(f"找不到 {bundle}")
            return 2
        text = bundle.read_text(encoding="utf-8", errors="replace")
        block = extract_dom_block(text)
        source = f"{bundle} 中的注入块"
        if block is None:
            print("bundle.js 里没有找到 DOM 兜底块（还没注入？可以用 --asset 先测源文件）")
            return 2

    try:
        pack, src = dictionary.current_pack()
    except Exception as e:  # noqa: BLE001
        print(f"取语言包失败: {e}")
        return 2

    with tempfile.TemporaryDirectory() as td:
        blk = Path(td) / "block.js"
        blk.write_text(block, encoding="utf-8")
        # 语言包不再是磁盘上的文件，夹具要的是路径，就落到临时目录里
        pk = Path(td) / "pack.json"
        pk.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
        env = dict(os.environ)
        env["NODE_PATH"] = mods
        proc = subprocess.run(
            [node, str(HARNESS), str(blk), str(pk)],
            capture_output=True,
            text=True,
            errors="replace",
            env=env,
            timeout=180,
        )

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if "Cannot find module 'jsdom'" in err:
        print("node 找不到 jsdom（NODE_PATH 没生效）")
        return 2

    try:
        res = json.loads(out[out.index("{") :])
    except (ValueError, IndexError):
        print("验证脚本没能给出结果：")
        print(out[:2000] or "(无输出)")
        if err:
            print("--- stderr ---")
            print(err[:2000])
        return 1

    diag = res["diag"]
    print(f"被测代码: {source}")
    print(f"词典    : {src} -> 语言包 {len(pack):,} 条")
    print(f"jsdom   : {mods}")
    print()
    if diag.get("err"):
        print("注入块执行抛异常：")
        print(diag["err"])
        return 1
    if not diag.get("started"):
        print("注入块没启动（window.__CUBEMX2ZH_DOM__ 未设置）")
        return 1
    print(f"已启动  : 词条 {diag['size']:,} 条")
    st = diag.get("stats") or {}
    print(f"翻译统计: 文本 {st.get('text', 0)} 处 / 属性 {st.get('attr', 0)} 处 / 扫描 {st.get('scanned', 0)} 节点")
    print()
    failed = res.get("failed") or []
    print(f"断言 {res['total'] - len(failed)}/{res['total']} 通过")
    ok = not failed
    if ok:
        print("结论:DOM 兜底翻译器通过全部断言")
    else:
        print("结论: 存在失败断言")
        for c in failed:
            print(f"  [FAIL] {c['name']}")
            print(f"         实际: {c['actual']!r}")
            print(f"         期望: {c['expected']!r}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
