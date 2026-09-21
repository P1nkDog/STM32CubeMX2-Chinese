"""STM32CubeMX2 中文汉化工具核心库。

汉化机制只有一条：i18n 注入（`i18n`）+ DOM 兜底（`assets/dom-translate.js`），
语言包由 `langpack` 从词典构建。

上一代（v0.1.0）的字面量字节替换策略已于 v0.2.0 移除。
"""

__version__ = "0.2.0"
