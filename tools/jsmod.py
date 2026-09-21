"""从 webpack 产物里精确抠出某个模块的源码。

为什么不能简单地数括号
----------------------
``core/i18n.py`` 的锚点用正则是够的（只匹配固定片段），但要**整段**
抠出一个模块函数，就必须知道它在哪里结束。天真的「括号配平」在这种
代码上会数错：

.. code-block:: javascript

    const l=/{([^}]+)}/g;      // 字符类里的 } 会被误当成块结束 → 深度少 1

于是要么提前截断、要么多吞一个字符，产出的 JS 直接语法错误。

所以这里做了个最小但够用的 JS 词法器，只为了**正确地跳过**：
字符串、模板字面量（含 ``${}`` 嵌套）、正则字面量、行/块注释。
正则与除号的区分沿用经典启发式：看前一个有效 token 是不是「值」。
"""
from __future__ import annotations

import re

# '/' 之后如果前一个有效 token 是这些，那 '/' 就是正则开头而不是除号
_REGEX_PREFIX_CHARS = set("(,=:[!&|?{};+-*%~^<>")
_REGEX_PREFIX_WORDS = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "case", "do", "else", "yield", "await", "throw",
}


def _scan_string(text: str, i: int) -> int:
    """i 指向引号，返回闭合引号之后的下标。"""
    quote = text[i]
    i += 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == quote:
            return i + 1
        i += 1
    return n


def _scan_template(text: str, i: int) -> int:
    """i 指向反引号，返回闭合反引号之后的下标（正确处理 ${} 嵌套）。"""
    i += 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i + 1
        if c == "$" and i + 1 < n and text[i + 1] == "{":
            end = _scan_balanced(text, i + 1)
            i = end if end > 0 else n
            continue
        i += 1
    return n


def _scan_regex(text: str, i: int) -> int:
    """i 指向 '/'，返回正则字面量（含 flags）之后的下标。"""
    i += 1
    n = len(text)
    in_class = False
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "\n":
            return i  # 未闭合，当作除号处理更安全
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            i += 1
            while i < n and (text[i].isalpha() or text[i].isdigit()):
                i += 1
            return i
        i += 1
    return n


def _scan_balanced(text: str, start: int) -> int:
    """从 ``text[start]``（``(`` / ``[`` / ``{``）开始配平，返回结束下标+1。

    失败返回 -1。
    """
    depth = 0
    i = start
    n = len(text)
    prev_char = ""   # 上一个有效字符
    prev_word = ""   # 上一个有效标识符（用于正则判定）
    while i < n:
        c = text[i]

        # ---- 注释
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue

        # ---- 字符串 / 模板
        if c in "\"'":
            i = _scan_string(text, i)
            prev_char, prev_word = '"', ""
            continue
        if c == "`":
            i = _scan_template(text, i)
            prev_char, prev_word = '"', ""
            continue

        # ---- 正则
        if c == "/":
            is_regex = (
                prev_char == ""
                or prev_char in _REGEX_PREFIX_CHARS
                or prev_word in _REGEX_PREFIX_WORDS
            )
            if is_regex:
                i = _scan_regex(text, i)
                prev_char, prev_word = '"', ""
                continue

        # ---- 括号配平
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i + 1

        if not c.isspace():
            if c.isalnum() or c in "_$":
                prev_word += c
            else:
                prev_word = ""
            prev_char = c
        i += 1
    return -1


def extract_module(text: str, module_id: int) -> str | None:
    """抠出 webpack 模块 ``module_id`` 的函数表达式源码。

    同时兼容两种写法::

        448496:(L=>{...})            单参数（只收 module）
        152985:((L,e,t)=>{...})      多参数
    """
    for m in re.finditer(r"[,{]\s*" + str(module_id) + r"\s*:\s*\(", text):
        start = m.end() - 1
        end = _scan_balanced(text, start)
        if end > 0:
            return text[start:end]
    return None


__all__ = ["extract_module"]
