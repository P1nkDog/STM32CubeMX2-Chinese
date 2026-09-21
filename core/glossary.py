"""术语门禁：核对语言包里的 STM32 术语译法是否与术语表一致。

为什么要有这个门禁
------------------
「所有翻译都要和 ST 官方中文文档对齐」如果只写成文档里的一句话，很快就会
被遗忘或走样（凭语感翻出来的「低/中/高/非常高」就是这么进来的）。
把它变成可执行的门禁之后，译法一旦偏离官方用词就会**直接报错**，
而不是等到用户在界面上发现。

检查三件事
----------
1. **terms**：术语表规定的译法，语言包里必须一模一样；
2. **keep_english**：官方与业界惯例直接用英文缩写的专有名词（GPIO/EXTI/HAL…）
   **不应**出现在语言包里 —— 进了语言包就意味着界面会被改成中文；
3. **scope**：多义词（如 Speed 下的 Low/High）的字段译法必须
   · 真的内嵌在 ``assets/dom-translate.js`` 的 FIELD_MAP 里（否则作用域白写）；
   · 且与全局译法**不同**（若相同，说明全局表已经把速度那套用掉了，
     电平字段会被误译）。

为什么这个模块放在 `core/` 而不是只留 `tools/check_glossary.py`
--------------------------------------------------------------
门禁是**落盘前的运行时检查**，不是一次性开发脚本。原先 `main.py` 用
`subprocess` 去起 `tools/check_glossary.py`，而 PyInstaller 的 `datas`
里没有 `tools/`，于是 EXE 里 `tool.exists()` 恒为假、门禁静默放行 ——
README 承诺的「违规直接中止」在用户实际下载的那个包里从未生效。
（即便把 tools 打进 datas 也不行：frozen 下 `sys.executable` 就是 EXE 本身。）

所以逻辑放这里，由 `main.py` 直接 import 调用；`tools/check_glossary.py`
退化成命令行外壳，CI 与手工核对仍用老命令。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import paths


@dataclass
class Report:
    passes: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def brief(self, verbose: bool = False) -> str:
        lines = [f"  OK   {p}" for p in self.passes] if verbose else []
        lines += [f"  WARN {w}" for w in self.warns]
        lines += [f"  FAIL {e}" for e in self.errors]
        lines.append("")
        lines.append(
            "术语门禁：%d 项通过 / %d 项告警 / %d 项违规"
            % (len(self.passes), len(self.warns), len(self.errors))
        )
        if self.errors:
            lines.append(
                "结论: 存在与 ST 官方中文用词不一致的译法，"
                "请修 rules/glossary.zh.json 或对应词条。"
            )
        elif self.warns:
            # 别在跳过核对的情况下断言「全部一致」——那正是本次要修的静默降级
            lines.append(
                "结论: 无违规，但有 %d 项告警（未收录或跳过的核对项），见上。"
                % len(self.warns)
            )
        else:
            lines.append("结论: 全部术语与术语表一致")
        return "\n".join(lines)


def unescape_js(text: str) -> str:
    """把 JS 源码里的 \\uXXXX 转义还原成真字符。

    dom-translate.js 里的中文一律写成转义（避免源码编码问题），
    所以直接搜中文是搜不到的，必须先还原。
    """
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)


def check(pack: dict[str, str], gloss: dict, dom_src: str) -> Report:
    """对一份扁平语言包做术语核对。纯函数，不碰磁盘。"""
    rep = Report()
    repl = pack.get("replacements", pack)  # 兼容 {languageId, replacements} 包装形态

    # ---- 1) 术语译法一致 --------------------------------------------------
    for en, zh in (gloss.get("terms") or {}).items():
        if en.startswith("_"):
            continue
        if en not in repl:
            rep.warns.append(
                "术语未出现在语言包: %r（界面可能确实没这个词，不阻塞）" % en
            )
            continue
        if repl[en] != zh:
            rep.errors.append("译法不符: %r  语言包=%r  术语表=%r" % (en, repl[en], zh))
        else:
            rep.passes.append("术语 %s → %s" % (en, zh))

    # ---- 2) 专有名词不得被翻译 --------------------------------------------
    for en in gloss.get("keep_english") or []:
        if en in repl:
            rep.errors.append(
                "专有名词不应进语言包: %r（当前会被翻成 %r）" % (en, repl[en])
            )
        else:
            rep.passes.append("专有名词 %s 保持英文" % en)

    # ---- 3) 多义词的作用域译法 --------------------------------------------
    for field_name, mapping in (gloss.get("scope") or {}).items():
        if field_name.startswith("_") or not isinstance(mapping, dict):
            continue
        for en, zh in mapping.items():
            if zh not in dom_src:
                rep.errors.append(
                    "作用域译法没进 dom-translate.js: %s/%s = %r"
                    % (field_name, en, zh)
                )
            else:
                rep.passes.append("作用域 %s/%s → %s" % (field_name, en, zh))
            if repl.get(en) == zh:
                rep.errors.append(
                    "多义词 %r 的全局译法与作用域译法相同（%r）——"
                    "全局表会先生效，作用域形同虚设" % (en, zh)
                )

    return rep


def run(pack: dict[str, str]) -> Report | None:
    """读术语表与 DOM 脚本，核对语言包。术语表缺失时返回 None（调用方自行放行）。"""
    gp = paths.glossary_path()
    if gp is None:
        return None
    gloss = json.loads(gp.read_text(encoding="utf-8"))

    from . import i18n  # 延迟导入：只有这里需要 DOM 脚本路径

    if not i18n.DOM_SCRIPT.is_file():
        # 找不到兜底翻译器就没法核对作用域译法。这是打包缺件，不是翻译问题，
        # 报 Warn 放行 —— 否则会因为这个而彻底无法汉化。
        return Report(
            warns=[
                f"未找到 {i18n.DOM_SCRIPT}，跳过作用域译法核对（打包缺件，"
                "见 STM32CubeMX2-Chinese.spec 的 datas）"
            ]
        )
    dom_src = unescape_js(
        i18n.DOM_SCRIPT.read_text(encoding="utf-8", errors="replace")
    )
    return check(pack, gloss, dom_src)
