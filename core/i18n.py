"""i18n 通道：Theia i18n 注入引擎（不写盘，只做文本变换）。

为什么改这条路
--------------
CubeMX2 是 Theia + Electron 应用，界面文案都走框架自带的 i18n API。
在 CubeMX2 1.1.1 上实测，其解析链是：

    nls.localizeByDefault(英文原文)
      → getDefaultKey(英文原文)                 # 用编译进去的 nls 元数据反查 key
      → Localization.localize(localization, key, 英文原文)
            ├─ localization.replacements[英文原文]    ★ 优先，按英文原文直接命中
            └─ localization.translations[key]
      → format(译文, 参数)                       # {0} 占位符由框架自己处理

也就是说框架**原生支持「按英文原文查表」**。只要把 {英文原文: 中文}
填进 ``localization.replacements``，所有走 i18n API 的调用点一次性生效，
不再需要对每个字面量做字节替换，也不必对大文件做字符串手术。

需要注入的四件事
----------------
1. ``fallback``  —— ``localizeByDefault`` 在英文原文反查不到 key 时会**直接
   返回英文**（根本不进 localize），必须改成先进查表。
2. ``tail``      —— 在 nls 模块初始化时把语言包装进 ``nls.localization``，
   并把当前 locale 设为 zh-cn。
3. ``packkeep``  —— 前端 ``I18nPreloadContribution`` 在拿到语言包时会
   ``nls.localization = p`` 整个覆盖，会把我们的 replacements 冲掉，改成合并。
4. ``zhpack``    —— 把框架自带的 zh-cn 包标记成真正的 languagePack。
   实测框架内置 zh-cn 有 1293 条，但都是 **Theia 自身**（AI/notebook/
   terminal/vsx）的显式键文案，不含 VS Code 工作台文案；不标记
   languagePack 它连加载机会都没有（getAvailableLanguages 会把它过滤掉）。

i18n 通道的边界（为什么还需要 DOM 通道）
----------------------------------
B 只能覆盖**走了 i18n API** 的文案。实测 CubeMX2 的 bundle.js 里，
语言包 3144 条中：
  · 1166 条出现在 ``localizeByDefault(...)`` / ``nls.localize(...,"...")`` 里 → i18n 通道管
  · 1571 条**只以裸字符串出现**，例如 ST 自己写的 React 代码
        ``createElement(Button, {...}, "Reset pins")``
        ``leftLabel:"Graphic view", rightLabel:"Table view"``
    Pinout 主界面整片都是这种 → 必须有 DOM 层兜底（DOM 通道）。

DOM 通道（``dom``）就是**在 bundle 末尾追加** ``assets/dom-translate.js``：
浏览器端 ``index.html`` 是 ``<script src="./bundle.js">``，所以追加的代码会在
渲染进程里执行；它从 ``window.__CUBEMX2ZH__`` 取同一份中文表（不复制数据），
按**整串精确匹配**翻译文本节点与 placeholder/title 等属性，并用
MutationObserver 跟进动态渲染。用户选了非中文语言时那份表不会被注入，
C 自动空转，不会越权。

设计原则
--------
- **全部用正则锚点定位，不用硬编码偏移**：应用升级后小版本改名也能适配。
- **每条编辑都要求唯一命中**，命中数不等于 1 直接报错，绝不猜。
- **幂等**：注入块带 MARKER，重复执行先还原 `.orig` 再注入。
- **可校验**：注入后交给 `node --check` 做语法门禁。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import langpack

# ---------------------------------------------------------------------------
# 幂等标记
# ---------------------------------------------------------------------------

MARKER = "/*__CUBEMX2ZH__*/"
MARKER_END = "/*__CUBEMX2ZH_END__*/"

# DOM 通道：追加在 bundle 末尾的 DOM 兜底翻译器。
# 注意 DOM_MARKER 故意不与 MARKER 互为子串，避免幂等判断互相误判。
DOM_MARKER = "/*__CUBEMX2ZH_DOM_V1__*/"
DOM_MARKER_END = "/*__CUBEMX2ZH_DOM_V1_END__*/"

# 注入用的静态资源目录（打包 EXE 时要一起带上，见 STM32CubeMX2-Chinese.spec）
ASSETS = Path(__file__).resolve().parent.parent / "assets"
DOM_SCRIPT = ASSETS / "dom-translate.js"

# ---------------------------------------------------------------------------
# 锚点
# ---------------------------------------------------------------------------

# 1) localizeByDefault 的兜底返回：命中不到的英文原文直接返回，绕过了查表
A_FALLBACK = re.compile(
    r"return (?P<locmod>[A-Za-z_$][\w$]*)\.Localization\.format\("
    r"(?P<value>[A-Za-z_$][\w$]*),(?P<args>[A-Za-z_$][\w$]*)\)\}"
    r"(?P<exp>[A-Za-z_$][\w$]*)\.localizeByDefault="
)

# nls 模块里 localize(key, value, ...args) 这个包装函数的名字
A_LOCFN = re.compile(
    r"function (?P<fn>[A-Za-z_$][\w$]*)\((?P<k>[A-Za-z_$][\w$]*),(?P<v>[A-Za-z_$][\w$]*)"
    r",\.\.\.(?P<rest>[A-Za-z_$][\w$]*)\)\{return [A-Za-z_$][\w$]*\.Localization\.localize\("
    r"(?P<nls>[A-Za-z_$][\w$]*)\.localization,"
)

# 2) nls 模块 IIFE 的结尾：})(nls||(e.nls=nls={}));
A_TAIL = re.compile(
    r"\}\)\((?P<a>[A-Za-z_$][\w$]*)\|\|\((?P<b>[A-Za-z_$][\w$]*)\.nls=(?P=a)=\{\}\)\);"
)

# 3) 语言包到达时的整体覆盖点
A_PACKKEEP = re.compile(
    r"(?P<flag>[A-Za-z_$][\w$]*)\.languagePack\?"
    r"(?P<nls>[A-Za-z_$][\w$]*)\.nls\.localization=(?P<p>[A-Za-z_$][\w$]*):"
)

# 4) 框架自带 zh-cn 包的注册点
A_ZHPACK = re.compile(
    r"(?P<reg>[A-Za-z_$][\w$]*)\.registerLocalizationFromRequire\("
    r"\"zh-cn\",(?P<mod>[A-Za-z_$][\w$]*)\((?P<mid>\d+)\)\)"
)


@dataclass
class Edit:
    """一条待应用的编辑。"""

    name: str
    desc: str
    pattern: re.Pattern
    make: callable  # (match, ctx) -> str  返回完整替换文本
    required: bool = True


@dataclass
class Target:
    """一个待注入的 bundle。

    ``edits`` 是锚点式（改函数，命中数必须唯一）；
    ``dom`` 是追加式（在文件末尾追加 DOM 兜底翻译器，不需要锚点）。
    """

    key: str
    rel: str
    edits: list[str]
    gz: bool = False
    dom: bool = False


TARGETS: list[Target] = [
    # ---- 前端：用户看到的一切都在这里 ----
    Target(
        key="lib/frontend/bundle.js",
        rel="lib/frontend/bundle.js",
        edits=["fallback", "tail", "packkeep"],
        gz=True,
        dom=True,  # Pinout 等 ST 自绘界面全靠它
    ),
    Target(
        key="lib/frontend/secondary-window.js",
        rel="lib/frontend/secondary-window.js",
        edits=["fallback", "tail"],
        dom=True,  # 第二个窗口是同一套界面，同样需要兜底
    ),
    Target(
        key="lib/frontend/778.js",
        rel="lib/frontend/778.js",
        # 懒加载 chunk，同一个 webpack runtime。它**自带一份 nls 模块**
        # （独立闭包），不注入的话这条通道上的框架文案永远是英文。
        edits=["fallback", "tail"],
        gz=True,
        dom=True,
    ),
    # ---- 后端 / 主进程：消息、通知、原生菜单、对话框 ----
    # scripts/theia-electron-main.js 结尾 require('../lib/backend/electron-main.js')，
    # 所以 electron-main.js 才是 Electron 主进程真正的入口；main.js 是后端服务进程。
    # 这两个都必须注入，其余几个是本应用架构里的其它 Node 入口，一并覆盖。
    Target(
        key="lib/backend/main.js",
        rel="lib/backend/main.js",
        edits=["fallback", "tail", "zhpack"],
    ),
    Target(
        key="lib/backend/electron-main.js",
        rel="lib/backend/electron-main.js",
        edits=["fallback", "tail"],
    ),
    Target(
        key="lib/backend/plugin-host.js",
        rel="lib/backend/plugin-host.js",
        edits=["fallback", "tail"],
    ),
    Target(
        key="lib/backend/backend-init-theia.js",
        rel="lib/backend/backend-init-theia.js",
        edits=["fallback", "tail"],
    ),
    Target(
        key="lib/backend/ipc-bootstrap.js",
        rel="lib/backend/ipc-bootstrap.js",
        edits=["fallback", "tail"],
    ),
    Target(
        key="lib/backend/plugin-vscode-init.js",
        rel="lib/backend/plugin-vscode-init.js",
        edits=["fallback", "tail"],
    ),
    Target(
        key="lib/backend/parcel-watcher.js",
        rel="lib/backend/parcel-watcher.js",
        edits=["fallback", "tail"],
    ),
]


# ---------------------------------------------------------------------------
# 生成的代码片段
# ---------------------------------------------------------------------------


def _install_block(nls: str, pack_json: str) -> str:
    """在 nls 模块里安装语言包。

    注意（踩过的三个坑，每个都靠 node --check 门禁拦下来）：

    1. 用字符串拼接而不是 f-string —— JS 的花括号和 Python 格式化语法
       会互相打架，曾经产出过非法 JS。
    2. ``if(cond)`` 的 then 分支**必须用花括号包起来**。写成
       ``if(c)N.localization={...}else if(...)`` 是非法语法：``else``
       前面既没有 ``;`` 也没有换行，ASI 不会插入分号，于是
       ``SyntaxError: Unexpected token 'else'``。
       **同一条规则适用于块内每一条语句**：只要上一条语句以对象字面量的
       ``}`` 结尾，紧跟 ``if`` / ``else`` 等关键字就必须在新语句**开头**补 ``;``。
       这个坑在本文件里踩过两次（第一次是 ``else``，第二次是往块里加
       ``window.__CUBEMX2ZH__`` 那一句），两次都被自检/语法门禁拦下。
    3. ``try{}`` 的花括号必须严格配平（曾经多一个 ``}`` 导致 try 提前闭合）。
    4. 里面还顺手把这份表挂到 ``window.__CUBEMX2ZH__`` 给 DOM 通道使用。
       挂的是同一个对象引用，不会让 bundle 多一份 210KB 的中文表。
    """
    n = nls
    head = (
        "try{"
        "if(!" + n + ".locale)" + n + '.locale="zh-cn";'
        # ← 花括号包住 then 分支，规避 ASI 陷阱（见坑 2）
        "if(" + n + '.locale==="zh-cn"){' + n + ".localization={"
        'languageId:"' + langpack.LOCALE_ID + '",'
        'languageName:"' + langpack.LOCALE_NAME + '",'
        'localizedLanguageName:"' + langpack.LOCALE_NATIVE_NAME + '",'
        + "languagePack:!0,translations:{},replacements:" + pack_json
        + "}"  # 闭合 localization 对象字面量
        # 顺手把这份表挂到 window 上，交给 DOM 通道的 DOM 兜底翻译器用。
        # 是**同一份对象引用**，所以不额外占体积（bundle 里只有一份中文表）；
        # 后端是 Node 进程，typeof window==="undefined" 会直接跳过。
        # 注意开头的 "; "：上一条语句以对象字面量 "}" 结尾，紧跟 if 既无分号
        # 也无换行，ASI 不会插分号 —— 这是和 else 同源的坑，被自检抓过。
        + ';if(typeof window!=="undefined"){try{window.__CUBEMX2ZH__='
        + n + ".localization}catch(_){}}"
        + "}"  # 闭合 then 分支
    )
    tail = (
        # else 现在跟的是「块语句」，不再是「表达式语句」，语法合法
        "else if(console&&console.warn)console.warn("
        '"[STM32CubeMX2-Chinese] locale="+' + n + '.locale+'
        '"，已跳过中文注入（如需中文请把显示语言设为简体中文）");'
        "}"
        "catch(_){}"
    )
    return MARKER + head + tail + MARKER_END


def _dom_block() -> str:
    """DOM 通道：追加在 bundle 末尾的 DOM 兜底翻译器（见 assets/dom-translate.js）。"""
    if not DOM_SCRIPT.is_file():
        raise FileNotFoundError(f"缺少 DOM 兜底脚本: {DOM_SCRIPT}")
    body = DOM_SCRIPT.read_text(encoding="utf-8")
    # 前置换行是必须的：bundle.js 结尾是 `//# sourceMappingURL=bundle.js.map`
    # 这样的一行注释，不换行追加会把我们的代码整段吞进注释里。
    return "\n" + DOM_MARKER + "\n" + body + "\n" + DOM_MARKER_END + "\n"


def _zhpack_meta() -> str:
    return (
        '{languageId:"%s",languageName:"%s",localizedLanguageName:"%s",languagePack:!0}'
        % (langpack.LOCALE_ID, langpack.LOCALE_NAME, langpack.LOCALE_NATIVE_NAME)
    )


EDIT_BUILDERS: dict[str, Edit] = {}


def _register_edits() -> dict[str, Edit]:
    if EDIT_BUILDERS:
        return EDIT_BUILDERS

    def make_fallback(m: re.Match, ctx: dict) -> str:
        locfn = ctx.get("locfn")
        if not locfn:
            raise KeyError("缺少 localize 包装函数名（locfn）")
        return (
            f'return {locfn}("",{m.group("value")},...{m.group("args")})}}'
            f'{m.group("exp")}.localizeByDefault='
        )

    def make_tail(m: re.Match, ctx: dict) -> str:
        return m.group(0) + _install_block(m.group("a"), ctx["pack_json"])

    def make_packkeep(m: re.Match, ctx: dict) -> str:
        f, n, p = m.group("flag"), m.group("nls"), m.group("p")
        # 两个必须同时满足的点：
        #  a) 三元运算符的分支必须是 AssignmentExpression，逗号表达式必须加括号，
        #     否则 `a?b,c:d` 是非法语法（曾因此在 bundle.js 上炸过语法校验）。
        #  b) 用 Object.assign 做三路合并，而不是直接 `p.replacements=(...).replacements`。
        #     后者在 `nls.localization` 还不存在时会把 p 自己的 replacements
        #     赋成 undefined，等于把语言包自带的替换表也一并抹掉。
        #     合并顺序让**我们的中文表优先**（放最后），且永不产生 undefined。
        return (
            f"{f}.languagePack?("
            f"{p}.replacements=Object.assign({{}},{p}.replacements,"
            f"({n}.nls.localization||{{}}).replacements),"
            f"{n}.nls.localization={p}"
            f"):"
        )

    def make_zhpack(m: re.Match, ctx: dict) -> str:
        return (
            f'{m.group("reg")}.registerLocalizationFromRequire({_zhpack_meta()},'
            f'{m.group("mod")}({m.group("mid")}))'
        )

    EDIT_BUILDERS.update(
        {
            "fallback": Edit(
                "fallback",
                "localizeByDefault 兜底改为先查 replacements（否则反查不到 key 的文案永远是英文）",
                A_FALLBACK,
                make_fallback,
            ),
            "tail": Edit(
                "tail",
                "在 nls 模块装载语言包并把 locale 设为 zh-cn",
                A_TAIL,
                make_tail,
            ),
            "packkeep": Edit(
                "packkeep",
                "语言包到达时合并而非覆盖 replacements（否则自建表被冲掉）",
                A_PACKKEEP,
                make_packkeep,
            ),
            "zhpack": Edit(
                "zhpack",
                "把框架自带 zh-cn 包标记为 languagePack（否则它进不了可用语言列表）",
                A_ZHPACK,
                make_zhpack,
            ),
        }
    )
    return EDIT_BUILDERS


# ---------------------------------------------------------------------------
# 探测
# ---------------------------------------------------------------------------


@dataclass
class Probe:
    target: str
    rel: str
    exists: bool = False
    size: int = 0
    injected: bool = False
    hits: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exists and not self.problems


def probe_text(text: str, target: Target, app_dir: Path | None = None) -> Probe:
    edits = _register_edits()
    p = Probe(target=target.key, rel=target.rel, exists=True, size=len(text))
    p.injected = MARKER in text or DOM_MARKER in text
    for name in target.edits:
        edit = edits[name]
        n = len(edit.pattern.findall(text))
        p.hits[name] = n
        if not edit.required or n == 1:
            continue
        # 「已注入」状态下，除 tail 外的锚点都**已经被改写掉了**，
        # 命中 0 次是预期结果，不是错误（否则重复探测会一直报失败）。
        # tail 是特例：注入块是**追加在 tail 之后**的，所以它必须还在。
        if p.injected and name != "tail":
            p.notes.append(f"锚点 {name} 已被改写（命中 {n} 次，预期为 0）")
            continue
        p.problems.append(f"锚点 {name} 命中 {n} 次（期望 1 次）")
    # tail 需要同时拿到 localize 包装函数名，单独校验
    if "fallback" in target.edits:
        locfn = len(A_LOCFN.findall(text))
        p.hits["locfn"] = locfn
        if locfn != 1:
            p.problems.append(f"locfn 锚点命中 {locfn} 次（期望 1 次）")
    # DOM 通道是「追加式」，没有锚点可校验，只报告在不在
    if target.dom:
        p.hits["dom"] = 1 if DOM_MARKER in text else 0
    return p


def probe(app_dir: Path) -> list[Probe]:
    out: list[Probe] = []
    for target in TARGETS:
        path = app_dir / target.rel
        if not path.is_file():
            out.append(
                Probe(target=target.key, rel=target.rel, exists=False,
                      problems=["文件不存在"])
            )
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        out.append(probe_text(text, target, app_dir))
    return out


# ---------------------------------------------------------------------------
# 注入
# ---------------------------------------------------------------------------


def inject_text(
    text: str,
    target: Target,
    pack: dict[str, str],
    *,
    strict: bool = True,
) -> tuple[str, list[str]]:
    """对单个 bundle 文本做注入，返回 (新文本, 日志)。不写盘。"""
    edits = _register_edits()
    p = probe_text(text, target)
    if p.injected:
        raise ValueError(f"{target.rel} 已包含注入标记，请先回滚/还原再注入")
    if strict and not p.ok:
        raise ValueError(f"{target.rel} 锚点校验失败: " + "；".join(p.problems))

    ctx = {
        "pack_json": langpack.js_literal(pack),
        "locfn": None,
    }
    logs: list[str] = []

    for name in target.edits:
        edit = edits[name]
        matches = list(edit.pattern.finditer(text))
        if len(matches) != 1:
            logs.append(f"  [跳过] {name}: 命中 {len(matches)} 次")
            continue

        m = matches[0]
        if name == "fallback":
            ctx["locfn"] = A_LOCFN.search(text).group("fn")
        elif name == "tail":
            # tail 的替换依赖 pack_json，已在 ctx 里
            pass

        replacement = edit.make(m, ctx)
        text = text[: m.start()] + replacement + text[m.end() :]
        logs.append(f"  [OK] {name}: {edit.desc}")

    # DOM 通道：追加式，放最后（不依赖任何锚点，应用改版也不会失配）
    if target.dom:
        block = _dom_block()
        text = text + block
        logs.append(
            f"  [OK] dom: 追加 DOM 兜底翻译器（DOM 通道，{len(block):,} 字节；"
            "整串精确匹配 + 用户内容区黑名单）"
        )

    return text, logs


# ---------------------------------------------------------------------------
# 语法门禁
# ---------------------------------------------------------------------------

def _node_candidates() -> list[str]:
    """PATH 里找不到 node 时的兜底位置 —— 只有**标准安装位置**。

    这里以前第一行写着 ``C:\\Users\\<维护者的用户名>\\.workbuddy\\...\\node.exe``：
    对别人 clone 的仓库毫无意义，还把用户名发布进了公开仓库。真要指自己的
    非标准 node，设 ``CUBEMX2ZH_NODE`` 环境变量即可（优先级最高）。
    """
    out: list[str] = []
    for key in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(key)
        if base:
            out.append(str(Path(base) / "nodejs" / "node.exe"))
    return out


def find_node() -> str | None:
    env = os.environ.get("CUBEMX2ZH_NODE")
    if env and Path(env).is_file():
        return env
    found = shutil.which("node")
    if found:
        return found
    for c in _node_candidates():
        if Path(c).is_file():
            return c
    return None


def node_check(path: Path) -> tuple[bool, str]:
    """用 node --check 做 JS 语法校验。node 不可用时返回 (True, 'skipped')。"""
    node = find_node()
    if not node:
        return True, "未找到 node，跳过语法校验"
    try:
        proc = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as e:  # noqa: BLE001
        return True, f"语法校验未执行: {e}"
    if proc.returncode == 0:
        return True, "语法校验通过"
    raw = (proc.stderr or proc.stdout or "").strip()
    # node 的报错第一行是文件名，真正的错误在后面几行
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    detail = " | ".join(lines[:4])[:400]
    return False, f"语法校验失败: {detail or f'exit={proc.returncode}'}"


# ---------------------------------------------------------------------------
# 覆盖率评估
# ---------------------------------------------------------------------------

RX_LBD = re.compile(r'localizeByDefault\(\s*("(?:[^"\\]|\\.)*")')
RX_LOC = re.compile(
    r'\.localize\(\s*"(?:[^"\\]|\\.)*"\s*,\s*("(?:[^"\\]|\\.)*")'
)


def _unquote(literal: str) -> str:
    return langpack.js_unescape(literal[1:-1])


def i18n_literals(text: str) -> set[str]:
    """抽出所有 i18n 调用点的英文原文（localizeByDefault / nls.localize 的 value）。"""
    out = {_unquote(m.group(1)) for m in RX_LBD.finditer(text)}
    out |= {_unquote(m.group(1)) for m in RX_LOC.finditer(text)}
    out.discard("")
    return out


@dataclass
class Coverage:
    per_file: list[tuple[str, int, int, int]] = field(default_factory=list)
    total: int = 0
    hit: int = 0
    missing: set[str] = field(default_factory=set)
    # 语言包（3144 条）按落地通道分类
    pack_size: int = 0
    ch_i18n: set[str] = field(default_factory=set)   # 走 i18n API，i18n 通道负责
    ch_dom: set[str] = field(default_factory=set)   # 只在裸字符串位置，DOM 通道负责
    ch_none: set[str] = field(default_factory=set)  # 两个 bundle 里都没有

    @property
    def ratio(self) -> float:
        return self.hit / self.total if self.total else 0.0

    def brief(self) -> str:
        lines = [
            "─ i18n 调用点覆盖率（i18n 通道的视角）" + "─" * 36,
            f"{'文件':<38}{'i18n字面量':>11}{'语言包命中':>11}{'命中率':>8}",
        ]
        for rel, total, hit, _miss in self.per_file:
            lines.append(
                f"{rel:<38}{total:>11}{hit:>11}{hit / max(total, 1) * 100:>7.0f}%"
            )
        lines.append(
            f"{'合计':<38}{self.total:>11}{self.hit:>11}{self.ratio * 100:>7.0f}%"
        )
        lines.append(f"未覆盖（需补翻译）: {len(self.missing)} 条")
        lines.append("")
        lines.append("─ 语言包落地通道（整份语言包 {:,} 条）".format(self.pack_size) + "─" * 20)
        lines.append(f"  i18n 通道  走 i18n API（fallback/tail/packkeep）: {len(self.ch_i18n):>5} 条")
        lines.append(f"  DOM 通道  只以裸字符串出现，靠 DOM 兜底         : {len(self.ch_dom):>5} 条")
        lines.append(f"  ——     两个 bundle 里都没有（多在设置项）   : {len(self.ch_none):>5} 条")
        return "\n".join(lines)


RX_LITERAL = re.compile(r'"((?:[^"\\\n]|\\.){1,120})"')
RX_I18N_CTX = re.compile(r"(?:localizeByDefault|localize2?)\s*\([^()]{0,160}$")


def literal_index(text: str) -> tuple[dict[str, int], set[str]]:
    """扫一遍全文的双引号字面量。

    返回 (值 -> 出现次数, 至少一次出现在 i18n 调用参数里的值的集合)。
    """
    counts: dict[str, int] = {}
    in_i18n: set[str] = set()
    for m in RX_LITERAL.finditer(text):
        raw = m.group(1)
        if "\\" in raw:
            try:
                val = json.loads('"' + raw + '"')
            except ValueError:
                continue
        else:
            val = raw
        counts[val] = counts.get(val, 0) + 1
        if val not in in_i18n and RX_I18N_CTX.search(
            text[max(0, m.start() - 170) : m.start()]
        ):
            in_i18n.add(val)
    return counts, in_i18n


def channels(
    app_dir: Path, pack: dict[str, str]
) -> tuple[set[str], set[str], set[str]]:
    """把语言包按「靠哪条通道落地」分类。

    · i18n 通道：该英文原文出现在 ``localizeByDefault(...)`` / ``nls.localize(...,"…")`` 里；
    · DOM 通道：只以裸字符串出现（ST 自绘界面），只能靠 DOM 兜底；
    · 都没有：该条目在两个 bundle 里都找不到，多半属于后端设置项文案。
    """
    keys = set(pack)
    seen: set[str] = set()
    b: set[str] = set()
    for target in TARGETS:
        path = app_dir / target.rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        counts, in_i18n = literal_index(text)
        for k in keys:
            if k in counts:
                seen.add(k)
                if k in in_i18n:
                    b.add(k)
    return b, seen - b, keys - seen


def coverage(app_dir: Path, pack: dict[str, str]) -> Coverage:
    cov = Coverage()
    keys = set(pack)
    for target in TARGETS:
        path = app_dir / target.rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lits = i18n_literals(text)
        hit = lits & keys
        miss = lits - keys
        cov.per_file.append((target.key, len(lits), len(hit), len(miss)))
        cov.total += len(lits)
        cov.hit += len(hit)
        cov.missing |= miss
    cov.pack_size = len(pack)
    cov.ch_i18n, cov.ch_dom, cov.ch_none = channels(app_dir, pack)
    return cov


def missing_report(app_dir: Path, pack: dict[str, str]) -> list[tuple[str, int]]:
    """未覆盖文案 + 命中它的目标文件数，按（次数降序，文本升序）排。

    计数不是字节级出现次数：同一个字面量在一个 bundle 里出现 50 次也只 +1，
    所以并列极多 —— 一条设置项说明会同时出现在 10 个 bundle 里，就是 10。

    并列项必须有**确定**的次序。以前直接返回 ``Counter.most_common()``，
    同次数的条目按插入序排，而插入序来自 set 迭代、受 ``PYTHONHASHSEED``
    影响 —— 同一份代码连跑两次，Top 30 就不一样，等于没法拿它做对照。
    """
    keys = set(pack)
    counter: Counter = Counter()
    for target in TARGETS:
        path = app_dir / target.rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for lit in i18n_literals(text) - keys:
            counter[lit] += 1
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
