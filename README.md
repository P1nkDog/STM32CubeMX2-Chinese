# STM32CubeMX2 中文汉化工具

给 **STM32CubeMX2**（Electron/Theia）加中文界面的非官方社区工具。

- 一键汉化 / 一键回滚，改动前自动备份，回滚做到字节级还原
- 两条通道并用：框架 i18n 注入（主力）+ DOM 整串精确匹配兜底
- 词典在线更新、环境检查、锚点自检，术语对齐 ST 官方中文文档
- 只要 Python 3.11+，零第三方依赖

机制调查、注入点清单、翻译规范与踩坑记录在 [docs/I18N-STRATEGY.md](docs/I18N-STRATEGY.md)，
日常翻译怎么上手看 [docs/TRANSLATION.md](docs/TRANSLATION.md)。

> 本项目与 STMicroelectronics 无隶属或背书关系，不包含 STM32CubeMX 本体。
> 使用本工具修改第三方软件可能违反其许可协议，风险自负，建议仅用于个人学习与本地界面理解。

[![Release](https://img.shields.io/github/v/release/P1nkDog/STM32CubeMX2-Chinese)](https://github.com/P1nkDog/STM32CubeMX2-Chinese/releases)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-blue)](https://www.microsoft.com/windows)

## 效果预览

汉化后的引脚配置（Pinout）界面 —— 右侧详情视图、GPIO 模式下拉与右键菜单都已翻：

![汉化后](docs/images/after.png)

已验证：STM32CubeMX2 1.1.1 ／ 工具与词典 v0.2.0 ／ Windows。

## 快速开始

### 方式一：下载 EXE（推荐）

1. 前往 [Releases 发布页](https://github.com/P1nkDog/STM32CubeMX2-Chinese/releases) 下载最新版 EXE。
2. **完全退出 STM32CubeMX2**（含系统托盘图标）。
3. 双击运行，主菜单选 `2) 一键汉化`。
4. 启动 STM32CubeMX2 看效果；想还原就再跑一次，选 `3) 一键回滚`。

### 方式二：源码运行

```powershell
python main.py
```

只需要 Python 3.11+。`node` 不是运行依赖 —— 它只用于落盘前跑一次 `node --check`
语法校验，没装就跳过并打一行提示，汉化照常完成。

## 使用说明

### 交互菜单

| 选项 | 功能 |
|------|------|
| 1) 环境/安装检查 | 检测安装目录、进程、词典、语法门禁可用性、汉化状态 |
| 2) 一键汉化 | 备份原文件后注入中文语言包 |
| 3) 一键回滚 | 从 `.orig` 备份恢复原版文件（含 `bundle.js.gz`） |
| 4) 词典更新 | 从 GitHub 拉取最新词典 |
| 5) 软件更新 | 打开 GitHub Releases 发布页 |
| 6) 高级 | 导出词典 / 导入修改后的词典 |

> **改完词典不用「导入」。** 你编辑的那份工作副本本来就被优先读取，改完直接选
> `2) 一键汉化` 就生效。「导入」只服务于「把改动固化进仓库、好提交 PR」这一种场景。

### 命令行参数

| 参数 | 说明 |
|------|------|
| `-g, --path <目录>` | 指定安装目录（指到 `dist`/`app` 那一层也行，会自己往上找到根） |
| `--patch` / `--rollback` | 汉化 / 回滚（免菜单） |
| `--doctor` | 环境/安装检查 |
| `--probe` | 注入点锚点自检（应用开着也能跑） |
| `--coverage` | 覆盖率评估并列出未覆盖文案 |
| `-v, --verbose` | 打出细节：锚点命中明细、术语门禁的通过项、源串长度统计 |
| `--export-dict` / `--import-dict` | 导出词典到工作副本 / 把工作副本导回仓库 `dict/` |
| `--update-dict` / `--check-update` | 拉取并应用最新词典 / 只检查 |
| `--open-github` / `--version` | 打开发布页 / 显示版本号 |

`--probe` 与 `--coverage` 是维护者动作，不进菜单 —— 用户不需要为了「界面还有英文」
去跑统计，直接用界面里的收集器更准（见常见问题「零散漏网太多」那条）。

### 安装目录是怎么找到的

按这个顺序，第一个验真成功的就用：

| 顺序 | 来源 | 说明 |
|------|------|------|
| 1 | `-g <目录>` | 指到 `dist`、`app`、甚至 `bundle.js` 都行，会自己往上找到根 |
| 2 | 上次确认的 | `~/.stm32cubemx2-chinese/config.json`，只在**你亲手给过**之后才有 |
| 3 | 自动扫描 | 环境变量 `STM32CUBEMX2_PATH` → 系统卸载表 → 常见安装位置 |
| 4 | 问你要 | 以上全空时，控制台会让你输入安装目录 |

三条约束：判据只有一个文件（`…/dist/resources/app/lib/frontend/bundle.js`，中间那段
版本号用通配，所以应用升级不会让整套定位失效）；自动扫描绝不翻盘乱搜，往子目录里搜
**只在你手动给出路径之后**才开，而且结果必须你回 `y` 才采用 —— 认错目录的后果是往别的
程序里写文件；记忆只存你确认过的，每次读回都重新验真，目录被挪走就静默回退到扫描。

扫不到时分三种情况告诉你，而不是一句「未找到」：注册表里**有** CubeMX2 但给出的目录
不可用（会把它读到的 `InstallLocation` 原样列出来，方便远程排障）、只找到**老版**
STM32CubeMX（Java 版，本工具不支持）、以及**根本没有**安装痕迹。

## 汉化策略

界面文案其实分两套，所以有**两条通道**：

| 通道 | 覆盖对象 | 做法 |
|------|------|------|
| **i18n 通道**（主力） | 框架文案（菜单、命令面板、设置项…）走 `nls.localizeByDefault` 的那部分 | 把 `{英文原文: 中文}` 写进框架的 `localization.replacements` |
| **DOM 通道**（兜底） | ST 自己写的界面文案（Pinout 主界面、状态栏…）—— 它们**是裸字符串，一次 i18n 都没调用** | 在 bundle 末尾追加一个翻译器，渲染后按**整串精确匹配**替换文本与 `placeholder`/`title` 等属性 |

> 只走 i18n 通道的话，能在前端 bundle 里落地的条目只剩一半上下 —— 剩下那些裸字符串
> 它天生够不到，这就是「菜单变中文了但主界面还是英文」的原因。

- **注入 10 个 bundle**：每一份自带 nls 模块的 bundle 都是一条独立通道，包括懒加载
  chunk 和后端的 Electron 主进程入口。`--probe` 会把每个文件的锚点命中数列出来。
- **DOM 通道的安全边界**：只做整串精确匹配、不碰输入框的 `value`、跳过编辑器/终端/
  构建输出/可编辑区，`data-cubemx2zh-skip` 可让任意元素退出翻译。宁可少翻，不可翻错。
- **没收录的英文原样显示**，不会误改。

逐条注入点、覆盖率实测、运行时数据从哪来，见
[docs/I18N-STRATEGY.md](docs/I18N-STRATEGY.md) 第 0、3、5、9 节 —— 这里不写死条数，
跑 `--coverage` 才是当前真相。

## 更新

- **词典更新**（菜单 4 / `--update-dict`）：从 GitHub 拉取最新 `localization.json`，
  写入工具旁（或 `%LOCALAPPDATA%`）。更新后直接执行「一键汉化」即可生效。

  > 这份远程词典会**整份覆盖**你手改的那份工作副本（它就是被优先读取的那份），
  > 不是合并。改过词典又想留着自己的译法，就先复制一份备份，或在提示出现时选 N。
  > 工具会在下载前打印覆盖提示和具体路径，但不会替你备份。
- **软件更新**（菜单 5 / `--open-github`）：打开 GitHub Releases 发布页，自行下载新版 EXE。

> 远程地址由 `core/dictionary.py` 中的 `GITHUB_REPO` 决定（当前：`P1nkDog/STM32CubeMX2-Chinese`）。

## 安全机制

- **自动备份**：改动前把原文件备份为 `*.orig`（仅首次，不覆盖；`bundle.js.gz` 同样备份）。
- **锚点唯一性**：每条注入的正则必须恰好命中 1 次，否则拒绝注入、零写入。
- **幂等重建**：重复汉化 = 从 `.orig` 基线重新注入，翻译更新后重跑即可。
- **语法门禁**：先写临时文件 → `node --check` → 通过才落盘；失败则原文件不受影响。
- **术语门禁**：落盘前核对译法与 `rules/glossary.zh.json`（对齐 ST 官方中文用词），
  不一致直接中止。全过时一行都不打 —— 门禁是保险不是日报，想确认它跑过就加 `-v`。
- **逐文件隔离**：一个文件失败只回滚该文件，不牵连其它。
- **定位门禁**：往子目录里搜出来的安装目录必须用户确认才采用；记住的目录每次读回都
  重新验真，对不上就回退到扫描。
- **进程检测**：汉化/回滚前确认 CubeMX2 没在运行。
- **回滚可验证**：实测 10 个 bundle + 2 个 `.gz` 回滚后 sha1 与 `.orig` 完全一致。

## 参与翻译

**只是想把某个词改得顺一点？** 运行程序 → `6) 高级` → `1) 导出词典`，
它会告诉你文件路径；用记事本打开，在 `entries` 里改对应的中文（或加一行），保存，
回主菜单选 `2) 一键汉化` 即可 —— 不需要导回，也不需要装 Python 之外的任何东西。

词典最开始由 AI 翻译，需要社区协作打磨。完整流程与规矩看
[docs/TRANSLATION.md](docs/TRANSLATION.md)；要拿 AI 批量补译，先把
[docs/TRANSLATION-AGENT.md](docs/TRANSLATION-AGENT.md) 喂给它 —— 用词统一表和禁改清单在那份里。

漏在哪一类、逐类怎么补，见 [docs/I18N-STRATEGY.md](docs/I18N-STRATEGY.md) 第 10 节
（五类漏网文案的定性办法：先在语言包里查，再去 `.orig` 里搜，最后去 `bundle.js.map` 里搜）。
**只漏了一两条**时不用走整套流程，直接改 `dict/localization.json` 的 `entries`：
键写界面上看到的英文原文、值写中文，然后 `python main.py --patch`。

> **术语必须先查 `rules/glossary.zh.json`。** 涉及 STM32 专有名词、字段名、枚举值，
> 一律以 ST 官方中文资料（RM > DS > UM）的用词为准，不要凭语感 —— 比如 GPIO 速度档位
> 官方是「低速 / 中速 / 高速 / 超高速」，不是口语的「低 / 中 / 高 / 非常高」。
> `--patch` 会强制拦下不一致的译法。**多义词**（`Low`/`High` 在速度档位与电平字段下
> 译法不同）写在术语表的 `scope` 里，由 DOM 通道按上下文判定。

> **键要和界面逐字节一致。** DOM 通道只做整串精确匹配，大小写、单复数都算
> （框架里是 `Collapse All`，界面上是 `Collapse all`），差一个字符就**不报错、只是不翻**。
> 源码里 `"\xA0 Pin function \xA0"` 两端是**不换行空格**，词典的键**必须带真实 NBSP
> 原样写** —— 键不做任何归一化，用普通空格代替就静默命中不了。

## 项目结构

```
main.py                 命令行入口与交互菜单
core/                   locate 定位 · i18n 注入引擎 · langpack 词典→语言包
                        session 汉化/回滚编排 · glossary 术语门禁 · dictionary 词典解析
                        backup 备份回滚 · process 进程检测 · gzip_sync .gz 同步
                        update 远程更新 · paths 路径约定
dict/localization.json  唯一词典：扁平的 {英文原文: 中文}，一条一行、键排序
assets/dom-translate.js DOM 通道的兜底翻译器（含未收录文案收集器）
rules/glossary.zh.json  术语规范（唯一依据，被术语门禁读取 —— 是代码输入不是文档）
tools/                  自检与提取脚本（见下节）
docs/                   机制文档 · 翻译指南 · 截图
icon/                   程序图标
```

常用的跑法见下面「自检流程」那条命令清单；逐模块的设计说明在
[docs/I18N-STRATEGY.md](docs/I18N-STRATEGY.md)。

## 开发者指南

### 打包 EXE

```powershell
python -m PyInstaller --onefile --name STM32CubeMX2-Chinese `
  --add-data "dict/localization.json;dict" `
  --add-data "rules/glossary.zh.json;rules" `
  --add-data "assets/dom-translate.js;assets" `
  --icon "icon/icon.ico" main.py
```

产物 `dist\STM32CubeMX2-Chinese.exe`；本地 `STM32CubeMX2-Chinese.spec` 可直接复用
（`*.spec` 按约定不入库）。两条纪律：

- **打包前同步词典**：源码运行优先读仓库根的 `localization.json`（工作副本），打包后读
  的是 `dict/` 那份，两者不同步就会发出旧词典 —— 用 `--import-dict` 固化。
- **三个 `--add-data` 都是运行时依赖**，漏一项就有一档机制在用户机器上静默降级：漏
  `assets/dom-translate.js` → DOM 通道拒绝注入；漏 `rules/glossary.zh.json` → 术语门禁
  无从核对、`--patch` 直接放行。改完 `datas` 要重打包并跑一次 `--patch` 确认。

### 自检流程

```powershell
python tools/test_locate.py       # 安装目录定位（临时目录搭假布局，68 条断言，不碰真实安装）
python tools/test_update.py       # 词典更新链路与入口（离线打桩，45 条断言）
python tools/test_glossary.py     # 术语门禁自证（32 条：改错译法/词族回退/传错形状会怎样）
python tools/check_dict.py        # 词典结构
python tools/selftest_i18n.py     # 离线语法自检（改生成器后先跑）
python main.py --probe            # 锚点自检（10 个文件）
python main.py --coverage         # 覆盖率 + 未覆盖清单
python main.py --patch            # 汉化（内含两道门禁）
python tools/verify_i18n.py       # 落盘后 i18n 通道语义自检
python tools/verify_dom.py        # 落盘后 DOM 通道真实 DOM 自检（249 条断言，需 npm i）
python tools/e2e_i18n.py          # 端到端：跑框架自己的真实代码
python main.py --rollback         # 回滚（字节级还原）
```

前四条不装 CubeMX2 也能跑（临时目录里搭假布局），打包或提交词典前先跑一遍；
其余需要真实安装目录。本仓库单人维护，没挂 CI —— 这几条脚本就是替代它的东西。
`-g` 全部可以省略 —— 不给就走自动定位，并且会把**实际用的目录和它的来源**打印出来：
验证跑在另一台安装上是最坏的一种绿。脚本里不启用向下搜、找到多个目录也不猜，直接报错。

`tools/extract_st_params.py` 是另一类工具：从 ST 配置描述符（`*_parameters.json`）里
穷尽面板文案。MPU/PWR/GPIO 各面板的标签、选项、提示都是**数据**，静态扫 `bundle.js`
永远扫不到，换芯片系列时要重跑一次（`--missing` 只列尚未收录的）。

## 常见问题

**Q: 提示「未找到 STM32CubeMX2 安装目录」，或者让我输入安装目录？**
A: 这句话分三种，先看清是哪一种：
   - **只找到老版 STM32CubeMX** → 本工具只汉化 Theia 版的 STM32CubeMX2（1.1.x）；
     老版（5.x/6.x，Java 程序）和 STM32CubeIDE 结构完全不同，汉化不了。
   - **注册表里有 CubeMX2，但它给的目录里没有可注入的文件** → 多半装在另一个
     Windows 账户下，或者装完被手动挪过位置。
   - **没有任何安装痕迹** → 先确认是不是真的装了。

   最快的自查办法：右键桌面或开始菜单里的 STM32CubeMX2 快捷方式 →
   「打开文件所在的位置」，地址栏里那个目录就是安装根，把它粘进输入框即可。
   （从**任务管理器**的「打开文件所在的位置」进来会停在 `...\1.1.1\dist`
   那一层 —— 那个也可以，工具会自己往上找到根。）
   也可以直接 `-g "D:\你的路径"`，或设环境变量 `STM32CUBEMX2_PATH`。

   输入过一次之后会记在 `~/.stm32cubemx2-chinese/config.json`；
   想改或者想让它重新扫描，删掉那个文件就行。

**Q: 汉化后部分界面还是英文？**
A: 先看是哪种：
   - **整个主界面（Pinout 等）还是英文** → 那是裸字符串，检查 DOM 通道是否生效：
     F12 里看 `window.__CUBEMX2ZH_DOM__`，`size` 应是个非零数字；没有这个对象说明
     nls 模块没加载到（看 Console 里的 `[STM32CubeMX2-Chinese]` 提示）。
   - **零散设置项说明** → 正常，那是还没翻译。用 `--coverage` 看清单、
     `tools/dump_missing.py` 导出后参与翻译即可逐步补齐；
     单条漏网的也可以直接加进 `dict/localization.json` 的 `entries`。

**Q: 零散漏网太多，想一次性收集，不想一张张截图？**
A: **正常用一遍软件就行** —— 翻译器会自己攒。

   DOM 通道的 DOM 兜底翻译器带了一个**未收录文案收集器**：任何查表失败的英文
   都会被记在本地（`localStorage`，绝不联网，不上传）。把应用的各个页面点一遍
   （Pinout / 引脚配置 / 时钟树 / PWR / 各设置页），然后在 F12 Console 里执行：

```js
__cubemx2zhMiss("text")     // 累计收集到的全部未收录文案，一行一条
__cubemx2zhMiss()           // 直接打印，并返回数组
__cubemx2zhMissClear()      // 清空，重新开始收集
```

   拿到的清单直接当 `dict/localization.json` 里 `entries` 的**键**用即可。

   > 它只「记录」，不做任何猜测：引脚名（`PA5`）、寄存器位名（`CSLEEP`）这类
   > 本来就要保留英文的也会被一并记下，人工筛的时候忽略即可 ——
   > **宁可多记也不要漏**。收集是**跨会话累积**的（存在 localStorage 里），
   > 不是只采当前这一屏。

   只想采**当前这一屏**、不等累积的话，用 `tools/collect-untranslated.js` —— 粘进
   F12 Console 的一次性扫描脚本，带注释。

   收集到的英文原文直接贴回来即可 —— 它们绝大多数是**运行时数据**，源码树里都搜不到，
   按采集结果补进 `dict/localization.json` 的 `entries` 是最快的路径。
   过滤口径为什么放宽到现在这样，见
   [docs/I18N-STRATEGY.md](docs/I18N-STRATEGY.md) 第 10.6 节。

**Q: 明明汉化了，界面还是全英文？**
A: 十有八九是**你之前在界面里选过别的显示语言**。i18n 通道尊重用户选择
   （`locale` 已有值时不会强改），这是刻意设计。把显示语言切回「简体中文」
   即可，或删掉 `localeId` 这条本地存储。

**Q: 提示"锚点命中 0 次/多次"？**
A: 说明 CubeMX2 版本变了。对照 `docs/I18N-STRATEGY.md` 第 8 节调整
   `core/i18n.py` 里的锚点正则。此时工具**不会**写任何文件。新增版本如果多出
   自带 nls 的 bundle，也要按文档 3.5 节的做法加进 `TARGETS`。

**Q: 要不要装 Node.js / jsdom？**
A: **普通用户两个都不装。** 界面里的 DOM 翻译是 CubeMX2 **自带 Chromium** 在执行的，
   跟本机有没有 Node 无关。Node 只用于可选的落盘前语法校验，缺了就跳过并打一行普通
   提示（不影响结果和退出码）；想确认这道保险开没开就跑 `--doctor`，看「— 落盘前语法
   门禁 —」那节；要用非标准位置的 node，设环境变量 `CUBEMX2ZH_NODE` 指向 `node.exe`。
   jsdom 只服务 `tools/verify_dom.py` 那一个自检脚本，改 DOM 通道或大批提交词条的人才
   需要 —— 仓库根一条 `npm i` 装好，`node_modules/` 不入库，CI 也不跑它。

**Q: 提示"STM32CubeMX2 正在运行"？**
A: 先完全退出 CubeMX2（含系统托盘），再执行汉化。

**Q: 杀毒软件报毒？**
A: PyInstaller 打包的单文件 EXE 偶发误报，可将程序加入杀毒软件白名单后使用。

**Q: 汉化后想恢复原版？**
A: 运行程序选择 `3) 一键回滚`，或手动把 `*.orig` 覆盖回同名文件。
