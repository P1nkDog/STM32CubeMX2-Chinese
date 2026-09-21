# 词典翻译任务交接说明（给翻译 Agent）

> 本文给**受托执行翻译的 Agent**看。目标文件是 `dict/localization.json`。
> 人类贡献者请读 [TRANSLATION.md](TRANSLATION.md)，规则一致，只是语气不同。
> 审查人：主 Agent（提交前由主 Agent / 用户审查）。

---

## 1. 背景（一句话）

`dict/localization.json` 是一张扁平表 `{"界面英文原文": "中文"}`。
汉化时 `--patch` 直接读它、现场构建注入内容，走框架 i18n 通道 + DOM 兜底两条路。
**没有 CSV，没有单独的构建步骤。**

---

## 2. 文件与结构

```text
D:\project\python\STM32CubeMX2-Chinese\dict\localization.json
```

```json
{
  "version": "0.2.0",
  "targetApp": { "name": "STM32CubeMX2", "testedVersions": ["1.1.1"] },
  "entries": {
    "Cancel": "取消",
    "Open Project": "打开工程"
  }
}
```

| 位置 | 含义 | 你要做什么 |
|------|------|------------|
| `version` | 词典版本 | **不要改**（主 Agent 提交前统一 bump） |
| `targetApp` | 目标软件与已验证版本 | **不要改** |
| `entries` 的**键** | 界面上显示的英文原文 | **不要改写法**，见 3.1 |
| `entries` 的**值** | 中文译文 | **你只填/改这一侧** |

一条一行，键按字典序排列（改完请保持排序，方便 diff）。

### 填写示例

| 键（英文原文） | 值（中文） |
|---|---|
| `Deactivate GPIO` | `停用 GPIO`（不是「停用通用输入输出」） |
| `Pack manager` | `Pack 管理器` |
| `Search by part no` | `按部件号搜索`（part → 部件号，可以译） |

---

## 3. 必须遵守的规则

### 3.1 键是从界面抄下来的，不是你归纳的

**键必须与界面文字逐字节一致**：大小写、单复数、空格、NBSP（不换行空格）都算。
DOM 兜底通道做整串精确匹配，差一个字符就**不生效、而且不报错**。

工具**不会帮你归一化键**（`langpack.build()` 明确不 strip），所以也不要顺手整理。

### 3.2 译什么

菜单、按钮、对话框标题、面板名、提示语、校验错误信息、tooltip。

### 3.3 术语表（保持英文，**不要写进词典**）

```text
GPIO  DMA  NVIC  EXTI  SPI  I2C  I2S  UART  USART  CAN  USB
CMSIS  Pack  Packs  MCU  IDE  IOC  SWD  JTAG  RTOS  HAL  LL
STM32  STM32CubeMX2  CubeMX  FreeRTOS  FileX  USBX
```

这些词列在 `rules/glossary.zh.json` 的 `keep_english` 里。
**写进词典就等于让界面把它们翻成中文**，术语门禁会直接报错。

### 3.4 用词统一

| 英文 | 中文 | 说明 |
|------|------|------|
| Project | **工程** | 不要写「项目」 |
| Configuration | 配置 | |
| Peripheral | 外设 | |
| Middleware | 中间件 | |
| Utility | 实用工具 | |
| Pinout | 引脚配置 | |
| Clock | 时钟 | |
| Board | 开发板 | |
| Generate | 生成 | |
| Settings | 设置 | |
| Preferences | 首选项 | |
| Activate / Activated | **启用 / 已启用** | 不要写「激活」；也不要写成「使能」—— 使能是 enable |
| Deactivate / Deactivated | **停用 / 已停用** | 同上，不写「取消激活」「去使能」 |
| Active（形容词） | 活动 / 已启用 | `active editor` = 活动编辑器，不写「激活的编辑器」 |

> **这张表里只有一部分进了 `rules/glossary.zh.json`，也就是只有那部分被机器强制检查。**
> 其余条目目前只是文档约定。若发现某条被反复翻错，正确做法是**把它补进 glossary 的
> `terms`**、让 `tools/check_glossary.py` 去拦，而不是继续往这张表里加字。

### 3.5 风格

- 菜单/按钮：短，动宾或名词（`保存工程`、`新建文件`）
- 对话框标题：短（`重置配置`）
- 提示/错误：完整句子（`此引脚的当前 GPIO 配置将会丢失。`）
- 保留原有标点风格（原文有 `...` 就保留 `...`）
- 不要加解释、不要加括号注释
- 原文含 `{0}` 等占位符的，中文里保留同样数量与顺序（由框架 `format` 处理）

### 3.6 不确定的就不要加

宁缺毋滥。没收录的英文会**原样显示**，不会出错；翻错了才会。

---

## 4. 工作步骤

1. 拿到待翻清单（通常是 `tools/dump_missing.py` 导出的，或界面上
   `__cubemx2zhMiss()` 收集的）
2. 逐条确认它是**界面文案**，且键与界面**逐字节一致**
3. 涉及 STM32 术语的先查 `rules/glossary.zh.json`；表里没有的，按 ST 官方中文资料
   （参考手册 RM > 数据手册 DS > 用户手册 UM）的用词补进 `terms`，再写词条
4. 加进 `dict/localization.json` 的 `entries`，保持键排序
5. 自查：`python tools/check_dict.py` 与 `python tools/check_glossary.py`
6. 告诉主 Agent：「翻译完成，共 N 条」

---

## 5. 完成标准

- [ ] 键与界面文字逐字节一致（含大小写、NBSP）
- [ ] 术语符合 3.3 / 3.4
- [ ] 「工程」不是「项目」
- [ ] GPIO / Pack / MCU 等未被翻译，也没被写进词典
- [ ] `python tools/check_dict.py` 通过
- [ ] `python tools/check_glossary.py` 通过

---

## 6. 不要做的事

- 不要改 Python 代码，不要改 `assets/dom-translate.js`
- **不要执行汉化 / 回滚**（`--patch` / `--rollback`）
- 不要自己 bump 词典 `version`（由主 Agent 提交前统一改）
- 不要把键「顺手整理」成更规范的样子 —— 见 3.1
- 不要翻译 `pi pi-*`、`rgba(...)`、哈希串这类非文案字符串

---

## 7. 审查方式（主 Agent 会做）

1. `tools/check_dict.py` 结构校验
2. `tools/check_glossary.py` 术语一致性
3. 抽样对照键与界面截图，确认逐字节一致
4. `--patch` 后跑四层验证（`verify_i18n` / `verify_dom` / `e2e_i18n`）
5. 启动 CubeMX2 用眼睛确认

不通过会退回并说明原因。

---

## 8. 交付

翻译完成后回复：

```text
已完成词典翻译
文件：dict/localization.json
新增/修改：约 XXXX 条
存疑未译：XX 条（列出键名与原因）
```

**不要自行执行汉化或回滚。**
