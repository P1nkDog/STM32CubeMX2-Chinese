# 汉化策略：i18n 注入 + DOM 兜底

> 本文记录 CubeMX2 汉化从「字节级字面量替换」转为「i18n 注入 + DOM 兜底」的
> 机制调查结论、注入点清单、以及踩过的坑。所有结论均在 **STM32CubeMX2 1.1.1**
> （Theia + Electron，`resources/stm32cubemx-application/1.1.1/dist/resources/app`）
> 上实测确认。
>
> 一句话结论：**界面文案分两套 —— 框架文案走 i18n（i18n 通道），
> ST 自己写的界面文案是裸字符串、必须靠 DOM 兜底（DOM 通道）。
> 只走 i18n 通道的话覆盖率天生只有一半。**

## 0. 两套文案，两条通道（最重要的一张表）

把词典 6919 条的「落地形态」按通道分类（`main.py --coverage` 现场统计）：

| 落地形态 | 条数 | 走哪条通道 |
| --- | --- | --- |
| 出现在 `localizeByDefault(...)` / `nls.localize("key","…")` 里 | 1186 | **i18n 通道**：框架原生 |
| **只以裸字符串出现**（ST 自绘界面） | **1629** | **DOM 通道**：渲染后整串匹配 |
| 10 个 bundle 里都搜不到 | 4104 | **两条都不走**：多为后端设置项描述与运行时数据 |

裸字符串长这样（`lib/frontend/bundle.js` 里 Pinout 主界面）：

```js
createElement(Button, {...,"data-testid":"pinout-toolbar-reset-pins"}, "Reset pins")
leftLabel:"Graphic view", rightLabel:"Table view"
title:"Pinout legend"   /   x="Not configurable pin"
{icon:"pass", text:"Saved", tooltip:"All changes saved"}      // 状态栏脏状态指示器
```

这些字符串**一次 i18n 都没调用**，所以 i18n 通道无论如何都够不到 ——
不是它没生效，而是它们压根不在 i18n 通道上。

## 1. 为什么换策略

旧策略把界面文案当成「bundle 里的字节」来替换：正则扫出 `:"All"`、`,"Cancel")`
这类片段，逐条做字节替换。它的天花板很清楚：

| 问题 | 说明 |
| --- | --- |
| 覆盖率有上限 | 正则「想到什么扫什么」，扫不到的永远漏 |
| 文件覆盖面窄 | 只 patch 两个文件；`lib/backend/main.js` 里 626 处 i18n 调用一处没动 |
| 噪声吃人力 | `text` + `quote_frag` 片段占翻译表 60%，大量是随机 ID、webpack 内部符号 |
| 顺序敏感 | 串行就地替换，每条在上一条改完的缓冲区上再匹配 |
| 升级即报废 | 索引的是字节位置，应用一升级全部推倒重来 |

而 CubeMX2 的界面文案**本来就全部走框架自带的 i18n API**。绕开它去改字节，
等于放弃了框架已经提供的扩展点。

## 2. 机制：框架原生支持「按英文原文查表」

`lib/frontend/bundle.js` 与 `lib/backend/main.js` 中的模块 `249401`
（`Localization`）与 `152985`/`7862`（`nls`）：

```js
// Localization.localize(localization, key, value, ...args)
function localize(localization, key, value, ...args) {
  let t = value;
  if (localization) {
    const r = localization.replacements?.[value];   // ★ 优先：按英文原文直接命中
    if (typeof r === 'string') t = r;
    else {
      const l = localization.translations[key];     // 否则按 key 查
      if (l) t = normalize(l);
    }
  }
  return format(t, args);                            // {0} 占位符由框架处理
}

// nls.localizeByDefault(英文原文)
function localizeByDefault(value, ...args) {
  if (nls.localization) {
    const key = getDefaultKey(value);                // 用编译进去的 nls 元数据反查 key
    if (key) return nls.localize(key, value, ...args);
    console.warn(`Could not find translation key for default value: "${value}"`);
  }
  return Localization.format(value, args);           // ← 反查不到 key 就直接返英文
}
```

三条关键结论：

1. `localization.replacements` **以英文原文为键**，这正是我们词典的天然形态。
2. 覆盖范围是**所有走 i18n API 的调用点**，不管在哪个文件、哪个 chunk。
3. `localizeByDefault` 在反查不到 key 时会**直接返回英文，根本不进查表**——
   这是必须改的一处。

实测三个 bundle 里按 i18n 调用点统计的英文原文共 **4924 条**（去重后）。

## 3. 四处注入点

注入全部用**正则锚点**定位（不写死偏移），每条编辑要求**唯一命中**，
命中数不等于 1 直接拒绝注入。

### 3.1 `fallback` —— 让查表不再被短路

`bundle.js` / `secondary-window.js` / `main.js` 各一处。

```js
// 改前
return n.Localization.format(d, u)}r.localizeByDefault = i;

// 改后（key 传空串，等价于「只按英文原文查 replacements」）
return c("", d, ...u)}r.localizeByDefault = i;
```

其中 `c` 是该模块里 `localize(key, value, ...args)` 的包装函数名，
由锚点 `A_LOCFN` 现场提取（不同 bundle 里分别是 `c` / `d` / `o`）。

### 3.2 `tail` —— 装载语言包

在 nls 模块 IIFE 结尾追加：

```js
/*__CUBEMX2ZH__*/try{
  if(!NLS.locale) NLS.locale = "zh-cn";
  if(NLS.locale === "zh-cn") {
    NLS.localization = {
      languageId:"zh-cn", languageName:"Chinese (Simplified)",
      localizedLanguageName:"简体中文", languagePack:!0,
      translations:{}, replacements:{ /* 语言包，约 210KB */ }
    };
  } else if(console&&console.warn) console.warn("[STM32CubeMX2-Chinese] locale=" + NLS.locale + "，已跳过中文注入");
}catch(_){}
```

> 踩过的坑（靠 `tools/selftest_i18n.py` 的合成样本 + `node --check` 抓住）：
> `if` 的 then 分支**必须用花括号包起来**。写成
> `if(c) NLS.localization={...}else if(...)` 是**非法语法**——
> `else` 前面既没有 `;` 也没有换行，ASI 不会插入分号，直接
> `SyntaxError: Unexpected token 'else'`。
> 注意这个坑和「括号配平」无关（那是另一个坑），纯粹是 ASI 规则。

- 只有 `nls.locale` 有值，前端 `I18nPreloadContribution.initialize()`
  才会去 `loadLocalization()`；否则整段跳过、永远英文。这里顺手把它打开。
- **尊重用户选择**：`locale` 已被设成别的语言（UI 里选过）时不注入中文。
- 数据是**内嵌**的，不依赖运行时文件读取或 RPC，离线也确定生效。
  翻译更新后重新执行汉化即可（工具会从 `.orig` 基线重建，幂等）。

### 3.3 `packkeep` —— 语言包到达时别把自建表冲掉（仅 `bundle.js`）

前端 `I18nPreloadContribution` 从 `localizationServer` 拿到语言包后，会**整体覆盖**
`nls.localization`。若不处理，我们内嵌的 3000+ 条 `replacements` 会被冲掉，
界面直接退回英文（而且是**静默**退回，最难查）。

```js
// 改前：整个对象被覆盖，replacements 丢失
p.languagePack ? o.nls.localization = p : ...

// 改后：三路合并，我们的中文表优先，且永不产生 undefined
p.languagePack ? (
  p.replacements = Object.assign({}, p.replacements, (o.nls.localization||{}).replacements),
  o.nls.localization = p
) : ...
```

两个踩过的坑：

1. 三元运算符的分支必须整体加括号。`a ? b, c : d` 是**非法语法**
   （分支位置只接受 AssignmentExpression），曾被 `node --check` 抓住。
2. 不要写成 `p.replacements = (o.nls.localization||{}).replacements`。
   当 `nls.localization` 还不存在时，右值是 `undefined`，等于把语言包
   **自带的** `replacements` 也一并抹掉。用 `Object.assign` 三路合并才安全。
   这个坑是 `tools/verify_i18n.py` 新加的 packkeep 运行期用例抓出来的
   （见第 6 节）。

### 3.4 `zhpack` —— 让框架自带的中文包真正加载（仅 `main.js`）

```js
// 改前：createLocalization("zh-cn", ...) 生成的对象没有 languagePack 标记
d.registerLocalizationFromRequire("zh-cn", s(897836))

// 改后
d.registerLocalizationFromRequire(
  {languageId:"zh-cn", languageName:"Chinese (Simplified)",
   localizedLanguageName:"简体中文", languagePack:!0}, s(897836))
```

后端 `LocalizationProvider.getAvailableLanguages()` 会**过滤掉没有
`languagePack` 标记的语言**，所以不改这里，框架自带的 zh-cn 包连加载机会都没有。

### 3.5 目标文件清单（10 个）

**每一处「自带一份 nls 模块」的 bundle 都要注入**，漏一个就少一条通道。
`python main.py --probe` 会把每个文件的锚点命中数列出来。

| 文件 | 角色 | 注入项 |
| --- | --- | --- |
| `lib/frontend/bundle.js` | 前端主 bundle（用户看到的一切） | fallback / tail / packkeep + **dom** |
| `lib/frontend/secondary-window.js` | 第二个窗口（同一套界面） | fallback / tail + **dom** |
| `lib/frontend/778.js` | 懒加载 chunk（**自带一份 nls**） | fallback / tail + **dom** |
| `lib/backend/main.js` | 后端服务进程 | fallback / tail / zhpack |
| `lib/backend/electron-main.js` | **Electron 主进程真正入口** | fallback / tail |
| `lib/backend/plugin-host.js` | 插件宿主进程 | fallback / tail |
| `lib/backend/backend-init-theia.js` | 后端初始化入口 | fallback / tail |
| `lib/backend/ipc-bootstrap.js` | IPC 引导 | fallback / tail |
| `lib/backend/plugin-vscode-init.js` | 插件初始化 | fallback / tail |
| `lib/backend/parcel-watcher.js` | 打包/监听进程 | fallback / tail |

> **踩过的大坑**：一开始只注入了 `bundle.js` / `secondary-window.js` / `main.js`
> 三个文件，结果界面上「菜单是中文、主界面几乎全英文」。
> 两个原因叠加：
> 1. 主界面是裸字符串（下一节）；
> 2. `scripts/theia-electron-main.js` 结尾是
>    `require('../lib/backend/electron-main.js')` —— **它才是 Electron 主进程入口**，
>    `main.js` 只是后端服务进程；另外 `778.js` 这个懒加载 chunk 里
>    **自带一份独立的 nls 模块**，也是一条独立通道。
>
> 教训：判断「哪些文件要注入」不能靠文件名猜，要按
> **`localizeByDefault=` 和 `A_TAIL` 锚点在哪些文件里各命中 1 次** 来枚举。

### 关于框架自带中文包的真实体量（重要更正）

框架内置 zh-cn 包（模块 `897836`）经递归展开后确有 **1293 条**，
但它全部是 **Theia 自身**的显式键文案：

```
ai-chat-ui.show-settings, aiHistory:clear, notebook.cell.changeToCode,
terminal:new:profile, vsx.enabling, theia/ai/agents/title, ...
```

而 `getDefaultKey` 产出的键形如 `vscode/<module>/<localKey>`，
内置包里**一条都没有**；全应用也没有 `vscode-language-pack-*`。
结论：**它不覆盖 VS Code 工作台文案**（设置项、命令面板等）。
开启它仍然是净赚（AI / notebook / terminal 等界面），但不要指望它解决主体。

真正的主力是自建语言包，详见下节。

## 4. 【历史】语言包当初怎么来：把旧词典一条不浪费地转过来

> **本节记录 v0.2.0 迁移时做过的一次性转换，描述的对象现已不存在。**
> 现在词典本身就是一张扁平表，`--patch` 现场构建，既没有 CSV join，
> 也没有 `nls.zh-cn.json` / `supplement.zh.json` 这两个文件。
> 留着是因为它解释了词典里那些数字的来历（当初 6049 片段 → 6885 条；今天这份 6919 条）。

旧词典的 `en`/`zh` 是字节片段，不能直接当表的键。但导出翻译表时生成的
`manual-translate.csv` 里：

- `match` 列 = 原始字节片段（与词典 `en` 完全一致，**6049/6049 全部 join 成功**）
- `en` 列 = 扫描器还原出的**英文原文**
- `kind` 列 = 调用形态（`localizeByDefault` / `label` / `description` / `text` …）

于是 `core/langpack.py` 用 `match` 做 join key，取 `en` 作键、
`inner_string(zh)` 作值，得到扁平表：

```
词典 6049 条  ->  去重  ->  3144 条唯一「英文原文 -> 中文」
```

跳过的是重复条目（2886，同一字面量在不同文件里各存了一份）、
译空/未翻译（5416）、源串不可用（47）。构建报告会逐类打印。

**i18n 通道下词典里多余的条目是无害的**：查表是按英文原文精确匹配，
不在 i18n 调用点上的条目永远不会被用到，不会像字节替换那样误伤。

## 5. 覆盖率

`python main.py --coverage -g <安装根目录>`：

| 文件 | i18n 字面量 | 语言包命中 | 命中率 |
| --- | --- | --- | --- |
| `lib/frontend/bundle.js` | 2370 | 1531 | 65% |
| `lib/frontend/secondary-window.js` | 1900 | 1205 | 63% |
| `lib/frontend/778.js` | 90 | 43 | 48% |
| `lib/backend/main.js` | 654 | 498 | 76% |
| `lib/backend/electron-main.js` | 68 | 33 | 49% |
| `lib/backend/plugin-host.js` | 90 | 43 | 48% |
| `lib/backend/backend-init-theia.js` | 68 | 33 | 49% |
| `lib/backend/ipc-bootstrap.js` | 68 | 33 | 49% |
| `lib/backend/plugin-vscode-init.js` | 68 | 33 | 49% |
| `lib/backend/parcel-watcher.js` | 68 | 33 | 49% |
| **合计** | **5444** | **3485** | **64%** |

**这只是 i18n 通道的视角**（「语言包里有没有这条 i18n 原文」）。真正的界面覆盖率要把
DOM 通道算进来：词典里一部分条目命中在 i18n 调用点上（走 i18n 通道），一部分只以
裸字符串出现（只能靠 DOM 通道），还有一大批在 10 个 bundle 里根本搜不到 ——
那些是**运行时数据**，来自设备/配置描述符，静态扫描永远穷举不出来。

> 三类的具体条数**别抄进文档**，跑 `python main.py --coverage` 看实时值。
> 这一版文档就吃过亏：正文里的数字比实际词典落后了一倍多。

剩余 873 条未覆盖的 i18n 文案里，大量是 VS Code 设置项的说明文字（只在设置编辑器里可见）。
`--coverage` 会把它们**按出现次数排序**输出，次数越高 = 用户可见度越高，
可以直接 `tools/dump_missing.py` 导出成 CSV 交给翻译。

对比旧策略：旧策略只 patch 两个文件，`main.js` 的 626 处 i18n 调用
**一处都没生效**；现在十个文件是一个通道，且改的是函数而不是 6000 处字面量。

### 5.1 两条解析路径各占多少（实测）

覆盖率只说明「语言包里有没有这条」，还得确认框架真的会去查它。
`tools/e2e_i18n.py` 把框架**自己的**三个模块（`249401` / `448496` / `152985`）
从已注入的 bundle 里原样抠出来在 node 里跑，然后调用**框架自己的**
`nls.localizeByDefault`，抽样 450 条：

| 解析路径 | 条数 | 占比 | 说明 |
| --- | --- | --- | --- |
| `getDefaultKey` 反查到 key → 正常走 `translations`/`replacements` | 279 | **62%** | 框架元数据里有这条，天然生效 |
| 反查不到 key → 靠改写的 `fallback` 兜底命中 | 171 | **38%** | **没有 3.1 的补丁就永远是英文** |

这组数字说明了两件事：

- 框架自带的 VS Code 元数据只有 **1354** 条 key/message，覆盖不到全部界面文案；
- `fallback` 那个补丁不是「锦上添花」，而是**三分之一以上文案能不能中文的分水岭**。

## 6. 安全设计与验证

| 机制 | 位置 | 作用 |
| --- | --- | --- |
| 锚点唯一性 | `core/i18n.py::probe_text` | 命中数 ≠ 1 直接拒绝，绝不猜 |
| 幂等标记 | `MARKER = /*__CUBEMX2ZH__*/` | 已注入则拒绝二次注入 |
| 干净基线重建 | `session._clean_base` | 重复汉化 = 从 `.orig` 重新注入 |
| 语法门禁 | `i18n.node_check` | 写临时文件 → `node --check` → 通过才 `replace` 落盘 |
| 逐文件隔离 | `session.apply_i18n_patch` | 一个文件失败只回滚该文件，不牵连其它 |
| `.orig` 备份 | `core/backup.py`（复用） | 首次备份不覆盖，一键回滚 |
| gz 同步 | `core/gzip_sync.py`（复用） | `bundle.js.gz` 一并重压并备份 |

### 6.1 四层验证工具（每层证明的东西不同）

| 工具 | 验证方式 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| `tools/selftest_i18n.py` | 合成样本注入 + `node --check`；再探测真实锚点 | 生成器产出的 JS **语法**合法；锚点在真实文件上唯一命中；幂等生效 | 语义对不对 |
| `tools/verify_i18n.py` | 注入块抽出来在 node 里执行 + **复刻**的 `Localization.localize` | 数据与注入块语义正确：6919 条、locale=zh-cn、`{0}` 占位符、未收录原样返回、**packkeep 三路合并** | 用的是复刻实现，不是框架真代码 |
| `tools/e2e_i18n.py` | 抠出框架**真实模块** `249401`/`448496`/`152985` 在 node 里跑，调用真实 `localizeByDefault` | 整条链（反查 key → 查 replacements → format）在**框架自己的代码**上成立；并给出 62%/38% 路径占比 | 不覆盖 Electron/DOM 侧（`I18nPreloadContribution` 的实际时序） |
| `tools/verify_dom.py` | **真实 DOM（jsdom）** 里跑从已注入 bundle 抠出的 DOM 块 | DOM 通道的翻译行为：文本/属性/动态渲染/幂等，以及**不该翻的地方真的没翻**（编辑器、console、逃生舱、拼接文本） | 需要 `npm i jsdom`；不覆盖真实 Chromium 的细节差异 |

四层都是只读的，不改安装目录。另有一个**改文件之前**的门禁 `tools/test_locate.py`
（安装目录定位，见第 12 节），它不验证注入内容，但排在最前面。**推荐顺序**：

```bash
python tools/test_locate.py                      # 0. 定位门禁（不需要本机装了 CubeMX2）
python tools/test_update.py                      # 0b. 词典更新链路（fetch 打桩，不联网）
python tools/test_glossary.py                    # 0c. 术语门禁自证（证明它会拦）
python tools/selftest_i18n.py -g <安装根目录>    # 改完生成器先跑这个
python main.py --patch                           # 落盘（内含语法门禁）
python tools/verify_i18n.py                      # 落盘后 i18n 通道语义自检
python tools/verify_dom.py                       # 落盘后 DOM 通道行为自检
python tools/e2e_i18n.py                         # 端到端（框架真代码）
```

除 `selftest_i18n`（不给 `-g` 就是纯离线，跳过真实锚点探测）以外，**`-g` 全部可以
省略**：这些脚本走 `locate.pick_root()`，与 `main.py` 同一套发现逻辑，选定后把
**实际用的目录和来源**打印出来。脚本非交互，所以三条口子刻意留着 —— 不弹输入框、
不向下搜、找到多个目录不猜只报错。验证跑在另一台安装上是最坏的一种绿。

四个工具抓到的真实 bug 记录：
ASI 漏分号（selftest，**踩过两次**：一次是 `else`、一次是往块里加
`window.__CUBEMX2ZH__` 那一句）、`packkeep` 抹掉语言包自带表（verify 的 packkeep 用例）、
harness 硬编码 nls 变量名导致新增目标文件后误报（verify）、
f-string 花括号、三元分支缺括号、`try` 块提前闭合（后三个由语法门禁在落盘前拦下）。

## 7. 旧策略（字面量字节替换）已移除

v0.1.x 的做法是把界面文案当 bundle 里的字节来替换（`core/patcher.py` +
`session.apply_patch`，用 `--strategy literal` 调用）。v0.2.0 起这套**整体删除**，
本工具只剩 i18n 注入 + DOM 兜底一条路径。

删掉的东西：`core/patcher.py`、`session` 里的 `apply_patch` / `dry_run` /
`rollback` / `_iter_targets` / `_patch_one` / `files_cfg_gz`、
`main.py` 的 `--strategy` 参数、`tools/purge_unsafe_dict.py`、
`tools/simulate_patch_safety.py`。

**词典格式没动** —— `dict/localization.json` 仍是「字节片段 + `expect` 命中数」的
形态，`core/langpack.py` 负责把它还原成扁平语言包。所以老版本 EXE 与新版本
读的是同一份词典，远程词典更新也不受影响。

之所以曾经留着它：担心 ST 改版导致锚点失配、新策略直接罢工。
现在不再需要这层保险 —— 锚点失配时工具**拒绝写任何文件**（见第 6 节），
不会留下半汉化的烂摊子，用户按 README 的 FAQ 等词典更新即可。
两套策略共用 `session.py` 的维护成本，换不来实际收益，故删。

共用模块不变：`backup` / `gzip_sync` / `locate` / `paths` / `dictionary` /
`manual_csv` / `filters` / `process` / `update`。

## 8. 升级适配

应用升级后如果注入失败，先跑 `python main.py --probe -g <目录>`：

- 锚点命中数变化 → 对照本文第 3 节，调整 `core/i18n.py` 里的
  `A_FALLBACK` / `A_LOCFN` / `A_TAIL` / `A_PACKKEEP` / `A_ZHPACK` 正则。
- 模块 id（如 `897836`）变化 → `A_ZHPACK` 用的是捕获组，会自动适配；
  若 zh-cn 换成了别的写法，正则需要跟着改。

即使锚点全部失配，工具**不会写坏文件**：探测失败即拒绝注入。

### 8.1 锚点会不会误匹配到别处？

`A_TAIL` 这类锚点抓的是**压缩后的变量名**（`l` / `S` / `g` / `f` …），所以必须依赖
「唯一命中」这条硬规则：命中 0 次或 ≥2 次都拒绝注入。目前十个文件上
全部恰好 1 次（`--probe` 可复现）。

要换到别的版本上验证「抠出来的还能不能真是那个模块」，
用 `tools/jsmod.py`：它带一个最小 JS 词法器，能正确跳过字符串、模板字面量、
**正则字面量**和注释之后再配平括号。这一点很关键——天真地数括号会在
`const l=/{([^}]+)}/g;` 这种行上数错（字符类里的 `}` 被当成块结束），
抠出来的源码直接语法错误。`tools/e2e_i18n.py` 就是用它取模块的：
模块取错了，端到端必然失败，等于多了一道交叉校验。

## 9.DOM 通道：兜底翻译（裸字符串专用）

### 9.1 为什么需要它

见第 0 节：词典里 **1629 条只以裸字符串出现**，一次 i18n 都没调用。
i18n 通道改的是函数，DOM 通道只能改渲染出来的结果。

### 9.2 落在哪：bundle 末尾

`lib/frontend/index.html` 里是这么加载的：

```html
<script type="text/javascript" src="./bundle.js" charset="utf-8"></script>
```

所以**在 bundle 末尾追加一段 IIFE，就会在渲染进程里执行**，而且：
不需要锚点（应用改版也不会失配）、不需要新文件、不需要改 HTML。

追加前**必须换行**：`bundle.js` 的结尾是一行 `//# sourceMappingURL=bundle.js.map`
注释，不换行追加会把整段代码吞进注释里。

追加的代码在 `assets/dom-translate.js`（约 8KB），带自己的标记
`/*__CUBEMX2ZH_DOM_V1__*/`。`bundle.js` / `secondary-window.js` / `778.js`
三个前端文件各追加一份，靠 `window.__CUBEMX2ZH_DOM__` 保证只生效一次。

### 9.3 数据从哪来：不复制第二份中文表

i18n 通道在装载语言包时顺手把**同一个对象引用**挂到全局：

```js
NLS.localization = { ...replacements: { /* 6919 条 */ } };
if (typeof window !== "undefined") { try { window.__CUBEMX2ZH__ = NLS.localization; } catch(_){} }
```

DOM 通道直接读 `window.__CUBEMX2ZH__.replacements`，所以 bundle 里中文表只有一份
（后端是 Node 进程，`typeof window === "undefined"` 会跳过）。
如果用户把显示语言设成了别的语言，i18n 通道不会注入这张表，DOM 通道就自动空转 ——
**不会越权翻译**。

### 9.4 怎么翻：只做整串精确匹配

1. **整串相等**才算命中；命中不了再试「去掉首尾空白后相等」（命中则保留原空白）。
   不做任何子串替换，所以 `"Pins: 12"` 这种拼接文本不会被误改。
2. 属性也只翻 `placeholder` / `title` / `aria-label` / `aria-description` / `alt` / `label`。
   **绝不翻 `value`**，那是用户数据。
3. 长度 2–240 之外的字符串一律不碰（多半是正文/日志）。
4. 语言包里键名带中文的条目在装载时直接丢掉 —— 既防「翻出来的中文又被当键再翻一次」
   的替换链，也顺手挡掉脏词条。
5. 动态渲染用 `MutationObserver` 跟进（`childList` + `characterData` + 过滤过的
   `attributes`），React 重渲染把英文写回来时会被再翻一次。

### 9.5 三条安全边界：宁可少翻，不可翻错

| 边界 | 内容 |
| --- | --- |
| 标签黑名单（文本） | `script/style/noscript/template/title/textarea/code/pre/svg/math/canvas/iframe/embed/object/input/select/option/progress/meter` |
| 标签黑名单（属性） | 同上但**不含** `input/textarea/select` —— 它们的 `placeholder` 正是要翻的东西 |
| 选择器黑名单 | `.monaco-editor`（代码编辑器/查找框）、`.xterm`/`.theia-terminal`（终端）、`#theia-debug-console`（ST 构建输出）、`.theia-output`、`[contenteditable=true]` |
| 逃生舱 | 任何元素加 `data-cubemx2zh-skip` 属性即可整体退出翻译 |
| 运行期开关 | `window.__CUBEMX2ZH_DOM_DISABLE__ = true`（需在脚本执行前设置） |
| 自检入口 | `window.__CUBEMX2ZH_DOM__` = `{size, stats, rescan}`，F12 里可直接看翻了多少处 |

### 9.6 模板串：唯一一条规则

个别文案是拼出来的，整串匹配够不到，Pinout 的搜索框就是一个：

```js
// bundle.js 里长这样（O ∈ text / pin name / pin label / pin position）
return `Search for any ${O}...`;
```

所以 `assets/dom-translate.js` 里保留了一组**刻意极少**的规则：

```js
var RULES = [
  { re: /^Search for any (.{1,40})\.\.\.$/, format: m => "按" + inner(m[1]) + "搜索..." }
];
```

- 规则同样**只匹配整个字符串**（带锚点 `^...$`）；
- 捕获到的片段**再查一次词典**，查不到就原样保留，不做任何机翻；
- 插值片段本身（`text` / `pin name` …）的译法放在 `dict/localization.json` 的 `entries` 里。

### 9.7 被拆开的句子：按容器限定的片段表

快捷键弹窗是「整串匹配」的天敌 —— 一句话被 React 拆成了好几个文本节点：

```js
createElement("div",{className:"clock-popup-content"},
  "Hold ", createElement(Action,{name:"Space"}), " key while moving the mouse")
createElement("div",{className:"clock-popup-content"},
  "Press any of ", ←, →, ↑, ↓, " keys. Hold it to scroll faster")
createElement("div",{className:"clock-popup-content"},
  "Pinch open on the ", createElement(Action,{name:"Touchpad"}), " to zoom in")
```

每个文本节点单独匹配，于是 `"Hold "`、`"Press any of "`、`"Pinch open on the "`
统统查不到 —— 同一句里只有后半截是中文，就成了截图里那种中英夹杂。

难点在于：`Hold` / `Use` / `Press` / `Space` 这些**独立的短词**如果直接进全局表，
全站任何「恰好只有一个词」的文本节点都会被它们命中。所以按**容器**限定：

```js
var SCOPE_SEL = ".clock-popup-content,.pinout-popup-content";  // 从源码读出的 class
var SCOPE_MAP = { "Hold":"按住", "Use":"使用", "Press":"按下",
                  "Pinch open on the":"在", "Touchpad":"触控板", … };
```

- 容器选择器**是从 bundle 源码里读出来的**，不是猜的；
- 查找顺序：**作用域表优先，再退回全局表**（作用域表更具体，也能覆盖全局译法）；
- 空白处理与全局一致（去首尾空白后替换，保留原有排版）。

**片段表必须按「动词续写」写，不能按名词短语写。** 这是踩过的坑：
旧词典把 ` key while moving the mouse` 这类尾段当名词短语翻成了
`移动鼠标时按住的按键`，和前面的 `按住 [空格]` 拼起来就是
`按住 [空格] 移动鼠标时按住的按键` —— 每个词都译了，句子却不成话。
改成动词续写（`键并移动鼠标`）之后拼出来才是通顺的一句：

| 行 | 头段 + 键位 + 尾段 | 拼出来的结果 |
| --- | --- | --- |
| 平移 | `Hold` + `Space` + `key while moving the mouse` | 按住 `空格` 键并移动鼠标 |
| 平移 | `Press` + `Home` + `key to center the package in window` | 按下 `Home` 键可将封装居中显示于窗口 |
| 滚动 | `Press any of` + `←→↑↓` + `keys. Hold it to scroll faster` | 按下 `← →` 键可滚动，按住不放滚动更快 |
| 滚动 | `Use` + `Mouse wheel` + `to scroll vertically` | 使用 `鼠标滚轮` 可垂直滚动 |
| 滚动 | `Hold 2 fingers on the` + `Touchpad` + `and move left/right to scroll horizontally` | 双指放在 `触控板` 并左右移动可水平滚动 |
| 缩放 | `Hold` + `Ctrl` + `key and use` + `Mouse wheel` | 按住 `Ctrl` 键并使用 `鼠标滚轮` |
| 缩放 | `Pinch open on the` + `Touchpad` + `to zoom in` | 在 `触控板` 上双指张开可放大 |
| 选择 | `Press` + `Tab` + `key to put focus on the package or any pin` | 按下 `Tab` 键可将焦点置于封装或任意引脚 |
| 其他 | `Press any of` + `Page ↑ Page ↓` + `keys to rotate the package` | 按下 `Page ↑ Page ↓` 键可旋转封装 |

另外三条必须记住的：

- **键位名一律保留英文**（`Home` / `Shift` / `Ctrl` / `Alt` / `Tab` / `Enter` /
  `Escape` / `Backspace` / `Page ↑`）。`Home` 要特别处理：全局表里 `Home` 是
  「主页」（给别的界面用的），进了快捷键就成了「按下 主页 键」，
  所以作用域表里显式写 `"Home": "Home"` 把它压住；
- 这些尾段**只进作用域表、不进全局表**：一旦全局生效，别处出现同名字符串
  就会被改错；作用域表天然限定了影响范围；
- 源串本身有残句（`Hold Ctrl key and use Mouse wheel` 后面没动词，
  是 ST 自己漏写的）。**不替它补**，保持与原文一致。

> 反向断言同样进了测试夹具：`Hold`/`Use`/`Press`/`Space` 放在弹窗**外面**必须一动不动。

### 9.8 词典 `dict/localization.json`

「界面上有、但词典里没有」的漏网之鱼（`Saved` / `Split view` / `Saving...` /
`All changes saved` 这些当初由一张单独的补充表收着），现在**直接补进词典本身**。

v0.2.0 把扁平语言包扶正为词典之后，「主表」与「人工补充表」的区分就没有意义了 ——
两者形状本来就一样，分成两个文件只带来一个后果：**更新通道只覆盖其中一个**，
用户点了「词典更新」却拿不到最大那批词条。

- 键 = 英文原文（必须与界面字符串**逐字节一致**，含大小写与 NBSP）；
- 值 = 中文；
- 改完直接 `--patch`。语言包每次汉化现场构建，**没有单独的构建步骤**。

### 9.9 已知限制（诚实地列出来）

| 限制 | 说明 |
| --- | --- |
| 拼接文本不翻 | `"Pins: " + n` 这类整串不相等，不碰（这是刻意的，宁可不翻） |
| 模板串只能靠规则 | 目前只写了 Pinout 搜索框一条；新增需在 `RULES` 里加，并补测试 |
| 首屏可能一闪英文 | 中文表比 DOM 块先到就没事；若 nls 模块懒加载得晚，`boot()` 会轮询等待（100ms/400ms，最多约 10s） |
| 用户内容区靠黑名单 | 黑名单外的区域理论上可能误伤；但命中条件是「整串等于某条已译界面文案」，概率极低，且可用 `data-cubemx2zh-skip` 兜底 |
| 没有启动画面文案 | `splash-screen-assets/app-*.js` 里 `nlsMod=0`，压根没有 i18n 模块，属于独立话题 |

### 9.10 怎么验证（不用肉眼看）

`tools/verify_dom.py` 用 **jsdom** 造一个真实 DOM 夹具（还原截图上的情形：
工具栏裸字符串、`placeholder`、`title`、快捷键弹窗 **14 行完整分片句子**、
GPIO 配置面板的标签与下拉值、以及各种不该翻的区域），再把
**从已注入 bundle 里抠出来的真实代码**放进去执行，断言 249 条：

```bash
npm i jsdom                                  # 只在验证时需要
python tools/verify_dom.py -g <安装根目录>    # 测注入后的真实代码
python tools/verify_dom.py --asset           # 测源文件（注入前自检）
```

jsdom 的查找顺序是 `CUBEMX2ZH_NODE_MODULES` → 仓库根 `node_modules/` →
`tools/node_modules/` → `NODE_PATH` 里的每一项；都找不到时会把**试过的目录**
打出来。这里刻意不写死任何具体机器上的路径 —— 以前列着一条维护者机器上的
`node_modules`，等于把用户名发布进公开仓库，而且对别人毫无意义。
node 本身同理：`CUBEMX2ZH_NODE` → `PATH` → `%ProgramFiles%\nodejs\node.exe`。

覆盖的行为：文本/属性翻译、动态插入被翻译、重复注入幂等、
编辑器与 console 不动、逃生舱生效、拼接文本不被子串替换、
中文键不参与替换、首尾空白保留、模板串规则命中且不误伤、
**弹窗整句逐字比对（14 条，期望值写死而非查表）**、
**弹窗内的 `Home` 不得变成「主页」**、**弹窗外的短词不翻译（作用域反例）**、
**配置面板 17 条标签/选项值命中**、**`EXTI` 等专有名词保持英文**、
**NBSP 引脚术语命中**、**运行时数据类文案（`General information`）命中**。

## 10. 补翻流程：怎么找漏网文案、怎么补

真实用起来会发现「还有一堆没翻」，这些漏网文案其实是**三类**，
成因完全不同，混在一起找会走弯路。

### 10.1 五类漏网文案

| 类别 | 例子 | 为什么漏 | 怎么补 |
| --- | --- | --- | --- |
| **A. 走了 i18n 但包里没有** | VS Code 工作台的 `Remove Breakpoint`、`Edit Keybinding...` | 语言包只覆盖了旧词典扫到的那些；框架元数据有 1354 条，覆盖不到全部 | `tools/dump_missing.py` 导出 → 翻译 → 写进词典 `entries` |
| **B. 转义层级没对齐** | `Pin function` / `Pin type` / `Voltage Tolerance` / `Pin Options` | 源码里写作 `"\xA0 Pin function \xA0"`；CSV 的 `en` 列保留了转义写法，**构建语言包时没还原** → 键是字面 4 字符 `\xA0`，运行时是 NBSP，永远匹配不上 | 旧管线里由 `langpack.decode_source()` 修；**现在键直接存进词典，不再有这一层** |
| **C. 运行时数据，源码里根本没有** | `General information` / `Main features` / `Add a label` / `Software layer` / `Resource initialization code generation`；GPIO 面板的 `Pull` / `Initialization state` / `Active state` / `Speed` / `Output type` / `Push pull` / `No pull-up and no pull-down` / `Input` / `Callable` / `SW Label for signal`；PWR 面板的 `Applicative services` / `RAM retention in stop mode` / `Programmable voltage detector` / `Allow to generate runtime functions` / `Polarity` / `Voltage detection` / `Status pins` | 实测在**整个前端源码树**（含 `bundle.js.map` 的 9503 个源文件）里都搜不到 —— PWR 那批连 ST 自己的 `bundles/` 目录和整个安装目录都零命中，来自设备/配置描述数据 | 只能靠 DOM 通道按英文原文整串命中 → 写进词典 `entries`（拼写按界面截图逐字抄，见 10.5；带编号的走 10.6 的模板规则） |
| **D. 枚举组的兄弟项** | 同一个下拉里 `低 / Medium / 高 / Very high` 混排；另有 `Pull-up` / `Pull-down`、`Open drain`、`Eventout` / `Analog`、`Generated` / `Not generated` | 补词条时只抄了截图里**高亮的那一项**（当前值），同一枚举组其余选项全部没补。它和 A/C 不是一回事 —— A/C 是「收不到」，D 是**收集方式**出了问题 | 按**枚举组整组打通**（引脚模式 / 输出类型 / 上拉下拉 / 速度档位 / 代码生成 五组），并用 `dom_harness.js` 的 `GPIO_ENUM_GROUPS` 上硬门禁：整组任缺一条即红 |
| **E. 源码里有，但没走 i18n 的裸字面量** | ST 自绘弹窗的整句：`Exit ?` / `Your changes will be lost` / `To keep your modifications, save and close.` / `Save & Exit` / `Discard changes & Exit`；`Reset pins` / `Reset pin` / `Deactivate GPIO` / `Reserve GPIO` / `Reset configuration` / `Deactivate` / `Change mode` 各弹窗的整段文案 | 字面量**就在 `bundle.js` 里**（模块 `824589` 是本族弹窗组件本体，调用方 `934490` / `317245` / `47293` / `100815` / `83578` / `8516xxx` 把 title·header·message·confirmText 直接写进 props），但没有被 `localizeByDefault` 包住 ——i18n 通道的注入点碰不到裸字面量。**和 C 类的区别：C 类源码里搜不到，E 类搜得到** | 源码里能枚举 → **系统性扫调用方**（见 10.8），词条写进词典 `entries`，由 DOM 通道整串命中。别等截图 |

> 判断某条属于哪一类的办法：先在语言包里查，再去 `.orig` 里搜，
> 最后去 `bundle.js.map` 的 `sourcesContent` 里搜。三步能定性。
>
> **搜到了还要再看一层**：它有没有被 `localizeByDefault(...)` / `nls.localize(...)` 包住？
>
> - 包住了 → **A 类**。补进词典后 i18n 通道直接生效，不需要碰 DOM 通道。
> - 没包住（裸字面量）→ **E 类**。补进词典后要靠 DOM 通道整串命中 ——
>   因为 i18n 通道的注入点是 `localizeByDefault`，**它碰不到没被包住的字面量**。
>   这就是「词表里明明有 `Reset pins`，弹窗却还是英文」的原因。
> - 三步都搜不到 → **C 类**（运行时数据），只能用 10.6 的收集器收。

### 10.2 两个查找工具

```bash
# 只看「走了 i18n 调用的」字面量（i18n 通道覆盖范围）
python tools/dump_missing.py -g <安装根目录>          # -> missing.csv

# 看「裸字符串」缺口（DOM 通道覆盖范围），带 ui_score 打分
python tools/scan_bare_ui_text.py -g <安装根目录>      # -> bare-missing.csv
```

`scan_bare_ui_text.py` 有两个必须知道的坑，都已处理：

1. **每个目标文件里都内嵌了一份完整的 VS Code nls 元数据**（约 1354 条），
   不剥掉的话同一句英文会被重复统计 10 遍、排序完全失真 → `strip_metadata()`；
2. 差集里混着大量**错误消息和字体名**（`LinkedMap got modified during iteration.`、
   `Segoe UI`、`IPv4 range`），不是界面文案 → 用上下文打分
   （附近有 `createElement(` / `label:` / `placeholder:` 记 +3，
   附近有 `Error(` / `console.` / `%s` 记 -4）先排界面标签，再按次数排。

### 10.3 补一条的完整动作

```bash
# 1. 加词条（全局整段文案）
#    编辑 dict/localization.json 的 entries：  "英文原文": "中文"
# 2. 如果是「被拆开的句子里的短片段」，改这里（按容器限定）
#    assets/dom-translate.js 里的 SCOPE_MAP
# 3. 重建 + 重注入 + 验证
python main.py --patch -g <安装根目录>
python tools/verify_dom.py -g <安装根目录>
```

词典就是最终产物，改哪条就是哪条，不存在「被自动生成的东西冲掉」这回事。

### 10.4 应用正在运行时怎么验证

CLI 有进程守卫（检测到 CubeMX2 在跑就拒绝写盘，这是**故意**的）。
但验证不必停 —— 在**临时副本**上做完整体检：

```python
# 复制 10 个目标文件（含 .orig / .gz）到临时目录，在那里注入
session.apply_i18n_patch(临时根目录, pack, "verify-replica")
```

然后照常跑 `verify_i18n.py` / `verify_dom.py` / `e2e_i18n.py` 指向临时根目录。
实测能给出与真实安装完全等价的结论，且完全不碰运行中的应用。

### 10.5 C 类文案只能「按截图抄」，两个配套纪律

C 类（运行时数据）没法靠扫描源码找到，只能从界面截图里逐字抄。抄的时候有两条纪律：

1. **大小写/单复数逐字节一致。** 差一个字母就是 MISS，而且**不报错**。
   真踩过的例子：框架里 `Collapse All`（大写 A）早就有词条，但 Pinout 界面上用的是
   `EXPAND_COLLAPSE_LABEL` 里的 `Collapse all`（小写 a）—— 一个字母之差，
   界面上就一直是英文。同理 `No items in array`（复数）而不是 `No item in array`。
   抄之前先在语言包里按**中文值反查**一遍，能防一半的坑：
   ```python
   [k for k, v in repl.items() if v == "数组中没有项"]   # -> ['No items in array']
   ```
2. **抄错不会翻错，只会不翻。** DOM 通道是整串精确匹配，键抄错了顶多那一条
   保持英文，不会污染别处。所以这条链路可以放心迭代 —— 出一版、截图、再补。

判断一条属于哪类（A/i18n / DOM）：**先查语言包 → 再在 `.orig` 里搜 → 最后在
`bundle.js.map` 的 `sourcesContent` 里搜**。三步都搜不到，就是 C 类。

### 10.6 未收录文案收集器：不用再一张张截图

C 类只能从界面上抄，而截图一轮只能补十几条。所以**让翻译器自己攒**：
`assets/dom-translate.js` 里内置了一个收集器，任何**查表失败**的英文都会被记进
`localStorage`（键 `cubemx2zh-miss-v1`），完全本地、不联网、不上传。

```js
__cubemx2zhMiss("text")   // 累计的未收录文案，一行一条 —— 直接当词典 entries 的键
__cubemx2zhMiss()         // 打印 + 返回数组
__cubemx2zhMissClear()    // 清空，重新开始
```

过滤规则（免得把整屏正文都收进来）：长度 2~120、必须含 ASCII 字母、不含中文、
≤18 个词，字符集允许 `A-Za-z0-9 ,./()+&':%_-?[];!…`，总量上限 4000 条。
它是**跨会话累积**的，不是只采当前屏 —— 正常用一遍软件，再导出即可。

> **这套过滤条件放宽过一次（2026-09-19），原因值得记下来。**
> 第一版把问号、方括号、省略号排除在外，长度只到 60、词数只到 8 ——
> 结果**恰恰把弹窗里的整句文案全过滤掉了**：
> `Exit ?`（有问号）、`Exit [read-only] ?`（有方括号）、`Resetting…`（有省略号）、
> `To keep your modifications, save and close.`（勉强 8 个词）、
> `All GPIO-configured pins will be reset, and their configuration will be lost.`（11 个词）。
> 也就是说：**收集器把「真正缺的那一类」精准地漏掉了**，用户只能继续截图。
> 过滤规则越「聪明」，越容易挡掉你要找的东西 —— 宁可多记。
> `tools/dom_harness.js` 里有两条回归断言专门盯这次放宽
> （带问号的句子、超过 8 个词的长句，必须都能收到）。

> 只有记录、没有猜测：引脚名（`PA5`）、寄存器位名（`CSLEEP`）这类本来就要保留
> 英文的也会被一并记下，人工筛的时候忽略即可 —— **宁可多记也不要漏**。
> 过滤规则与导出接口在 `tools/dom_harness.js` 里都有断言，含两条反向断言
> （「不收录已翻译的」「不收录中文」）。

### 10.7 带编号的标签走模板规则，不写进词表

PWR 面板里每个唤醒引脚都会生成一条 `Wake-up pin <n>`，`n` 是数据（芯片决定有几个），
词条里写不下 —— 这类走 `assets/dom-translate.js` 的 `RULES`：

```js
{ re: /^(?:Wake-up|Wake up) pin (\d+)$/, format: function (m) { return "唤醒引脚 " + m[1]; } }
{ re: /^Pin (\d+)$/,                     format: function (m) { return "引脚 "   + m[1]; } }
```

`RULES` 的纪律：**只匹配整个字符串**（不加 `g`、绝不做子串替换），捕获到的片段
再查一次词典，查不到就原样保留，不机翻。目前只有三条（另一条是 Pinout 的搜索框）。

> 若 React 把那串拆成 `"Pin "` + `"4"` 两个文本节点，规则就匹配不到完整串 ——
> 这时由全局表里的 `Pin` / `Wake-up pin` 条目接住（`lookup()` 会先试「去掉首尾空白
> 后再匹配」，命中即保留原有空白）。两条路都覆盖，不会漏。


### 10.8 E 类（自绘弹窗）怎么系统性补齐，而不是等截图

E 类和 C 类最容易混，但**处理方式完全相反**：C 类源码里搜不到，只能等界面暴露；
E 类源码里搜得到，**可以一次枚举干净**。

起因是一次「退出确认弹窗」还全是英文（只有 `取消` 是中文）。排查过程就是 E 类的标准做法：

```text
1. 在 bundle.js 里搜整句 → 命中，落在一个干净的独立模块 934490 里：
     934490:((L,e)=>{"use strict"; ... e.getDialogProps=s})
     const t={default:{close:"Close project ?",exit:"Exit ?"}, ...}
     r={close:"Discard and Exit",exit:"Discard changes & Exit"};
   → 是裸字面量，没有 localizeByDefault 包着 ⇒ E 类，不是 C 类。

2. 反查谁在用它 → 用 tools/jsmod.py 抠模块：
     extract_module(bundle, 451677)   # CloseDirtyProjectWidget：调用 getDialogProps
     extract_module(bundle, 470990)   # ConfirmDialogComponent：把 props 透传给 ConfirmDialog
     extract_module(bundle, 824589)   # ← 本族弹窗的**组件本体**（关键发现）
   → 拿到组件本体后，「谁用了这个组件」就是全部同类调用方。

3. 找同类调用方的特征锚点（比按模块名猜可靠）：
     在 bundle.js 里搜 "iconType:\"warning\""（本族弹窗的独有 prop 组合）
     → 12 处命中，逐个看调用点，就把这一族的全部整句抄齐了：
       · 关闭/退出工程（934490）
       · 重置/停用/切换模式配置（317245 + 47293 的 dialogContent 表）
       · 重置引脚 / 重置引脚状态（100815）
       · GPIO 重置配置（83578）
       · 停用 GPIO / 保留 GPIO（8516xxx）
       · Pinout 工具栏的 Reset pins 弹窗

4. 和语言包做差集 → 只有 26 条缺（其余同族文案早就在词典里了）
   ⇒ 这一步很重要：**先差集再补**，否则会把已有的词条重复写一遍，
     还会因为手抄的拼写和词典不一致而互相覆盖。
```

两条经验：

- **同族组件的调用方才是收集单元**，不是「弹窗」这个视觉单位 ——
  找到一个组件本体，就能顺着它的 prop 特征把所有调用方捞干净。
- 只要东西在源码里，「截图 → 补词条」这个循环就是**错误的方法**；
  该做的是找到组件本体、沿调用方枚举（和 10.1 里 D 类「枚举组整组打通」同一条纪律）。

`tools/dom_harness.js` 里为这一族建了独立夹具（`#dlg-exit` / `#dlg-resetcfg` /
`#dlg-resetpin` / `#dlg-gpio` 等），还原真实 DOM 形状：标题带图标、
按钮是「`svg` 图标 + `span` 文字」。**这一点必须测** ——
`SVG` 在 `SKIP_TAGS_TEXT` 里，但按钮文字在 `svg` **外面**，属于正常文本节点，
必须能被翻到；夹具就是用来钉住这条边界的。

---

## 11. 术语规范：以 ST 官方中文文档为准

> 用户要求（2026-09-19）：**「所有翻译都要尽可能和 STM32 的官方中文文档对齐。」**
> 这一节把这条要求落成可执行的机制，而不是一句写在文档里的话。

### 11.1 为什么必须落成机制

早先的译法是从旧词典继承来的（早期机翻 + 社区译法混拼），问题有两类：

- **不是官方用词**：GPIO 速度档位曾译成「低 / 中 / 高 / 非常高」，
  而 ST 参考手册的中文用词是「低速 / 中速 / 高速 / 超高速」；
- **同一个词两种译法**：`Alternate Function` 译成「复用功能」（对），
  同一软件的 `With Alternate Functions` 却译成「含备用功能」——
  用户看到会以为是两个不同的概念。

这类问题**靠自觉是守不住的**：它们不报错、不影响功能，只在用户盯着界面时才暴露。
所以要有规范文件 + 自动门禁。

### 11.2 规范文件 `rules/glossary.zh.json`

唯一依据，人工维护，分三部分：

| 键 | 含义 | 例子 |
| --- | --- | --- |
| `terms` | 术语 → **唯一允许**的中文 | `Push pull` → 推挽、`Medium` → 中速 |
| `scope` | **多义词**：同一英文在不同字段下不同译法 | `Speed` 下的 `Low` → 低速（而电平字段的 `Low` → 低） |
| `keep_english` | 一律**保留英文**的技术缩写 | `GPIO`、`EXTI`、`HAL`、`ADC`、`SPI`… |

用词依据的优先级：

```
参考手册（RM）中文版  >  数据手册（DS）  >  用户手册（UM）/ 应用笔记（AN）  >  ST 官方中文网页
```

官方没有中文版的（例如 CubeMX 自己的界面词），用中文技术社区通行译法，
并在文件里的 `_comment` 注明依据 —— **不要凭语感翻**。

> 注意 `keep_english` **只收纯技术缩写**。键盘键位名（`Ctrl`/`Home`/`Space`…）
> 和 `Delete`/`Insert` 这类**同时有普通词义**的词不进来 ——
> 它们在快捷键弹窗里保持英文（由 `dom-translate.js` 的 `SCOPE_MAP` 负责），
> 但在别的语境里该译就译（菜单里的 `Home` → 主页、`Delete` → 删除）。
> 第一版把键位名也算进 `keep_english`，门禁立刻误报了 `Home`/`Delete` —— 已修正。

### 11.3 多义词：同一个英文，两套译法

`Low` / `High` 在 GPIO 面板里有两个身份：

| 出现位置 | 含义 | 官方译法 |
| --- | --- | --- |
| Speed（速度档位） | 输出速度 | **低速 / 高速** |
| Initialization state、Active state | 电平 | **低 / 高** |

全局表里只能存一套（存电平那套，覆盖面更广），速度那套必须
**只在 Speed 的上下文里**生效。判定用两个信号，命中任一即为 Speed：

1. **属性行 label**（下拉闭合、只显示当前值时）——
   从节点向上找第一个「恰好只含一个 `label`」的祖先，那层就是属性行，读它的 label；
2. **选项集合指纹**（下拉展开时）—— MUI 的 `Select` 展开后会把该字段的**全部选项**
   渲染进同一个 `role=listbox` 容器，而「速度档位」是唯一同时含
   `Medium` / `Very high` 的字段。（此时浮层挂在 `body` 上，已经脱离属性行，
   label 那条路走不通。）

两条路都判不出来 → **退回全局表，绝不猜**。
`tools/dom_harness.js` 里正反两组断言都写死了：Speed 容器内必须是
「低速/中速/高速/超高速」，Active state 容器内必须仍是「低/高」，
并且**没有任何上下文的孤立 `Low` 必须是「低」**。

### 11.4 门禁 `tools/check_glossary.py`

```bash
python tools/check_glossary.py        # 检查，违规即非零退出
python tools/check_glossary.py -v     # 连通过项一起打印
```

它查三件事：

1. `terms` 里的译法，语言包里必须一模一样；
2. `keep_english` 里的词**不应**出现在语言包中（出现就意味着界面会被改成中文）；
3. `scope` 的多义词译法必须真的内嵌在 `dom-translate.js` 里，且与全局译法**不同**
   （相同就说明全局表把速度那套用掉了，作用域形同虚设）。

已接进 `main.py`：

- `--import-dict`：把工作副本导回仓库前强制跑，违规则不导回；
- `--patch`：**落盘前强制跑**，违规直接中止 —— 避免偏离官方用词的译法被写进安装目录。

### 11.5 门禁第一次运行就抓到了 5 个问题

包括**术语表自身定义不精确**：

- `Home` → 「主页」、`Delete` → 「删除」被误判为"专有名词不该译" ——
  实际是 `keep_english` 收得太宽（已改为只收技术缩写）；
- `Medium` / `Very high` 被写进了 `scope` —— 但它们只用于速度档位、没有第二个含义，
  属于全局唯一译法，放进 `scope` 反而触发"全局与作用域相同"的告警（已移回 `terms`）。

这说明门禁不只是拦新错误，**也在反过来校验规范本身**。

### 11.6 新增/修改词条的流程

```bash
# 1. 先查规范
python -c "import json,io;print(json.load(io.open('rules/glossary.zh.json',encoding='utf-8'))['terms'].get('你要加的英文'))"

# 2. 规范里没有 → 查 ST 官方中文资料，补进 glossary.zh.json 的 terms
# 3. 改 dict/localization.json 的 entries（与术语表保持一致）
# 4. 门禁 + 落盘
python tools/check_glossary.py       # 先自查
python main.py --patch -g <安装目录>  # 门禁不过会直接中止
```

### 11.7 门禁自己也得防：两个会静默放行的口子（2026-09-21 修）

门禁的价值全在于「不过就不写盘」。所以**门禁自己降级，比它漏掉一条错译更危险**
—— 后者有人撞见，前者永远绿着。这两处都是这么来的：

1. **`check()` 里那句包装形态兜底**。原先开头是
   `repl = pack.get("replacements", pack)`，注释说兼容
   `{languageId, replacements}`。可那个形态**根本传不进来**（`langpack.build()`
   把非字符串值直接丢掉，各处喂进来的都是扁平表），而兜底本身有害：词典里只要
   有一条英文原文正好叫 `replacements`，`repl` 就变成了一个字符串，于是

   - 术语表带 `scope` 段时 → 走到 `repl.get(en)` 当场 `AttributeError`，`--patch` 崩；
   - 术语表没有 `scope` 段时（老规范形态）→ 44 条术语全部「不在字符串里」变成
     告警、专有名词全部「不在字符串里」变成通过，**零违规、门禁放行**，
     一条故意翻错的译法就这么过去了。

   现在直接用 `pack`，并在开头断言形状：不是扁平 `{str: str}` 就报违规、拒绝，
   不猜。
2. **术语表读不了时甩裸 traceback**。`run()` 原来只在「路径为 None」时返回 None，
   文件在但读不动 / JSON 被编辑坏了会抛 `FileNotFoundError` / `JSONDecodeError`，
   用户看到的是一堆 Python 内部报错，像汉化本身失败了。现在与「缺 DOM 脚本」
   同一档处理：返回一条 `warns` 并放行，同时 `brief()` 在这种状态下**不许**写
   「全部术语与术语表一致」。

`tools/test_glossary.py` 就是因为这两件事才存在的：门禁绿了不等于门禁在工作。
它每一组都配对照组 —— 先证明改错会被抓，再证明正常输入不误伤。

## 12. 安装目录定位：改文件之前的那道门

v0.1.0 有用户报「未找到 STM32CubeMX2 安装目录」且事后联系不上，所以这一节把
**所有可能原因**都当成已知缺陷处理，而不是只修那一个。

### 12.1 判据只有一条

`is_install_root()`：目录里必须直接含有

```text
resources/stm32cubemx-application/<版本>/dist/resources/app/lib/frontend/bundle.js
```

中间那段版本号用通配，所以应用升级不会让整套定位失效。这条判据足够独特
（10 个目标文件合计 86.5 MiB 的 Electron 应用里才有这个形状），因此后面所有
「多找几个候选」的放宽都是安全的 —— **放宽的是候选，不是判定**。

### 12.2 真实布局，以及用户会落在哪一层

实测（相对安装根的层数）：

```text
+1  <root>\stm32cubemx2-1.1.1.exe        根启动器；快捷方式指这里
+4  ...\1.1.1\dist                        任务管理器「打开文件所在的位置」的落点
+6  ...\dist\resources\app                我们真正操作的目录
+9  ...\app\lib\frontend\bundle.js        照文档翻文件能到的最深
```

关键结论：用户手输路径最常见的错法**不是给了一棵别的树，而是层级不对**，
而且几乎总是**太深**（`dist` 那一层里面就是 `STM32CubeMX2.exe`，看起来极像
正确的安装目录）。所以归一化的主方向是**往上走**（`MAX_WALK_UP=12`）——
祖先链唯一，零误判风险，每一级的代价只是一次 glob。

### 12.3 四路发现，以及它们各自的可靠性

| 顺序 | 来源 | 备注 |
|---|---|---|
| 1 | `-g` | 与手输走同一个 `resolve_root()` |
| 2 | 上次确认的 | `~/.stm32cubemx2-chinese/config.json`，读回必验真 |
| 3 | 环境变量 | `STM32CUBEMX2_PATH` / `STM32CubeMX2_PATH` |
| 4 | 卸载表 → 常见安装位置 | 见下 |

**卸载表是唯一通用的发现机制。** 本机实测：
`HKCU\...\Uninstall\STM32CubeMX2_1.1.1` 写着 `InstallLocation` 和 `DisplayIcon`；
而硬编码清单里的 `C:\Program Files\STMicroelectronics`、`C:\STMicroelectronics`
**一个都不存在**。v0.1.0 的写法是「键名含 cubemx 才去读值」，本机恰好键名带
版本号才走通 —— Inno Setup 一类默认写 GUID 键名的安装器会整个漏掉。现在改成
键名与 `DisplayName` 一起看，并且 `InstallLocation` 为空时从
`UninstallString` / `DisplayIcon` 反推（要能吃下带引号带参数、路径含空格、
`,0` 图标索引三种形态）。判伪仍然只在 `is_install_root`，所以宁可多匹配几个
兄弟产品（CubeProgrammer 之类）也不要漏。

**探过但不可用的途径**（免得再试一遍）：

| 途径 | 实测结果 |
|---|---|
| `App Paths\STM32CubeMX2.exe` | 不存在（只有**老版** CubeMX 注册了它） |
| `.ioc` 文件关联 | `.ioc → iocFile`，但 `shell\open\command` 不存在，拿不到 exe |
| `~\.theia-cubemx2` 用户数据 | 没有任何绝对安装路径（`recentworkspace.json` 是空的，日志全相对路径） |
| 运行中进程的路径 | 可行，但救不了「没运行」的场景；现在 `tasklist` 只用来判断在不在运行 |

候选清单一律由环境变量拼（`%ProgramFiles%`、`%ProgramFiles(x86)%`、
`%LOCALAPPDATA%` 及其 `Programs` 子目录、`%APPDATA%`、`%SystemDrive%` 及其
`ST` / `STMicroelectronics` / `Programs` 子目录、家目录），
**不含任何具体机器上的路径** —— 以前清单里写着维护者的
`C:\mysoftware\cubemx2`，打进发布包对别人毫无意义。
一个坑：`%SystemDrive%` 的值是 `C:` 不带斜杠，`Path("C:") / "X"` 得到的是
驱动器相对路径 `C:X`（指向 C 盘的当前工作目录），测试抓到的。

### 12.4 四道门禁

| 门禁 | 为什么要它 | 怎么证明它拦得住 |
|---|---|---|
| 自动扫描不许向下搜 | 起点一旦是 `C:\Users\<用户>`，会去遍历整个用户配置目录 | 父目录输入 + `allow_down=False` → 拿不到根 |
| 向下搜深度封顶（3） | 「多套了几层壳」不该被搜到 | 同一棵树 `max_depth=2` 不命中、`6` 命中 |
| 向下搜目录数封顶（3000） | 唯一的失控面 | 预算给 3 → `truncated=True` 且 `visited<=3`；真机从 `C:\Windows` 起搜 0.8 秒撞顶 |
| 向下搜的结果必须用户确认 | 认错根 = 往别的程序里写文件 | 输入 `n` → 既不采用也不写记忆 |

`Resolved.needs_confirm` 把最后一条编码进了类型：只有 `how == "down"` 才要问；
`exact` / `up` 是用户自己指的那一层，不问。所有 `input()` 都兜 `EOFError`，
管道和 CI 里不会炸。

### 12.5 记忆只存用户确认过的

自动扫描的唯一命中**不写**进 `config.json`：扫一轮不到 0.1 秒，记下来只是把一次
偶然误判固化成永久。写进去的只有三种 —— 手输的、多安装列表里挑的、`-g` 给的。
读回一律重新过 `resolve_root(allow_down=False)`：目录被挪走、JSON 坏了、指向假根，
都静默回退到扫描。`--doctor` 在记忆与实际定位不一致时把两者都打出来，并说明
删掉那个文件就能清掉记忆。

配置文件放在家目录的点目录而不是 `user_data_dir()`：「装在哪」属于这台机器，
不属于某一份工具副本 —— 把工具从桌面挪到 U 盘不该让它失忆。

### 12.6 报错要分三态

`diagnose_missing()` 把一句「未找到安装目录」拆成
`registry_unreadable` / `registered_but_unreachable` / `old_cubemx_only` /
`not_installed`，其中 `registered_but_unreachable` 会把它读到的
`InstallLocation` 原样列出来 —— 联系不上用户时，这一行就是全部的现场证据。

`old_cubemx_only` 是 v0.1.0 那份报告里最可能的真相：老版 STM32CubeMX
（Java，5.x/6.x）的用户基数远大于 CubeMX2，而仓库名叫 `STM32CubeMX2-Chinese`。
这种人需要的不是输入框，是一句「本工具不支持老版，也不支持 STM32CubeIDE」。

### 12.7 自检

```bash
python tools/test_locate.py
```

临时目录里搭假布局，60 条断言。它**不要求本机装了 CubeMX2**（没装时集成断言
自动跳过，只打印一行说明），所以可以直接进 CI —— 已挂在
`.github/workflows/check.yml`。
