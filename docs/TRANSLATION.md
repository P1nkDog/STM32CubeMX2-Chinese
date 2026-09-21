# 翻译贡献指南

本项目的核心资产是**词典**（`dict/localization.json`）：一张扁平的
`{"界面英文原文": "中文"}` 映射表。

本指南说明：怎么找到该翻的文案、怎么改词典、怎么验证、怎么提交。

---

## 1. 词典是怎么生效的

```
dict/localization.json          ← 你改这个（唯一词典）
   │  python main.py --patch    ← 汉化时现场构建语言包，没有单独的构建步骤
   ├─ i18n 通道：注入框架的 localization.replacements，走 i18n API 的文案直接生效
   └─ DOM 通道：同一张表挂到 window.__CUBEMX2ZH__，DOM 兜底翻译器整串匹配裸字符串
```

**词典的键必须与界面上显示的英文逐字节相等。** 这是最重要的一条规则，
下面第 4 节展开。

---

## 2. 准备工作

1. 安装 STM32CubeMX2（版本需与词典 `targetApp.testedVersions` 一致）。
2. 克隆本仓库。
3. `python main.py --doctor -g <安装目录>`，确认能定位安装目录、词典与语言包条数正常。

---

## 3. 找到该翻什么

按「投入产出比」从高到低：

| 手段 | 拿到什么 | 适用 |
|------|---------|------|
| **界面上正常用一遍软件**，F12 执行 `__cubemx2zhMiss("text")` | 界面上真实出现过、但词典里没有的英文 | **最快最准**。运行时数据只有这样才能收到 |
| `python tools/dump_missing.py -g <安装目录>` | 走了 i18n 调用但词典里没有的 | 补框架文案（菜单、命令、设置项） |
| `python tools/scan_bare_ui_text.py -g <安装目录>` | 界面上的裸字符串缺口（带可见度打分） | 补 ST 自绘界面 |
| `python main.py --coverage -g <安装目录>` | 整体命中率 + 未覆盖 Top N | 看全局，定优先级 |

`--coverage` 输出里的**三通道分类**比百分比有用得多：它告诉你词典里有多少条
走 i18n 通道、多少条只能靠 DOM 通道、多少条在 bundle 里根本搜不到（那些是运行时数据，
只能靠上面第一种手段收集）。

---

## 4. 改词典

### 方式一：直接编辑（推荐，改几条时用这个）

打开 `dict/localization.json`，在 `entries` 里加行：

```json
  "Open Project": "打开工程",
  "Go to project location": "前往工程位置",
```

一条一行、键按字典序排列，所以 git diff 很好读。改完直接 `--patch` 验证。

### 方式二：导出工作副本（批量翻译时用）

```powershell
python main.py --export-dict    # 导出到仓库根的 localization.json
# 编辑那个文件的 entries
python main.py --import-dict    # 校验 + 术语门禁，通过后导回 dict/
python main.py --patch -g <安装目录>
```

工作副本优先于仓库词典被读取，所以改完不导回也能先验证效果。
`--patch` 在两份内容不一致时会提醒你别忘导回。

> 但同一份文件也是 `--update-dict` 的落点：远程词典会**整份覆盖**它，不合并。
> 手改了一堆译法又没留底，跑一次词典更新就全没了。工具会在下载前打印覆盖提示，
> 看到提示先选 N。之后的保底分两种模式：源码模式下 `--import-dict` 把改动固化进
> `dict/`，覆盖的就只是工作副本；EXE 模式下没有这条退路（内置词典在临时解压目录里，
> 写回去随进程退出就没），只能自己复制一份备份。

### 键的写法：逐字节等于界面文本

DOM 兜底通道做的是**整串精确匹配**，所以：

- **大小写、单复数、空格都算**：框架里是 `Collapse All`、界面上是 `Collapse all`，
  差一个字母就不生效 —— 而且**不报错，只是不翻**。
- **NBSP 要原样保留**：源码里的 `"\xA0 Pin function \xA0"` 两端是不换行空格（NBSP），
  界面上显示的文本就含 NBSP。词典的键**不做任何归一化**（`langpack.build()` 明确
  不 strip），所以这四条必须带真实 NBSP 写。用普通空格代替就命中不了。
- **带插值的句子翻不了整串**：如 `Search for any ${x}...`、`Wake-up pin 4`，
  那要在 `assets/dom-translate.js` 的 `RULES` 里加一条按形状匹配的规则。
- **一句话被 React 拆成多个文本节点**的（快捷键弹窗那种），改同文件的 `SCOPE_MAP`
  按容器限定翻译，并且**按「动词续写」写**，拼出来要能读成一句完整的话。

### 翻译规范

1. **术语必须先查 `rules/glossary.zh.json`。** 凡涉及 STM32 专有名词、字段名、
   枚举值，一律以 ST 官方中文资料（参考手册 RM > 数据手册 DS > 用户手册 UM）
   的用词为准，**不要凭语感翻**。比如 GPIO 速度档位官方是「低速 / 中速 / 高速 /
   超高速」，不是口语的「低 / 中 / 高 / 非常高」。
   `tools/check_glossary.py` 会强制校验，`--patch` 时违规直接中止。
2. **专有名词不译**：GPIO、DMA、NVIC、EXTI、SPI、CMSIS、Pack、MCU 等列在
   `keep_english` 里的，**不要写进词典**（写了门禁会报错 —— 进了词典就意味着会被翻成中文）。
3. **多义词写进 `scope`**：同一英文在不同字段下译法不同的（`Low`/`High` 在速度档位
   是「低速/高速」，在电平字段是「低/高」），由 `assets/dom-translate.js` 按上下文判定。
4. **同族译法不许分叉**：`terms` 只比对精确键，钉不住散文里的同一个动词，
   所以词族由 `family` 守着 —— 例如英文含 `activate` / `active` 的条目一律不许写「激活」
   （统一「启用 / 停用」，依据见 `rules/glossary.zh.json` 的 `_comment_activate`）。
   发现别的词也在分叉（一个词三种译法），就来加一条 `family` 规则。
5. **占位符保留**：原文含 `{0}` 的，中文里保留同样数量与顺序（由框架 `format` 处理）。
6. **枚举组整组补齐**：补下拉框选项时别只补截图里高亮那一条，同组的
   `Medium` / `Very high` 一起补，否则界面上会出现中英混排。
   `tools/dom_harness.js` 的 `GPIO_ENUM_GROUPS` 是给这类枚举上的硬门禁。
7. **不确定的别加**：宁缺毋滥。没收录的英文会原样显示，不会出错；翻错了才会。

> **以前那条「en/zh 引号数量必须一致」的规则已经作废。** 那是字节替换策略的防护
> （替换进去的内容会破坏 JS 结构）。现在中文是以**数据**形式注入查表的，
> 改不动代码结构，落盘前还有一道 `node --check` 语法门禁兜底。

---

## 5. 验证

```powershell
python tools/check_dict.py            # 词典结构（CI 也跑这个）
python tools/check_glossary.py        # 术语门禁
python main.py --patch -g <安装目录>   # 汉化（内含语法门禁）
python tools/verify_i18n.py -g <安装目录>   # i18n 通道语义
python tools/verify_dom.py  -g <安装目录>   # DOM 通道真实 DOM，249 条断言
python tools/e2e_i18n.py    -g <安装目录>   # 端到端：跑框架自己的真实代码
```

最后启动 CubeMX2 用眼睛看 —— 工具能证明「注入的内容正确」，
但只有真实界面能证明「翻对了地方」。

---

## 6. 提交

1. 提交 `dict/localization.json`（以及改过的 `rules/glossary.zh.json` / `dom-translate.js`）。
2. **bump 词典 `version` 字段**（如 `0.2.0` → `0.2.1`），否则用户点「词典更新」
   检测不到新版本。
3. 发 PR。CI 会跑 `tools/check_dict.py` 与 `tools/check_glossary.py`。
4. 合并后用户即可通过「词典更新」拉到新翻译。

---

## 7. 常见问题

**Q: 加了词条，汉化也成功了，界面还是英文？**
按这个顺序排查：

1. **键与界面文字不逐字节一致** —— 最常见。大小写、单复数、多余空格、
   该带 NBSP 的没带。见第 4 节。
2. **该文案是运行时数据** —— 来自设备/配置描述符，`--coverage` 里落在
   「两个 bundle 里都没有」那一档。这种要靠 `__cubemx2zhMiss()` 在界面上收原文，
   拿到什么键就写什么键。
3. **是拼接出来的句子** —— `"Pins: " + n` 这类整串不相等，DOM 通道刻意不碰。
   需要在 `dom-translate.js` 的 `RULES` 加规则。
4. **你之前在界面里选过别的显示语言** —— 注入尊重用户选择，`locale` 已有值时不强改。
   把显示语言切回简体中文即可。
5. **落在跳过区** —— 编辑器、终端、构建输出、`[contenteditable]` 内的文字不翻。

**Q: 汉化后界面变乱/功能异常？**
执行 `python main.py --rollback -g <安装目录>`。新机制下这很少发生 —— 中文是以数据
形式注入查表的，改不动代码结构，落盘前还有 `node --check` 语法门禁。真出问题多半是
术语译错（跑 `tools/check_glossary.py` 核对），而不是格式被破坏。

**Q: 想改一条已有的译法，但词典里那条是自动生成的怎么办？**
直接改 `entries` 里对应的值即可。现在没有「自动生成会覆盖你的手改」这回事 ——
词典本身就是最终产物，改哪条就是哪条。
