/* STM32CubeMX2-Chinese · DOM 通道 —— DOM 层兜底翻译器
 *
 * 为什么需要它
 * ------------
 * CubeMX2 里其实有两套文案：
 *   1) 框架文案（Theia / VS Code 工作台：菜单、命令面板、设置项…）
 *      —— 走 nls.localizeByDefault，i18n 通道已经覆盖；
 *   2) ST 自己写的界面文案 —— 直接以**裸字符串**写在 React 代码里，从不调用 i18n：
 *         createElement(Button, {...}, "Reset pins")
 *         leftLabel:"Graphic view", rightLabel:"Table view"
 *         title:"Pinout legend" / x="Not configurable pin"
 *      Pinout 主界面（工具栏 / 图例 / 详情面板 / 包信息）整片都是这种，
 *      i18n 通道无论如何都够不到 —— 这不是它没生效，是那些字符串根本没进 i18n 通道。
 *
 * 本文件把语言包（由 i18n 通道注入到 window.__CUBEMX2ZH__ 的同一份对象）当查找表，
 * 在渲染之后遍历 DOM，把**整段完全等于**某个英文原文的文本节点 / 属性翻译掉，
 * 并用 MutationObserver 跟进后续动态渲染。
 *
 * 三条安全边界（宁可少翻，不可翻错）
 * --------------------------------
 *  1. 只做**整串精确匹配**（含「去掉首尾空白后再匹配」），不做任何子串替换，
 *     所以拼接文本（"Pins: 12"）不会被误改；
 *  2. 跳过编辑器 / 终端 / 构建输出 / code / pre / 可编辑区等「用户内容区」，
 *     见 SKIP_TAGS_TEXT / SKIP_TAGS_ATTR / SEL_SKIP；任何元素加
 *     data-cubemx2zh-skip 属性也可以自行退出翻译；
 *  3. 查表失败一律原样保留，绝不猜测、绝不机翻。
 *
 * 译法依据
 * --------
 *  STM32 专有名词 / 字段名 / 枚举值一律以 rules/glossary.zh.json 为准，
 *  该表以 ST 官方中文资料（参考手册 RM / 数据手册 DS / 用户手册 UM）为据。
 *  其中**多义词**（同一英文在不同字段下译法不同）不能靠全局表一刀切，
 *  由本文件的 FIELD_MAP + detectField() 按上下文判定 —— 例如
 *  `Low`/`High` 在「速度档位」译「低速 / 高速」（官方手册用语），
 *  在「初始状态 / 有效状态」这类电平字段仍译「低 / 高」。
 *
 * 和 i18n 通道的关系
 * --------------
 *  i18n 通道是主通道（走框架 API，占位符 {0} 由框架处理）；DOM 通道只是兜底补充。
 *  DOM 通道不依赖任何框架内部函数，只依赖 window.__CUBEMX2ZH__。
 *  如果用户的显示语言不是简体中文，i18n 通道根本不会注入那份表，
 *  本脚本就会自动空转 —— 尊重用户选择。
 */
(function () {
  "use strict";

  if (typeof window === "undefined" || typeof document === "undefined") return;
  if (window.__CUBEMX2ZH_DOM__) return;           // 幂等：重复注入只生效一次
  if (window.__CUBEMX2ZH_DOM_DISABLE__) return;   // 调试开关

  /* ---------- 需要跳过的区域 ---------- */

  // 按标签名跳过（文本节点用）：祖先链上任意一层命中即跳过
  var SKIP_TAGS_TEXT = {
    SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEMPLATE: 1, TITLE: 1,
    TEXTAREA: 1, CODE: 1, PRE: 1,
    SVG: 1, MATH: 1, CANVAS: 1, IFRAME: 1, EMBED: 1, OBJECT: 1,
    INPUT: 1, SELECT: 1, OPTION: 1, PROGRESS: 1, METER: 1
  };

  // 按标签名跳过（属性用）：这里**不含** INPUT/TEXTAREA/SELECT，
  // 因为它们的 placeholder / title 正是我们要翻的东西
  var SKIP_TAGS_ATTR = {
    SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEMPLATE: 1,
    CODE: 1, PRE: 1,
    SVG: 1, MATH: 1, CANVAS: 1, IFRAME: 1, EMBED: 1, OBJECT: 1
  };

  // 按选择器跳过：用户内容区
  var SEL_SKIP = [
    ".monaco-editor",            // 代码编辑器（含 diff / peek / 查找框）
    ".xterm", ".theia-terminal", // 终端
    "#theia-debug-console",      // ST 构建输出
    ".theia-output",
    "[contenteditable=true]",    // 富文本编辑区
    "[data-cubemx2zh-skip]"      // 预留逃生舱：任何地方都能自行退出翻译
  ].join(",");

  // 要翻的属性（注意：**绝不翻 value**，那是用户数据）
  var ATTRS = ["placeholder", "title", "aria-label", "aria-description", "alt", "label"];

  var MIN_LEN = 2;
  // 长度上限分两档，别再用一个数卡住所有文案：
  //   MAX_LEN      —— 短文案（标签 / 选项值），走「作用域表 → 字段多义词表 → 全局表」
  //   MAX_LEN_LONG —— 长文案（面板说明、校验消息、悬停提示），**只走全局表**，
  //                   且必须整串精确命中才替换。
  // 为什么必须留长档：ST 配置面板的 desc 动辄几百字（最长的 UART 波特率说明 1900+ 字），
  // 一个 240 的硬上限会把它们全部挡在门外 —— 面板标签翻好了，悬停说明和红色校验
  // 消息却整片还是英文，正是「只翻了 5%」那种观感的来源之一。
  // 长文案不可能是下拉选项，所以跳过字段判定，既省事也避免误判。
  var MAX_LEN = 240;
  var MAX_LEN_LONG = 4000;   // 硬上限：再长基本是正文/日志，不碰
  var MAX_WALK = 20000; // 单次遍历上限，防病态 DOM 卡死

  var stats = { text: 0, attr: 0, scanned: 0 };
  var MAP = null;
  var OBS = null;

  /* ---------- 查找表 ---------- */

  function buildMap(pack) {
    var map = Object.create(null), n = 0, k, v;
    for (k in pack) {
      if (!Object.prototype.hasOwnProperty.call(pack, k)) continue;
      v = pack[k];
      if (typeof v !== "string" || !v || v === k) continue;
      // 键里带中文的直接丢掉：既防「翻出来的中文又被当键再翻一次」的替换链，
      // 也顺手挡掉脏词条
      if (/[\u3400-\u9fff]/.test(k)) continue;
      map[k] = v;
      n++;
    }
    return n ? map : null;
  }

  // 整串匹配；匹配不上就试「去掉首尾空白」，命中的话保留原有空白
  // host：文本节点的宿主元素，只有「尾部冒号回退」那一档会用到它来判断
  //       标签是否独立；属性翻译没有这层语境，不传即可。
  function lookup(s, host) {
    var v = MAP[s];
    if (v !== undefined) return v;
    var t = s.replace(/^[\s\u00a0\u200b]+|[\s\u00a0\u200b]+$/g, "");
    if (t && t !== s) {
      v = MAP[t];
      if (v !== undefined) return s.replace(t, function () { return v; });
    }
    for (var i = 0; i < RULES.length; i++) {
      var m = RULES[i].re.exec(s);
      if (m) return RULES[i].format(m);
    }
    /* 尾部冒号回退：字段标签的通用兜底。
     * 界面上的字段标签写成 "Project path:"，而词典是从 i18n 字面量扫出来的，
     * 键不带冒号（"Project path" -> "工程路径"）—— 整串精确匹配对不上，
     * 于是 ST 自绘面板里**所有**这类标签都会漏翻。实测 bundle.js 里
     * 这种「词表里有、界面多个冒号」的至少 14 条（Project path: / Destination: /
     * Warning: / Name: / Type: / Output: …），逐条补冒号变体是打地鼠。
     * 这里剥掉尾部冒号再查一次，命中就把冒号补回去：仍然要求**整串**命中，
     * 不做子串替换，所以不会误伤。补全角「：」与词典里已有的 18 条
     * 带冒号词条（Format: -> 格式：）口径一致。
     * 放在 RULES **之后**：具体模板规则优先，这条只是最后一级回退。
     *
     * 限定：宿主元素里还有别的元素时不做这级回退。
     *   <label>Project path:</label>            → 独立标签，翻
     *   <label>Destination: " "</label>         → 只有文本子节点，翻
     *   <div>Pins: <b>12</b></div>              → 标签后面挂着数值元素，不翻
     * 最后一例是「标签 + 数值」拼出来的读数，冒号只是排版，翻它等于改动一个
     * 由两块节点合成的串 —— 那正是「拼接文本不做子串替换」这条反向断言要挡的。
     * 真要把这类读数翻掉，走 SCOPE_MAP 按容器限定，别放宽这一级。
     */
    var cm = /^([\s\S]*[^\s\u00a0\u200b])[:\uFF1A][\s\u00a0\u200b]*$/.exec(t);
    if (cm && !(host && host.children && host.children.length)) {
      v = MAP[cm[1]];
      if (v !== undefined) {
        if (!/[:\uFF1A]$/.test(v)) v += "\uFF1A";
        return t === s ? v : s.replace(t, function () { return v; });
      }
    }
    return null;
  }

  /* ---------- 少量「模板串」规则 ----------
   * 个别文案是拼出来的，例如 Pinout 的搜索框：
   *     `Search for any ${O}...`   （O ∈ text / pin name / pin label / pin position）
   * 整串匹配对它无效，只好为它单写一条规则。
   * 这一组刻意保持**极少、且只匹配整个字符串**：捕获到的片段会再查一次词典，
   * 查不到就原样保留，不做任何机翻。
   */
  function inner(s) {
    var v = MAP[s];
    return v === undefined ? s : v;
  }

  var RULES = [
    {
      re: /^Search for any (.{1,40})\.\.\.$/,
      format: function (m) {
        return "\u6309" + inner(m[1]) + "\u641c\u7d22...";
      }
    },
    /* PWR 面板里每个唤醒引脚会生成一条**带编号**的标签，编号是数据、文案是模板，
     * 整串匹配对不上（引脚有几个是芯片决定的），所以按编号捕获：
     *     Wake-up pin 4 → 唤醒引脚 4
     *     Pin 4         → 引脚 4
     * 若 React 把那串拆成 "Pin " + "4" 两个节点，则由全局表里的
     * "Pin" / "Wake-up pin" 条目接住（去首尾空白后匹配），两条路都覆盖。 */
    {
      re: /^(?:Wake-up|Wake up) pin (\d+)$/,
      format: function (m) { return "\u5524\u9192\u5f15\u811a " + m[1]; }
    },
    {
      re: /^Pin (\d+)$/,
      format: function (m) { return "\u5f15\u811a " + m[1]; }
    },

    /* ===== 运行期拼串的文案（表达式/helper 求值后才成形） ===== */
    /* 这些整串词条对不上：数字与信号名是运行期数据，只能按形状命中。
     * 原文来源：*_parameters.json 的拼接表达式，以及
     *   .config/template/helpers/*.js 里 helper 用模板串拼出的校验消息。 */
    {
      re: /^No (nominal|data-phase) bit timing matches bitrate ([\d.]+) kbps, sample point ([\d.]+) per mille, tolerance ([\d.]+) per mille, and kernel clock (.+?)\. Try a different sample point, a wider tolerance, or a different clock divider\.$/,
      format: function (m) {
        var which = m[1] === "nominal" ? "\u6807\u79f0" : "\u6570\u636e\u9636\u6bb5";
        return "\u6ca1\u6709\u4e0e\u6bd4\u7279\u7387 " + m[2] + " kbps\u3001\u91c7\u6837\u70b9 " + m[3]
             + "\u2030\u3001\u5bb9\u5dee " + m[4] + "\u2030\u3001\u5185\u6838\u65f6\u949f " + m[5]
             + " \u5339\u914d\u7684" + which + "\u4f4d\u65f6\u5e8f\u3002\u8bf7\u5c1d\u8bd5\u5176\u4ed6\u91c7\u6837\u70b9\u3001\u66f4\u5bbd\u7684\u5bb9\u5dee\u6216\u4e0d\u540c\u7684\u65f6\u949f\u5206\u9891\u3002";
      }
    },

    /* PWR：PVDIN 那档电平 */
    {
      re: /^Level (\d+) \(External input voltage using (.+)\)$/,
      format: function (m) { return "\u7535\u5e73 " + m[1] + "\uff08\u5916\u90e8\u8f93\u5165\u7535\u538b\uff0c\u4f7f\u7528 " + m[2] + "\uff09"; }
    },
    /* PWR：PVD/AVD 电平档位 */
    {
      re: /^Level (\d+) \((.+)\)$/,
      format: function (m) { return "\u7535\u5e73 " + m[1] + "\uff08" + m[2] + "\uff09"; }
    },
    /* 内部互连通道 */
    {
      re: /^Channel (.+) is internally connected$/,
      format: function (m) { return "\u901a\u9053 " + m[1] + " \u5185\u90e8\u5df2\u8fde\u63a5"; }
    },
    /* 定时器互补输出通道 */
    {
      re: /^Complementary output channel (.+?)N$/,
      format: function (m) { return "\u4e92\u8865\u8f93\u51fa\u901a\u9053 " + m[1] + "N"; }
    },
    /* 定时器输入通道 */
    {
      re: /^Input channel (.+)$/,
      format: function (m) { return "\u8f93\u5165\u901a\u9053 " + m[1]; }
    },
    /* 定时器输出通道 */
    {
      re: /^Output channel (.+)$/,
      format: function (m) { return "\u8f93\u51fa\u901a\u9053 " + m[1]; }
    },
    /* 「使用 xxx GPIO 引脚」 */
    {
      re: /^Use (.+?) GPIO pin$/,
      format: function (m) { return "\u4f7f\u7528 " + m[1] + " GPIO \u5f15\u811a"; }
    },
    /* 数据交换说明 */
    {
      re: /^Data swapping adjusts byte order for (.+) core before loading and after processing$/,
      format: function (m) { return "\u6570\u636e\u4ea4\u6362\u4f1a\u5728\u52a0\u8f7d\u524d\u548c\u5904\u7406\u540e\u8c03\u6574 " + m[1] + " \u5185\u6838\u7684\u5b57\u8282\u987a\u5e8f"; }
    },
    /* 比较器正输入 */
    {
      re: /^Plus \(input COMP(\d+)\)$/,
      format: function (m) { return "\u6b63\u8f93\u5165\uff08COMP" + m[1] + "\uff09"; }
    },
    /* 比较器窗口上限 */
    {
      re: /^Window upper threshold \(input COMP(\d+)\)$/,
      format: function (m) { return "\u7a97\u53e3\u4e0a\u9650\u9608\u503c\uff08COMP" + m[1] + " \u8f93\u5165\uff09"; }
    },
    /* 比较器窗口下限 */
    {
      re: /^Window lower threshold \(input COMP(\d+)\)$/,
      format: function (m) { return "\u7a97\u53e3\u4e0b\u9650\u9608\u503c\uff08COMP" + m[1] + " \u8f93\u5165\uff09"; }
    },
    /* 脉冲宽度校验消息 */
    {
      re: /^Pulse \((\d+) bits value\) must be between 0 and the counter period = (\d+)\.$/,
      format: function (m) { return "\u8109\u51b2\uff08" + m[1] + " \u4f4d\u503c\uff09\u5fc5\u987b\u4ecb\u4e8e 0 \u4e0e\u8ba1\u6570\u5668\u5468\u671f = " + m[2] + " \u4e4b\u95f4\u3002"; }
    },
    /* FLASH 等待周期/编程延时档位（含最高频率） */
    {
      re: /^(\d+) \((\d+(?:\.\d+)?) MHz max\)$/,
      format: function (m) { return m[1] + "\uff08\u6700\u9ad8 " + m[2] + " MHz\uff09"; }
    },
    /* 信号在本封装上不可用 */
    {
      re: /^(.+?) not available on this package\u2019s pins\.$/,
      format: function (m) { return m[1] + " \u4e0d\u5728\u6b64\u5c01\u88c5\u7684\u5f15\u811a\u4e0a\u63d0\u4f9b\u3002"; }
    },
    /* FDCAN 时钟校准一致性提示 */
    {
      re: /^Set nominal time segment 1 \+ nominal time segment 2 \+ 1 to match the clock calibration unit time quanta per bit time \((.+)\)\.$/,
      format: function (m) { return "\u8bf7\u4f7f\u300c\u6807\u79f0\u65f6\u95f4\u6bb5 1 + \u6807\u79f0\u65f6\u95f4\u6bb5 2 + 1\u300d\u7b49\u4e8e\u65f6\u949f\u6821\u51c6\u5355\u5143\u7684\u6bcf\u6bd4\u7279\u65f6\u95f4\u4efd\u989d\uff08" + m[1] + "\uff09\u3002"; }
    },
    /* FDCAN：ID1 与掩码冲突 */
    {
      re: /^Extended filter ID1 \((0x[0-9a-fA-F]+)\) conflicts with the current extended ID mask\. Update Filter ID1 or change the extended ID mask\.$/,
      format: function (m) { return "\u6269\u5c55\u6ee4\u6ce2\u5668 ID1\uff08" + m[1] + "\uff09\u4e0e\u5f53\u524d\u6269\u5c55 ID \u63a9\u7801\u51b2\u7a81\u3002\u8bf7\u66f4\u65b0\u6ee4\u6ce2\u5668 ID1 \u6216\u66f4\u6539\u6269\u5c55 ID \u63a9\u7801\u3002"; }
    },
    /* FDCAN：ID2 与掩码冲突 */
    {
      re: /^Extended filter ID2 \((0x[0-9a-fA-F]+)\) conflicts with the current extended ID mask\. Update Filter ID2 or change the extended ID mask\.$/,
      format: function (m) { return "\u6269\u5c55\u6ee4\u6ce2\u5668 ID2\uff08" + m[1] + "\uff09\u4e0e\u5f53\u524d\u6269\u5c55 ID \u63a9\u7801\u51b2\u7a81\u3002\u8bf7\u66f4\u65b0\u6ee4\u6ce2\u5668 ID2 \u6216\u66f4\u6539\u6269\u5c55 ID \u63a9\u7801\u3002"; }
    },
    /* FDCAN：ID1/ID2 冲突位 */
    {
      re: /^The current extended ID mask suppresses bits required by Filter ID1 and Filter ID2 \(conflict bits: (0x[0-9a-fA-F]+)\)\. Update the filter values or change the extended ID mask\.$/,
      format: function (m) { return "\u5f53\u524d\u6269\u5c55 ID \u63a9\u7801\u6291\u5236\u4e86\u6ee4\u6ce2\u5668 ID1 \u4e0e ID2 \u6240\u9700\u7684\u4f4d\uff08\u51b2\u7a81\u4f4d\uff1a" + m[1] + "\uff09\u3002\u8bf7\u66f4\u65b0\u6ee4\u6ce2\u5668\u503c\u6216\u66f4\u6539\u6269\u5c55 ID \u63a9\u7801\u3002"; }
    },
    /* FDCAN：起始 ID 被改写 */
    {
      re: /^Extended filter start ID changes from (0x[0-9a-fA-F]+) to (0x[0-9a-fA-F]+) after applying the current extended ID mask\. Adjust Filter ID1 or change the extended ID mask\.$/,
      format: function (m) { return "\u5e94\u7528\u5f53\u524d\u6269\u5c55 ID \u63a9\u7801\u540e\uff0c\u6269\u5c55\u6ee4\u6ce2\u5668\u8d77\u59cb ID \u7531 " + m[1] + " \u53d8\u4e3a " + m[2] + "\u3002\u8bf7\u8c03\u6574\u6ee4\u6ce2\u5668 ID1 \u6216\u66f4\u6539\u6269\u5c55 ID \u63a9\u7801\u3002"; }
    },
    /* FDCAN：结束 ID 被改写 */
    {
      re: /^Extended filter end ID changes from (0x[0-9a-fA-F]+) to (0x[0-9a-fA-F]+) after applying the current extended ID mask\. Adjust Filter ID2 or change the extended ID mask\.$/,
      format: function (m) { return "\u5e94\u7528\u5f53\u524d\u6269\u5c55 ID \u63a9\u7801\u540e\uff0c\u6269\u5c55\u6ee4\u6ce2\u5668\u7ed3\u675f ID \u7531 " + m[1] + " \u53d8\u4e3a " + m[2] + "\u3002\u8bf7\u8c03\u6574\u6ee4\u6ce2\u5668 ID2 \u6216\u66f4\u6539\u6269\u5c55 ID \u63a9\u7801\u3002"; }
    },
    /* FDCAN：有效范围为空 */
    {
      re: /^After applying the current extended ID mask, the effective range is empty \(start (0x[0-9a-fA-F]+), end (0x[0-9a-fA-F]+)\)\. Adjust the filter range or change the extended ID mask\.$/,
      format: function (m) { return "\u5e94\u7528\u5f53\u524d\u6269\u5c55 ID \u63a9\u7801\u540e\uff0c\u6709\u6548\u8303\u56f4\u4e3a\u7a7a\uff08\u8d77\u59cb " + m[1] + "\uff0c\u7ed3\u675f " + m[2] + "\uff09\u3002\u8bf7\u8c03\u6574\u6ee4\u6ce2\u5668\u8303\u56f4\u6216\u66f4\u6539\u6269\u5c55 ID \u63a9\u7801\u3002"; }
    },
    /* FDCAN：报文 RAM 溢出 */
    {
      re: /^Message RAM allocation exceeds the available RAM for (\S+) \((\d+) words available, (\d+) words allocated\)\. Reduce the number or size of Tx\/Rx FIFOs, buffers, or filters\.$/,
      format: function (m) { return "\u62a5\u6587 RAM \u5206\u914d\u8d85\u51fa " + m[1] + " \u7684\u53ef\u7528 RAM\uff08\u53ef\u7528 " + m[2] + " \u4e2a\u5b57\uff0c\u5df2\u5206\u914d " + m[3] + " \u4e2a\u5b57\uff09\u3002\u8bf7\u51cf\u5c11 Tx/Rx FIFO\u3001\u7f13\u51b2\u533a\u6216\u6ee4\u6ce2\u5668\u7684\u6570\u91cf\u6216\u5927\u5c0f\u3002"; }
    },    /* ===== ST 自有前端里的运行期拼串（源码是模板串） ===== */
    /* IDE 工程生成：工具链下拉的标签（源码是模板串 `${d} toolchain: `） */
    {
      re: /^(.+?) toolchain: ?$/,
      format: function (m) { return m[1] + " \u5de5\u5177\u94fe\uff1a"; }
    },
    /* IDE 工程生成：生成代码目录分组标题（含实例名） */
    {
      re: /^Generated Code Directories \((.+)\)$/,
      format: function (m) { return "\u751f\u6210\u7684\u4ee3\u7801\u76ee\u5f55\uff08" + m[1] + "\uff09"; }
    },
    /* 欢迎页：最近打开的工程卡片标题（含相对时间） */
    {
      re: /^Last Opened project - (.+)$/,
      format: function (m) { return "\u6700\u8fd1\u6253\u5f00\u7684\u5de5\u7a0b - " + m[1]; }
    },
    /* 导出失败的通知消息（showMessage 会显示） */
    {
      re: /^Could not export project\. Error: (.+)$/,
      format: function (m) { return "\u65e0\u6cd5\u5bfc\u51fa\u5de5\u7a0b\u3002\u9519\u8bef\uff1a" + m[1]; }
    },
    /* 导出面板：RTE 输入框的悬停说明 */
    {
      re: /^files directory of 'user modifiable component' for '(.+)'$/,
      format: function (m) { return "\u201c\u7528\u6237\u53ef\u4fee\u6539\u7ec4\u4ef6\u201d\u7684\u6587\u4ef6\u76ee\u5f55\uff08" + m[1] + "\uff09"; }
    },
  ];

  /* ---------- 弹窗内的片段表（按容器限定） ----------
   * 快捷键弹窗把一句话拆成多个文本节点，只能逐段翻译。源码（已确认）：
   *     "Hold " + <Action name="Space"/> + " key while moving the mouse"
   *     "Press any of " + <Action name="←"/> ... + " keys. Hold it to scroll faster"
   *     "Pinch open on the " + <Action name="Touchpad"/> + " to zoom in"
   * 其中 "Hold" / "Use" / "Press" / "Space" 这类**独立的短词**如果放进全局表，
   * 会在全站任何「恰好只有一个词」的文本节点上误命中，所以限定只在弹窗容器内生效。
   * 容器 class 名是从 bundle 源码里读出来的，不是猜的。
   */
  var SCOPE_SEL = ".clock-popup-content,.pinout-popup-content";

  var SCOPE_MAP = {
    /* ---- 行首动作词 ---- */
    "Hold": "\u6309\u4f4f",                                  // 按住
    "Click and Hold": "\u5355\u51fb\u5e76\u6309\u4f4f",        // 单击并按住
    "Press": "\u6309\u4e0b",                                  // 按下
    "Press any of": "\u6309\u4e0b",                           // 按下
    "Use": "\u4f7f\u7528",                                    // 使用

    /* ---- 键位名 ----
     * 弹窗里一律保留英文键名。Home 必须在这里覆盖全局：全局表里 Home -> 主页
     * （那是给别的界面用的），进了快捷键就变成「按下 主页 键」，不成话。
     */
    "Home": "Home",
    "Space": "\u7a7a\u683c",                                  // 空格
    "Mouse wheel": "\u9f20\u6807\u6eda\u8f6e",                 // 鼠标滚轮
    "Touchpad": "\u89e6\u63a7\u677f",                          // 触控板
    "Middle mouse button": "\u9f20\u6807\u4e2d\u952e",          // 鼠标中键
    "Left mouse button": "\u9f20\u6807\u5de6\u952e",            // 鼠标左键

    /* ---- 句中连接片段 ---- */
    "Hold 2 fingers on the": "\u53cc\u6307\u653e\u5728",        // 双指放在
    "key and use": "\u952e\u5e76\u4f7f\u7528",                  // 键并使用
    "key and hold 2 fingers on the": "\u952e\uff0c\u53cc\u6307\u653e\u5728", // 键，双指放在
    "Pinch open on the": "\u5728",                             // 在
    "Pinch close on the": "\u5728",                            // 在

    /* ---- 句尾补语 ----
     * 这一组是「通顺度」的关键。旧词典把这些片段当**名词短语**翻
     * （"...的按键"），和前面的「按住 / 按下」拼起来就成了
     *     「按住 空格 移动鼠标时按住的按键」
     * 这种半截话。这里按「动词续写」重写，拼出来才是完整的一句话：
     *     「按住 空格 键并移动鼠标」
     * 只放在作用域表里、不进全局表 —— 这些片段一旦全局生效，
     * 万一别处出现同名字符串就会被改错。
     */
    "key while moving the mouse": "\u952e\u5e76\u79fb\u52a8\u9f20\u6807",                                 // 键并移动鼠标
    "while moving the mouse": "\u5e76\u79fb\u52a8\u9f20\u6807",                                           // 并移动鼠标
    "key to center the package in window": "\u952e\u53ef\u5c06\u5c01\u88c5\u5c45\u4e2d\u663e\u793a\u4e8e\u7a97\u53e3",   // 键可将封装居中显示于窗口
    "keys. Hold it to scroll faster": "\u952e\u53ef\u6eda\u52a8\uff0c\u6309\u4f4f\u4e0d\u653e\u6eda\u52a8\u66f4\u5feb",  // 键可滚动，按住不放滚动更快
    "to scroll vertically": "\u53ef\u5782\u76f4\u6eda\u52a8",                                             // 可垂直滚动
    "to scroll horizontally": "\u53ef\u6c34\u5e73\u6eda\u52a8",                                           // 可水平滚动
    "and move left/right to scroll horizontally": "\u5e76\u5de6\u53f3\u79fb\u52a8\u53ef\u6c34\u5e73\u6eda\u52a8",        // 并左右移动可水平滚动
    "and move up/down to scroll vertically": "\u5e76\u4e0a\u4e0b\u79fb\u52a8\u53ef\u5782\u76f4\u6eda\u52a8",            // 并上下移动可垂直滚动
    "and move up/down to zoom out/in": "\u4e0a\u4e0b\u79fb\u52a8\u53ef\u7f29\u5c0f/\u653e\u5927",                        // 上下移动可缩小/放大
    "to zoom in": "\u4e0a\u53cc\u6307\u5f20\u5f00\u53ef\u653e\u5927",                                      // 上双指张开可放大
    "to zoom out": "\u4e0a\u53cc\u6307\u634f\u5408\u53ef\u7f29\u5c0f",                                     // 上双指捏合可缩小
    "keys to zoom in": "\u952e\u53ef\u653e\u5927",                                                       // 键可放大
    "keys to zoom out": "\u952e\u53ef\u7f29\u5c0f",                                                      // 键可缩小
    "key to put focus on the package or any pin": "\u952e\u53ef\u5c06\u7126\u70b9\u7f6e\u4e8e\u5c01\u88c5\u6216\u4efb\u610f\u5f15\u811a", // 键可将焦点置于封装或任意引脚
    "key to select the focused pin": "\u952e\u53ef\u9009\u4e2d\u5df2\u805a\u7126\u7684\u5f15\u811a",         // 键可选中已聚焦的引脚
    "key to unselect the selected pin": "\u952e\u53ef\u53d6\u6d88\u9009\u4e2d\u5df2\u9009\u5f15\u811a",     // 键可取消选中已选引脚
    "key to flip the package": "\u952e\u53ef\u7ffb\u8f6c\u5c01\u88c5",                                    // 键可翻转封装
    "keys to rotate the package": "\u952e\u53ef\u65cb\u8f6c\u5c01\u88c5"                                  // 键可旋转封装
  };

  /* ---------- 跳过判定 ---------- */

  function ownerEl(node) {
    return node.nodeType === 1 ? node : node.parentElement;
  }

  function ancestorHit(node, tagSet) {
    var el = ownerEl(node);
    while (el) {
      var tag = el.localName ? el.localName.toUpperCase() : "";
      if (tagSet[tag]) return true;
      if (el.isContentEditable) return true;
      el = el.parentElement;
    }
    return false;
  }

  function selectorHit(node) {
    var el = ownerEl(node);
    return !!(el && el.closest && el.closest(SEL_SKIP));
  }

  // 只在 SCOPE_SEL 容器内查 SCOPE_MAP；命中就按「去掉首尾空白后再替换」的方式返回，
  // 与 lookup() 的行为保持一致（保留原有空白，不改变排版）。
  function scopedHit(node, s) {
    var el = ownerEl(node);
    if (!el || !el.closest || !el.closest(SCOPE_SEL)) return null;
    var t = s.replace(/^[\s\u00a0\u200b]+|[\s\u00a0\u200b]+$/g, "");
    var v = SCOPE_MAP[t !== "" ? t : s];
    if (v === undefined) return null;
    return t !== "" && t !== s ? s.replace(t, function () { return v; }) : v;
  }

  /* ---------- 多义词：按「字段」决定译法 ----------
   * 为什么需要这一层
   * ----------------
   * `Low` / `High` 在 GPIO 面板里有**两个身份**：
   *   · 速度档位（Speed）—— ST 官方参考手册译「低速 / 高速」
   *   · 初始状态 / 有效状态 —— 那是电平，译「低 / 高」
   * 全局表里只能放一套（放电平那套，覆盖面更广），速度那套必须
   * **只在 Speed 的上下文里**生效，否则「有效状态」的电平会被译成「高速」。
   *
   * 两个判定信号，命中任意一个即认定为 speed：
   *   ① **属性行 label**：从节点向上找第一个「恰好只含一个 label」的祖先，
   *      那层就是属性行，读它的 label 文本是不是 Speed。
   *      （Select 闭合、只显示当前值时走这条）
   *   ② **选项集合指纹**：所在下拉容器（role=listbox / menu / ul）的文本里
   *      含 `Medium` / `Very high`。MUI 的 Select 展开时会把该字段的**全部选项**
   *      渲染进同一个容器，而「速度档位」是唯一同时含这两个词的字段 ——
   *      这就是字段指纹。（下拉展开时走这条；此时浮层挂在 body 上，
   *      已经脱离属性行，label 那条路走不通）
   *
   * 两条路都判不出来 → 返回 null，**退回全局表**，绝不猜。
   */
  var AMBIG = { "Low": 1, "High": 1 };

  var FIELD_MAP = {
    speed: {
      "Low": "\u4f4e\u901f",    // 低速
      "High": "\u9ad8\u901f"    // 高速
    }
  };

  var SPEED_LABELS = { "Speed": 1, "\u901f\u5ea6": 1 };
  // 已翻的「中速/超高速」也要认：同一次遍历里前面的节点可能已经翻过了
  var SPEED_MARKERS = /Medium|Very high|Very High|\u4e2d\u901f|\u8d85\u9ad8\u901f/;

  function trimWs(s) {
    return s.replace(/^[\s\u00a0\u200b]+|[\s\u00a0\u200b]+$/g, "");
  }

  // 属性行的 label：向上找第一个「只有一个 label」的祖先 —— 那是属性行；
  // 超过 5 层或遇到多个 label（说明范围太大，可能串到别的字段）就放弃。
  function rowLabel(node) {
    var el = ownerEl(node), hop = 0;
    while (el && hop++ < 5 && el.localName !== "BODY") {
      if (el.querySelectorAll) {
        var labs = el.querySelectorAll("label");
        if (labs.length > 1) return null;
        if (labs.length === 1) {
          return (labs[0].textContent || "").replace(/[\s\u00a0]+/g, "");
        }
      }
      el = el.parentElement;
    }
    return null;
  }

  function detectField(node) {
    var lab = rowLabel(node);
    if (lab && SPEED_LABELS[lab]) return "speed";
    var el = ownerEl(node);
    var box = el && el.closest ? el.closest('[role="listbox"],[role="menu"],ul') : null;
    if (box && SPEED_MARKERS.test(box.textContent || "")) return "speed";
    return null;
  }

  // 命中就返回替换后的整串（保留原有首尾空白），否则 null
  function fieldHit(node, s) {
    var t = trimWs(s);
    if (!AMBIG[t]) return null;
    var f = detectField(node);
    if (!f) return null;
    var v = FIELD_MAP[f][t];
    if (v === undefined) return null;
    return t === s ? v : s.replace(t, function () { return v; });
  }

  /* ---------- 未收录文案收集（只存本地，绝不联网） ----------
   * 为什么要有它
   * ------------
   * ST 配置面板里有**大量**文案是运行时数据：PWR / GPIO / DEBUG 各分组的标签、
   * 下拉选项、分组标题，连 bundle.js.map 里那 9503 个源文件都搜不到
   * （实测 `Applicative services` 在整个安装目录零命中），所以静态扫描
   * 永远穷举不出来。唯一可靠的信息源是「界面上真正显示过什么」。
   *
   * 而靠截图一轮只能补十几个词 —— 那就让翻译器自己把「查表失败」的文案攒起来：
   * 正常用一遍软件，然后在 F12 Console 里执行
   *     __cubemx2zhMiss()          // 返回数组；传 "text" / "json" 得到字符串
   * 就能拿到累计的全部未收录文案，直接当 dict/localization.json 里 entries 的键用。
   *     __cubemx2zhMissClear()     // 清空重新开始
   *
   * 只收「看起来像 UI 文案」的：纯 ASCII 可打印字符、含字母、长度 2~400、不含中文、≤60 个词。
   * 引脚名（PA5）、信号名这类会一并记下 —— 人工筛的时候忽略即可，
   * **宁可多记也不要漏**。
   *
   * 2026-09-19 放宽过一次：原先把问号、方括号、省略号排除在外，长度也只到 60、
   * 词数只到 8 —— 结果**恰恰把弹窗里的整句文案全过滤掉了**
   * （`Exit ?` / `To keep your modifications, save and close.` …），
   * 收集器收集不到，用户只能继续截图。放宽后才对得上。
   *
   * 2026-09-19 再放宽一次（同一个坑的第二次）：长度 120 / 词数 18 / 字符集仍挡掉了
   * ST 配置面板的 description —— 它们动辄 200 字以上、几十个词，还带
   * `<label>_init`、`bits[4:0]`、`(G: Gathering, ...)` 这类符号。
   * 结果是：**标签翻好了，面板里最长的那些说明文字一条都没被记下来**。
   * 现在长度放到 400、词数 60，字符集直接改用「全部可打印 ASCII」这个负向判定，
   * 不再逐个白名单符号。多记的噪音人工筛掉即可，漏记的代价才是真的高。
   */
  var MISS_KEY = "cubemx2zh-miss-v1";
  var MISS_MAX = 4000;
  var MISS_TEXT_MAX = 400;
  var MISS_WORD_MAX = 60;
  var missMap = null;
  var missCount = -1;
  var missTimer = null;

  function missLoad() {
    if (missMap) return missMap;
    missMap = Object.create(null);
    try {
      var raw = window.localStorage && window.localStorage.getItem(MISS_KEY);
      if (raw) {
        var o = JSON.parse(raw), k;
        for (k in o) {
          if (Object.prototype.hasOwnProperty.call(o, k)) missMap[k] = o[k];
        }
      }
    } catch (_) { /* 没有 localStorage（隐私模式 / jsdom）就只留内存 */ }
    return missMap;
  }

  function missFlush() {
    missTimer = null;
    try {
      if (window.localStorage) {
        window.localStorage.setItem(MISS_KEY, JSON.stringify(missLoad()));
      }
    } catch (_) { /* 配额满 / 被禁用：忽略，不影响翻译 */ }
  }

  function missNote(s) {
    var m = missLoad();
    var t = trimWs(s);
    if (m[t]) return;
    if (missCount < 0) missCount = Object.keys(m).length;
    if (missCount >= MISS_MAX) return;
    if (t.length < MIN_LEN || t.length > MISS_TEXT_MAX) return;
    if (!/[A-Za-z]/.test(t)) return;                        // 纯数字 / 符号
    if (/[\u3400-\u9fff]/.test(t)) return;                  // 已经是中文
    // 负向判定：只要是可打印 ASCII 就收（换行/制表符等在 trimWs 后已不存在）。
    // 不再逐个白名单符号 —— 白名单每漏一个符号，就有一整类文案记不下来。
    if (!/^[\x20-\x7e]+$/.test(t)) return;
    if (t.split(/\s+/).length > MISS_WORD_MAX) return;      // 太长，多半是正文 / 日志
    m[t] = 1;
    missCount++;
    if (!missTimer) missTimer = window.setTimeout(missFlush, 400);
  }

  window.__cubemx2zhMiss = function (fmt) {
    var keys = Object.keys(missLoad()).sort();
    if (fmt === "json") return JSON.stringify(keys, null, 2);
    if (fmt === "text") return keys.join("\n");
    if (typeof console !== "undefined" && console.log) {
      console.log("[STM32CubeMX2-Chinese] 未收录文案 " + keys.length +
        " 条（可直接当 dict/localization.json 里 entries 的键）：\n" + keys.join("\n"));
    }
    return keys;
  };

  window.__cubemx2zhMissClear = function () {
    missMap = Object.create(null);
    missCount = 0;
    try {
      if (window.localStorage) window.localStorage.removeItem(MISS_KEY);
    } catch (_) {}
    return 0;
  };

  /* ---------- 落地翻译 ---------- */

  function applyText(node) {
    if (!node || node.nodeType !== 3) return;
    var cur = node.nodeValue;
    if (!cur) return;
    var len = cur.length;
    if (len < MIN_LEN || len > MAX_LEN_LONG) return;
    if (ancestorHit(node, SKIP_TAGS_TEXT) || selectorHit(node)) return;
    // 查找顺序：弹窗片段表 → 字段多义词表 → 全局表（越具体越优先）
    // 长文案（面板说明）不可能是下拉选项，跳过前两张表，只做全局整串匹配。
    var hit = null;
    if (len <= MAX_LEN) {
      hit = scopedHit(node, cur);
      if (hit === null) hit = fieldHit(node, cur);
    }
    if (hit === null) hit = lookup(cur, ownerEl(node));
    if (hit === null) { missNote(cur); return; }   // 没收录 → 攒起来，供补词条
    if (hit === cur) return;
    node.nodeValue = hit;
    stats.text++;
  }

  function applyAttrs(el) {
    if (!el || el.nodeType !== 1 || !el.getAttribute) return;
    if (ancestorHit(el, SKIP_TAGS_ATTR) || selectorHit(el)) return;
    for (var i = 0; i < ATTRS.length; i++) {
      var name = ATTRS[i];
      var cur = el.getAttribute(name);
      if (!cur) continue;
      if (cur.length < MIN_LEN || cur.length > MAX_LEN_LONG) continue;
      var hit = lookup(cur);
      if (hit === null) { missNote(cur); continue; }   // 同上：没收录的攒起来
      if (hit === cur) continue;
      el.setAttribute(name, hit);
      stats.attr++;
    }
  }

  function walk(root) {
    if (!root || !MAP) return;
    if (root.nodeType === 3) return void applyText(root);
    if (root.nodeType !== 1) return;
    applyAttrs(root);
    if (typeof document.createTreeWalker !== "function") return;
    var w = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT,
      null,
      false
    );
    var n = w.nextNode(), guard = 0;
    while (n && guard++ < MAX_WALK) {
      stats.scanned++;
      if (n.nodeType === 3) applyText(n);
      else applyAttrs(n);
      n = w.nextNode();
    }
  }

  /* ---------- 跟进动态渲染 ---------- */

  function onMutations(records) {
    if (!MAP) return;
    for (var i = 0; i < records.length; i++) {
      var r = records[i];
      try {
        if (r.type === "childList") {
          var added = r.addedNodes;
          for (var j = 0; j < added.length; j++) walk(added[j]);
        } else if (r.type === "characterData") {
          applyText(r.target);
        } else if (r.type === "attributes") {
          applyAttrs(r.target);
        }
      } catch (_) { /* 单条失败不影响其它 */ }
    }
  }

  function attach() {
    if (OBS || typeof MutationObserver !== "function") return;
    var root = document.documentElement;
    if (!root) return;
    OBS = new MutationObserver(onMutations);
    OBS.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRS
    });
  }

  function rescan() {
    if (!MAP) return;
    try { walk(document.body || document.documentElement); } catch (_) {}
  }

  /* ---------- 启动 ---------- */
  // 语言包可能比本脚本晚到（nls 模块被懒加载），所以要轮询等它
  var tries = 0;

  function boot() {
    var holder = window.__CUBEMX2ZH__;
    var pack = holder && holder.replacements;
    if (!pack) {
      if (++tries <= 100) window.setTimeout(boot, tries <= 20 ? 100 : 400);
      return;
    }
    MAP = buildMap(pack);
    if (!MAP) return;
    window.__CUBEMX2ZH_DOM__ = { size: Object.keys(MAP).length, stats: stats, rescan: rescan };
    attach();
    rescan();
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", rescan);
    }
    // 首屏之后 React 还会补渲染若干轮，补一次兜底
    window.setTimeout(rescan, 1500);
    window.setTimeout(rescan, 5000);
    if (typeof console !== "undefined" && console.info) {
      console.info("[STM32CubeMX2-Chinese] DOM 兜底翻译器已启动，词条 " + Object.keys(MAP).length +
        " 条；界面上未收录的文案会记在本地，执行 __cubemx2zhMiss() 查看");
    }
  }

  boot();
})();
