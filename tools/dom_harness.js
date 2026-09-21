/* STM32CubeMX2-Chinese · DOM 通道兜底翻译器 —— 真实 DOM 离线验证
 *
 * 用法（由 tools/verify_dom.py 调用）：
 *   node dom_harness.js <注入块文件> <语言包 json>
 *
 * 为什么要用 jsdom 而不是自己写个假 DOM：
 *   自己写假 DOM 只能验证「我实现的对象」，验证不了真实行为；
 *   jsdom 提供真的 TreeWalker / MutationObserver / closest，
 *   而待测脚本正是从**已注入的 bundle** 里原样抠出来的，改坏了必然暴露。
 *
 * 夹具刻意还原截图上的几种情形：工具栏裸字符串、placeholder、title、
 * 以及各种「不该翻」的用户内容区（编辑器 / console / 逃生舱属性）。
 */
"use strict";

const fs = require("fs");
const { JSDOM } = require("jsdom");

const blockFile = process.argv[2];
const packFile = process.argv[3];
const block = fs.readFileSync(blockFile, "utf8");
const pack = JSON.parse(fs.readFileSync(packFile, "utf8"));

// 故意塞一个「键就是中文」的脏词条，用来验证防替换链的守卫
pack["\u4e2d\u6587\u952e"] = "\u4e0d\u5e94\u751f\u6548";

const FIXTURE = `<!DOCTYPE html><html><head><title>STM32CubeMX2</title></head><body>
<div id="root">
  <div class="p-MenuBar">
    <div class="p-MenuBar-item"><div id="m-project">Project</div></div>
    <div class="p-MenuBar-item"><div id="m-view">View</div></div>
    <div class="p-MenuBar-item"><div id="m-help">Help</div></div>
  </div>
  <div class="pinout-toolbar">
    <button id="btn-reset" data-testid="pinout-toolbar-reset-pins">Reset pins</button>
    <button id="btn-export">Export pinout</button>
    <div id="lbl-graphic">Graphic view</div>
    <div id="lbl-table">Table view</div>
    <input id="filter" placeholder="Sort by" />
    <input id="pin-search" placeholder="Search for any text..." />
    <span id="tip" title="Pinout legend">i</span>
  </div>
  <div class="legend">
    <h4 id="lbl-unassigned">Unassigned pins</h4>
    <div id="lbl-notcfg">Not configurable pin</div>
    <div id="aria-notconn" aria-label="Not connected pin"></div>
  </div>
  <div class="monaco-editor">
    <span id="monaco-text">Reset pins</span>
    <input id="monaco-input" placeholder="Sort by" />
  </div>
  <pre id="console-text">Reset pins</pre>
  <div data-cubemx2zh-skip><span id="skipme">Reset pins</span></div>
  <div id="mixed">Pins: <b>12</b></div>
  <div id="padded">   Pins   </div>
  <div id="cjk">\u4e2d\u6587\u952e</div>
  <div id="notinpack">Totally not in the pack ZZZ</div>
  <div class="pinout-toolbar" id="cfg-toolbar">
    <span id="tb-title">GPIO Configuration</span>
    <button id="btn-collapse">Collapse all</button>
    <!-- 引脚详情按钮：按钮文字与 tooltip 是同一个英文串，text / title 两条路径都要走到 -->
    <button id="tb-gpio" title="Configure GPIO">Configure GPIO</button>
  </div>
  <!-- 自绘下拉展开后的**全部选项** —— 上一轮漏网的根因就在这里：
       词典里只收了「当前值」那一条，同一枚举组的兄弟项全是英文，
       表现就是截图里的中英混排（低 / Medium / 高 / Very high）。 -->
  <div class="sw-configuration-fallback-renderer" id="cfg-dropdowns">
    <div class="select-option" id="opt-mode-input">Input</div>
    <div class="select-option" id="opt-mode-output">Output</div>
    <div class="select-option" id="opt-mode-eventout">Eventout</div>
    <div class="select-option" id="opt-mode-analog">Analog</div>
    <div class="select-option" id="opt-otype-pushpull">Push pull</div>
    <div class="select-option" id="opt-otype-opendrain">Open drain</div>
    <div class="select-option" id="opt-pull-none">No pull-up and no pull-down</div>
    <div class="select-option" id="opt-pull-up">Pull-up</div>
    <div class="select-option" id="opt-pull-down">Pull-down</div>
    <div class="select-option" id="opt-speed-low">Low</div>
    <div class="select-option" id="opt-speed-medium">Medium</div>
    <div class="select-option" id="opt-speed-high">High</div>
    <div class="select-option" id="opt-speed-veryhigh">Very high</div>
    <div class="select-option" id="opt-layer-callable">Callable</div>
    <div class="select-option" id="opt-layer-generated">Generated</div>
    <div class="select-option" id="opt-layer-notgenerated">Not generated</div>
  </div>
  <!-- 反向例：有独立词条的长串不能被新加的短键（Analog）吃掉前半截 -->
  <div id="chk-analog-signals">Analog signals</div>
  <div class="pinout-menu">
    <div id="mi-exclude">Exclude pin</div>
    <div id="mi-debug">Configure DEBUG</div>
  </div>
  <div class="sw-configuration-fallback-renderer" id="cfg-panel">
    <div class="property-header"><label id="cfg-lbl-pull">Pull</label></div>
    <div class="property-value"><div id="cfg-val-pull">No pull-up and no pull-down</div></div>
    <div class="property-header"><label id="cfg-lbl-init">Initialization state</label></div>
    <div class="property-value"><div id="cfg-val-init">Low</div></div>
    <div class="property-header"><label id="cfg-lbl-active">Active state</label></div>
    <div class="property-value"><div id="cfg-val-active">High</div></div>
    <div class="property-header"><label id="cfg-lbl-speed">Speed</label></div>
    <div class="property-header"><label id="cfg-lbl-otype">Output type</label></div>
    <div class="property-value"><div id="cfg-val-otype">Push pull</div></div>
    <div class="property-header"><label id="cfg-lbl-mode">Mode</label></div>
    <div class="property-value"><div id="cfg-val-mode">Input</div></div>
    <div class="property-header"><label id="cfg-lbl-exti">EXTI</label></div>
    <div class="property-value"><div id="cfg-val-exti">Disabled</div></div>
    <div class="property-header"><label id="cfg-lbl-layer">Software layer</label></div>
    <div class="property-value"><div id="cfg-val-layer">Callable</div></div>
    <div class="property-header"><label id="cfg-lbl-swlabel">SW Label for signal</label></div>
  </div>

  <!-- 多义词夹具：Low / High 在不同字段下必须译成不同中文（以 ST 官方手册用语为准）---
       ① Speed 展开态：容器里含 Medium / Very high → 靠「选项集合指纹」判定
       ② Active state 展开态：同样有 Low / High，但没有速度指纹 → 仍按电平译
       ③ Speed 闭合态：没有 listbox，只能靠属性行 label 判定
       ④ Initialization state 闭合态：同样只有 label，但不是 Speed → 按电平译
       ⑤ 反向：完全没有上下文的孤立 Low → 必须退回全局表（电平），不许猜成速度 -->
  <div class="cfg-row">
    <div class="property-header"><label>Speed</label></div>
    <div class="property-content">
      <ul role="listbox" id="speed-list">
        <li role="option" id="sp-low">Low</li>
        <li role="option" id="sp-med">Medium</li>
        <li role="option" id="sp-high">High</li>
        <li role="option" id="sp-vhigh">Very high</li>
      </ul>
    </div>
  </div>
  <div class="cfg-row">
    <div class="property-header"><label>Active state</label></div>
    <div class="property-content">
      <ul role="listbox" id="active-list">
        <li role="option" id="ac-low">Low</li>
        <li role="option" id="ac-high">High</li>
      </ul>
    </div>
  </div>
  <div class="cfg-row">
    <div class="property-header"><label>Speed</label></div>
    <div class="property-content"><div class="property-value" id="speed-closed">Low</div></div>
  </div>
  <div class="cfg-row">
    <div class="property-header"><label>Initialization state</label></div>
    <div class="property-content"><div class="property-value" id="init-closed">Low</div></div>
  </div>
  <div id="loose-low">Low</div>

  <div class="pinout-popup" id="sc-popup">
    <div class="pinout-popup-heading" id="sc-heading">Move/pan</div>
    <div class="clock-popup-content" id="popup">Hold <span class="k">Space</span> key while moving the mouse</div>
    <div class="pinout-popup-content" id="popup-mmb">Hold <span class="k">Middle mouse button</span> while moving the mouse</div>
    <div class="pinout-popup-content" id="popup-home">Press <span class="k">Home</span> key to center the package in window</div>
    <div class="pinout-popup-content" id="popup-arrows">Press any of <span class="k">&#8592;</span> <span class="k">&#8594;</span> keys. Hold it to scroll faster</div>
    <div class="pinout-popup-content" id="popup-wheel">Use <span class="k">Mouse wheel</span> to scroll vertically</div>
    <div class="pinout-popup-content" id="popup-shift">Hold <span class="k">Shift</span> key and use <span class="k">Mouse wheel</span> to scroll horizontally</div>
    <div class="pinout-popup-content" id="popup-touch-lr">Hold 2 fingers on the <span class="k">Touchpad</span> and move left/right to scroll horizontally</div>
    <div class="pinout-popup-content" id="popup-ctrl-touch">Hold <span class="k">Ctrl</span> key and hold 2 fingers on the <span class="k">Touchpad</span> and move up/down to zoom out/in</div>
    <div class="pinout-popup-content" id="popup-pinch">Pinch open on the <span class="k">Touchpad</span> to zoom in</div>
    <div class="pinout-popup-content" id="popup-zoomkeys">Press <span class="k">Ctrl</span> <span class="k">Alt</span> <span class="k">+</span> keys to zoom in</div>
    <div class="pinout-popup-content" id="popup-tab">Press <span class="k">Tab</span> key to put focus on the package or any pin</div>
    <div class="pinout-popup-content" id="popup-esc">Press <span class="k">Escape</span> key to unselect the selected pin</div>
    <div class="pinout-popup-content" id="popup-back">Press <span class="k">&#8592;Backspace</span> key to flip the package</div>
    <div class="clock-popup-content" id="popup-page">Press any of <span class="k">Page &#8593;</span> <span class="k">Page &#8595;</span> keys to rotate the package</div>
  </div>
  <div id="outside-hold">Hold</div>
  <div id="outside-use">Use</div>
  <div id="outside-press">Press</div>
  <div id="outside-space">Space</div>
  <div id="dbg-title">General information</div>
  <div id="nbsp-pin">&#160; Pin function &#160;</div>
  <div id="dyn-host"></div>

  <!-- PWR 电源面板：同为**运行时数据** —— Applicative services 在整个安装目录里零命中
       （含 28MB 的 bundle.js 与 74MB 的 bundle.js.map），确认是设备描述数据带出来的，
       与 GPIO 面板同源，只能靠 DOM 通道整串命中。标签按界面截图逐字还原。
       带编号的标签（Wake-up pin 4 / Pin 4）编号由芯片决定，词条里写不下，走 RULES 模板。
       注意：本文件整段夹具是**模板字符串**，HTML 注释里不能出现反引号，否则会提前截断。 -->
  <div class="pwr-panel" id="pwr-panel">
    <div class="group-title" id="pwr-adv">Advanced features</div>
    <div class="group-title" id="pwr-wakeup">Wake-up pins</div>
    <div class="tree-node" id="pwr-pin1">Pin 1</div>
    <div class="tree-node" id="pwr-pin4">Pin 4</div>
    <div class="property-header"><label id="pwr-lbl-wakeup4">Wake-up pin 4</label></div>
    <div class="property-header"><label id="pwr-lbl-polarity">Polarity</label></div>
    <div class="group-title" id="pwr-status">Status pins</div>
    <div class="tree-node" id="pwr-csleep">CSLEEP</div>
    <div class="tree-node" id="pwr-ramret">RAM retention in stop mode</div>
    <div class="group-title" id="pwr-flash">FLASH low power mode</div>
    <div class="property-header"><label id="pwr-lbl-lpm">Low power mode</label></div>
    <div class="property-value"><div id="pwr-val-lpm">Sleep</div></div>
    <div class="group-title" id="pwr-vdet">Voltage detection</div>
    <div class="tree-node" id="pwr-pvd">Programmable voltage detector</div>
    <div class="group-title" id="pwr-io">I/O retention in standby mode</div>
    <div class="property-header"><label id="pwr-lbl-allio">All I/O retention</label></div>
    <div class="property-header"><label id="pwr-lbl-jtagio">JTAG I/O retention</label></div>
    <div class="group-title" id="pwr-app">Applicative services</div>
    <div class="property-header"><label id="pwr-lbl-rt">Allow to generate runtime functions</label></div>
    <div class="property-header"><label id="pwr-lbl-lpe">Low power entry</label></div>
    <div class="property-header"><label id="pwr-lbl-me">Mode entry</label></div>
    <div class="property-header"><label id="pwr-lbl-lpx">Low power exit</label></div>
    <div class="property-header"><label id="pwr-lbl-lpmc">Low power mode check</label></div>
  </div>

  <!-- ST 配置描述符面板（MPU）：标签 / 选项 / 提示全部来自 packs 里的
       .config/stm32cxx_cortex_mpu_parameters.json —— 前端只是**通用渲染器**，
       按描述符的 properties.*.title 画控件，所以这些字面量在 bundle.js 与
       bundle.js.map（74MB）里都是零命中，属「运行时数据」，与 GPIO / PWR 面板同源，
       只能靠 DOM 通道整串命中。
       注意：本段夹具是模板字符串，HTML 注释里不能出现反引号。 -->
  <div class="st-desc-panel" id="mpu-panel">
    <div class="group-title" id="mpu-grp-main">Main features</div>
    <div class="property-header"><label id="mpu-lbl-mpu">Use MPU</label></div>
    <div class="property-header"><label id="mpu-lbl-fault">MPU during fault</label></div>
    <div class="property-header"><label id="mpu-lbl-mmf">Memory management fault</label></div>
    <div class="group-title" id="mpu-grp-default">Use default map</div>
    <div class="property-header"><label id="mpu-lbl-memtype">Memory type</label></div>
    <div class="property-value"><div id="mpu-val-normal">Normal</div></div>
    <div class="property-value"><div id="mpu-val-device">Device</div></div>
    <div class="property-value"><div id="mpu-val-nc">Not cacheable</div></div>
    <div class="property-header"><label id="mpu-lbl-wp">Write policy</label></div>
    <div class="property-value"><div id="mpu-val-wt">Write through</div></div>
    <div class="property-value"><div id="mpu-val-wb">Write back</div></div>
    <div class="group-title" id="mpu-grp-reg">Use region</div>
    <div class="property-header"><label id="mpu-lbl-base">Base address</label></div>
    <div class="property-header"><label id="mpu-lbl-limit">Limit address</label></div>
    <div class="property-header"><label id="mpu-lbl-attrnum">Attribute number</label></div>
    <div class="property-header"><label id="mpu-lbl-ap">Access permission</label></div>
    <div class="property-value"><div id="mpu-val-prw">Privilege read/write</div></div>
    <div class="property-header"><label id="mpu-lbl-ia">Instruction access</label></div>
    <div class="property-value"><div id="mpu-val-allrw">All read/write</div></div>
    <div class="property-value"><div id="mpu-val-gre">nGRE</div></div>
    <div class="group-title" id="mpu-grp-code">Resource initialization code generation</div>
    <div class="property-header"><label id="mpu-lbl-layer">Software layer</label></div>
    <div class="property-value"><div id="mpu-val-generated">Generated</div></div>
    <div class="group-title" id="mpu-grp-label">Add a label</div>
    <div class="group-title" id="mpu-grp-note">Note</div>
    <div class="group-title" id="mpu-grp-gen">General information</div>
    <!-- 说明文本 / 校验消息：同样是描述符里的字面量（description / message），
         前端当普通文本节点渲染，走同一条 DOM 通道。
         mpu-desc-12 是 24 条多行 desc 之一：渲染出来是**一个**文本节点，
         内容是整段带换行的字符串 —— 只翻其中一行整段都不生效。 -->
    <div class="property-description" id="mpu-desc-00">A region overlapping error is found, please check the configured regions.</div>
    <div class="property-description" id="mpu-desc-01">Any value that is not 32-byte aligned will have its lower order bits[4:0] ignored. It is recommended to provide a 32-byte aligned address.</div>
    <div class="property-description" id="mpu-desc-02">Base address of the MPU region. This address must be 32-byte aligned.</div>
    <div class="property-description" id="mpu-desc-03">Choose the type of memory. Normal is used for RAM and Flash and exposes cacheability attributes. Device is used for peripherals, sets a region as non cacheable and exposes bus configuration options.</div>
    <div class="property-description" id="mpu-desc-04">Define the bus access policies of Device Memory accesses (G: Gathering, R: Reordering, E: Early-Acknowledge).</div>
    <div class="property-description" id="mpu-desc-05">Enable the MPU during non-maskable interrupt (NMI) and hard fault events.</div>
    <div class="property-description" id="mpu-desc-06">Enable the default MPU memory configuration. If an address is not covered by any MPU region is accessed with this option enabled the base memory mapping applies. If the option is disabled, any memory access not covered by an MPU region triggers a memory management fault.</div>
    <div class="property-description" id="mpu-desc-07">Initialization code is generated and called in peripheral initialization.</div>
    <div class="property-description" id="mpu-desc-08">Initialization code is generated but not called in peripheral initialization.</div>
    <div class="property-description" id="mpu-desc-09">Initialization code is not generated.</div>
    <div class="property-description" id="mpu-desc-10">Labels allow to create aliases inside mx_hal_def.h file like '&lt;label&gt;_init', '&lt;label&gt;_deinit' and '&lt;label&gt;_gethandle'. These aliases can be used on application side.</div>
    <div class="property-description" id="mpu-desc-11">Limit address of the region. Last address included in the region (bits[4:0] are not used and considered to be 0x1F).</div>
    <div class="property-description" id="mpu-desc-12">MPU default configuration:

Because the instruction cache is enabled, the MPU must be enabled with the OTP/RO data area defined as a non-cacheable read-only region (0x08FF FE00-0x08FF FFFF range cover the full area) if the region is effectively used.</div>
    <div class="property-description" id="mpu-desc-13">Memory management fault is automatically enabled by the drivers. To enable hard fault escalation, please bind the CORTEX SCB panel.</div>
    <div class="property-description" id="mpu-desc-14">Name must be a valid C identifier: start with a letter or underscore, and contain only letters, digits, or underscores.</div>
    <div class="property-description" id="mpu-desc-15">Pick whether the initialization code should be generated and automatically called at startup.</div>
    <div class="property-description" id="mpu-desc-16">Resource initialization code generation</div>
    <div class="property-description" id="mpu-desc-17">The index of the attribute to apply to this region.</div>
    <div class="property-description" id="mpu-desc-18">The limit address must be greater than or equal to the base address, else the configuration will be ignored.</div>
    <div class="property-description" id="mpu-desc-19">The system escalates to hard fault if you do not enable it.</div>
    <div class="property-description" id="mpu-desc-20">The value of the next address after the limit address must be 32-byte aligned. Therefore, bits[4:0] are not used and considered to be 0x1F.</div>
    <div class="property-description" id="mpu-desc-21">This attribute defines the write policy of the region.</div>
    <div class="property-description" id="mpu-desc-22">This defines which types of accesses are allowed for the region.</div>
    <div class="property-description" id="mpu-desc-23">This note is informational and cannot be edited.</div>
    <div class="property-description" id="mpu-desc-24">This option defines the cache line allocation policy.</div>
    <div class="property-description" id="mpu-desc-25">To modify this parameter, enable the corresponding region first.</div>
  </div>

  <!-- 描述符里的**表达式类**文案：title / message 写的是 JS 表达式或 Mustache，
       运行期求值后才成为界面文字。整串词条对不上（数字与信号名是运行期数据），
       只能由 assets/dom-translate.js 的 RULES 按形状命中。
       本段夹具填的就是**求值之后**的样子，逐字对齐 helper 源码的输出格式。
       注意：本段夹具是模板字符串，HTML 注释里不能出现反引号。 -->
  <div class="st-desc-panel" id="rt-panel">
    <div class="property-value"><div id="rt-lvl">Level 1 (2.2 V)</div></div>
    <div class="property-value"><div id="rt-lvl-ext">Level 0 (External input voltage using PVD_IN)</div></div>
    <div class="property-value"><div id="rt-ch-int">Channel TIM1_CH1 is internally connected</div></div>
    <div class="property-value"><div id="rt-ch-comp">Complementary output channel CH1N</div></div>
    <div class="property-value"><div id="rt-ch-in">Input channel CH1</div></div>
    <div class="property-value"><div id="rt-ch-out">Output channel CH1</div></div>
    <div class="property-value"><div id="rt-gpio-use">Use ADC1_IN5 GPIO pin</div></div>
    <div class="property-value"><div id="rt-swap">Data swapping adjusts byte order for ADC core before loading and after processing</div></div>
    <div class="property-value"><div id="rt-comp-plus">Plus (input COMP2)</div></div>
    <div class="property-value"><div id="rt-comp-up">Window upper threshold (input COMP6)</div></div>
    <div class="property-value"><div id="rt-comp-lo">Window lower threshold (input COMP6)</div></div>
    <div class="property-value"><div id="rt-lat">0 (24 MHz max)</div></div>
    <div class="property-description" id="rt-na">ADC1_IN5 not available on this package&rsquo;s pins.</div>
    <div class="property-description" id="rt-pulse">Pulse (16 bits value) must be between 0 and the counter period = 65535.</div>
    <div class="property-description" id="rt-bitt">No nominal bit timing matches bitrate 500 kbps, sample point 750 per mille, tolerance 1 per mille, and kernel clock 80 MHz. Try a different sample point, a wider tolerance, or a different clock divider.</div>
    <div class="property-description" id="rt-bitt2">No data-phase bit timing matches bitrate 2000 kbps, sample point 800 per mille, tolerance 5 per mille, and kernel clock 80 MHz. Try a different sample point, a wider tolerance, or a different clock divider.</div>
    <div class="property-description" id="rt-ram">Message RAM allocation exceeds the available RAM for FDCAN1 (2560 words available, 3000 words allocated). Reduce the number or size of Tx/Rx FIFOs, buffers, or filters.</div>
    <div class="property-description" id="rt-eid">Extended filter ID1 (0x1FFFFFFF) conflicts with the current extended ID mask. Update Filter ID1 or change the extended ID mask.</div>
  </div>

  <!-- 描述符里的**标签类**文案（下拉选项值 / 计量单位）：这些是纯字面量，
       可整串精确匹配，词条由 .scratch/sp/gen_labels.py 按规则生成。
       夹具按「同一枚举组给两个相邻值」摆放 —— 单补一条会中英混排，
       这一组断言就是钉住「整组都翻」。 -->
  <div class="st-desc-panel" id="lbl-panel">
    <div class="property-value"><div id="lb-16bits">16 bits</div></div>
    <div class="property-value"><div id="lb-8bits">8 bits</div></div>
    <div class="property-value"><div id="lb-ws0">0 WS</div></div>
    <div class="property-value"><div id="lb-ws15">15 WS</div></div>
    <div class="property-value"><div id="lb-stop1">1 stop bit</div></div>
    <div class="property-value"><div id="lb-stop15">1.5 stop bits</div></div>
    <div class="property-value"><div id="lb-i2s16">16-bit on 16-bit channel</div></div>
    <div class="property-value"><div id="lb-i2s32">16-bit on 32-bit channel</div></div>
    <div class="property-value"><div id="lb-cmp">Compare - oc3refc</div></div>
    <div class="property-value"><div id="lb-cmpp">Compare pulse - oc4refc rising oc6refc falling</div></div>
    <div class="property-value"><div id="lb-q3">3 quarts full</div></div>
    <div class="property-value"><div id="lb-way">1-way</div></div>
    <div class="property-value"><div id="lb-hour">12-hour</div></div>
    <div class="property-value"><div id="lb-dsize">1 x data-size</div></div>
    <div class="property-value"><div id="lb-keep-hz">192 kHz</div></div>
    <div class="property-value"><div id="lb-keep-aes">AES CBC</div></div>
    <div class="property-value"><div id="lb-keep-ngre">nGRE</div></div>
  </div>

  <!-- 第二个文案来源：.config/template/helpers/*.js 里 helper 返回值直接进界面。
       全量候选只有 52 条，逐条看上下文后只有 5 条真到界面（其余是 throw /
       logDebug / 映射表键 / 生成代码注释 / 组件名 —— 完整判定表见
       .scratch/sp/helper_keep.json，每条都写了理由）。
       USB PHY 标题的调用点是描述符里的 "title"；
       FDCAN 三条**静态**校验消息进词表，含插值的几条走 RULES（见上面 rt-* 那组）。 -->
  <div class="st-desc-panel" id="helper-panel">
    <div class="property-value"><div id="hp-phy-hs">Embedded High Speed PHY</div></div>
    <div class="property-value"><div id="hp-phy-fs">Embedded Full Speed PHY</div></div>
    <div class="property-description" id="hp-noviol">No violation detected.</div>
    <div class="property-description" id="hp-maskfail">Extended ID mask check failed.</div>
    <div class="property-description" id="hp-rangestart">The current extended ID mask suppresses the configured range start, so this range cannot be matched. Adjust the range or change the extended ID mask.</div>
    <div class="property-description" id="hp-throw">Input must be a string</div>
  </div>

  <!-- ST 自绘 ConfirmDialog 家族：调用方把整句文案**写死在源码里**（裸字符串）——
       模块 934490 的 getDialogProps 返回的 title/header/messageLines/confirmText/discardText
       全部是字面量，不经过框架 i18n，所以只能靠 DOM 通道整串命中。
       夹具按真实 DOM 形状还原：标题带图标，按钮是「svg 图标 + span 文字」
       （SVG 在跳过表里，但文字在 svg 外面，必须能被翻到）。
       注意：本段夹具是模板字符串，HTML 注释里不能出现反引号。 -->
  <div class="MuiDialog-root" id="dlg-exit">
    <div class="dialog-title" id="dlg-exit-title">Exit ?<svg viewBox="0 0 1 1"></svg></div>
    <div class="dialog-header" id="dlg-exit-header">Your changes will be lost</div>
    <div class="dialog-message" id="dlg-exit-msg">To keep your modifications, save and close.</div>
    <button id="dlg-exit-discard"><svg viewBox="0 0 1 1"></svg><span>Discard changes &amp; Exit</span></button>
    <button id="dlg-exit-cancel">Cancel</button>
    <button id="dlg-exit-confirm"><svg viewBox="0 0 1 1"></svg><span>Save &amp; Exit</span></button>
  </div>
  <div class="MuiDialog-root" id="dlg-ro">
    <div class="dialog-title" id="dlg-ro-title">Exit [read-only] ?</div>
    <div class="dialog-header" id="dlg-ro-header">Your changes will be lost (project is read-only)</div>
    <div class="dialog-message" id="dlg-ro-msg">To keep your modifications, save project to a new location.</div>
  </div>
  <div class="MuiDialog-root" id="dlg-resetcfg">
    <div class="dialog-title" id="dlg-rc-title">Reset configuration</div>
    <div class="dialog-header" id="dlg-rc-header">Reset to default settings</div>
    <div class="dialog-message" id="dlg-rc-msg1">This will restore all settings to their default values.</div>
    <div class="dialog-message" id="dlg-rc-msg2">Your current configuration will be lost.</div>
    <button id="dlg-rc-btn">Reset</button>
  </div>
  <div class="MuiDialog-root" id="dlg-resetpin">
    <div class="dialog-title" id="dlg-rp-title">Reset pins</div>
    <div class="dialog-header" id="dlg-rp-header">All GPIO-configured pins will be reset, and their configuration will be lost.</div>
    <div class="dialog-message" id="dlg-rp-msg">Other configured pins will be preserved. Reserved pins will be reset.</div>
    <button id="dlg-rp-btn">Reset</button>
  </div>
  <div class="MuiDialog-root" id="dlg-gpio">
    <div class="dialog-title" id="dlg-gp-title">Deactivate GPIO</div>
    <div class="dialog-header" id="dlg-gp-header">The current GPIO configuration of this pin will be lost.</div>
    <div class="dialog-message" id="dlg-gp-msg">If you configure this pin again, all settings will be reset to their default values.</div>
    <button id="dlg-gp-btn">Deactivate</button>
  </div>
  <div id="dlg-unknown">This sentence is not in the dictionary at all</div>
  <div id="dlg-unknown-q">Is this sentence in the dictionary?</div>
</div>
</body></html>`;

const dom = new JSDOM(FIXTURE, { runScripts: "outside-only", pretendToBeVisual: true });
const { window } = dom;
const doc = window.document;

// i18n 通道注入的就是这个结构（同一个对象从 window 上拿）
window.__CUBEMX2ZH__ = {
  languageId: "zh-cn",
  languageName: "Chinese (Simplified)",
  localizedLanguageName: "\u7b80\u4f53\u4e2d\u6587",
  languagePack: true,
  translations: {},
  replacements: pack,
};

const checks = [];
function check(name, actual, expected) {
  checks.push({ name, ok: actual === expected, actual, expected });
}
function T(id) {
  const el = doc.getElementById(id);
  return el ? el.textContent : undefined;
}
function must(name) {
  if (!(name in pack)) {
    checks.push({ name: "语言包必须包含 " + name, ok: false, actual: "缺失", expected: name });
    return false;
  }
  return true;
}

// ---- 执行待测代码 ----------------------------------------------------------
let ran = false;
let err = null;
try {
  window.eval(block);
  ran = true;
} catch (e) {
  err = String(e && e.stack ? e.stack : e);
}

const diag = {
  ran,
  err,
  started: !!window.__CUBEMX2ZH_DOM__,
  size: window.__CUBEMX2ZH_DOM__ ? window.__CUBEMX2ZH_DOM__.size : 0,
  stats: window.__CUBEMX2ZH_DOM__ ? JSON.parse(JSON.stringify(window.__CUBEMX2ZH_DOM__.stats)) : null,
};

// ---- 静态部分（首屏一次性扫描） -------------------------------------------
for (const [id, en] of [
  ["btn-reset", "Reset pins"],
  ["btn-export", "Export pinout"],
  ["lbl-graphic", "Graphic view"],
  ["lbl-table", "Table view"],
  ["lbl-unassigned", "Unassigned pins"],
  ["lbl-notcfg", "Not configurable pin"],
  ["m-view", "View"],
  ["m-help", "Help"],
]) {
  if (must(en)) check("文本 " + id, T(id), pack[en]);
}

check("placeholder 被翻译", doc.getElementById("filter").getAttribute("placeholder"),
  must("Sort by") ? pack["Sort by"] : "Sort by");
check("title 被翻译", doc.getElementById("tip").getAttribute("title"),
  must("Pinout legend") ? pack["Pinout legend"] : "Pinout legend");
check("aria-label 被翻译", doc.getElementById("aria-notconn").getAttribute("aria-label"),
  must("Not connected pin") ? pack["Not connected pin"] : "Not connected pin");

// ---- 弹窗分片（作用域表） --------------------------------------------------
// 快捷键弹窗把一句话拆成多个文本节点，逐段翻译；短词只在容器内生效。
// 期望值**写死成字面量**，不去查语言包：这组译法由 assets/dom-translate.js 的
// SCOPE_MAP 决定，和语言包无关。写死才能保证「句子读起来通顺」这件事被真正断言住，
// 而不是「拼出来等于自己」这种同义反复。
// 结构逐字还原自 bundle 源码：`"Hold ",createElement(Action,{name:"Space"})," key while moving the mouse"`
for (const [id, expected] of [
  ["popup", "按住 空格 键并移动鼠标"],
  ["popup-mmb", "按住 鼠标中键 并移动鼠标"],
  ["popup-home", "按下 Home 键可将封装居中显示于窗口"],
  ["popup-arrows", "按下 \u2190 \u2192 键可滚动，按住不放滚动更快"],
  ["popup-wheel", "使用 鼠标滚轮 可垂直滚动"],
  ["popup-shift", "按住 Shift 键并使用 鼠标滚轮 可水平滚动"],
  ["popup-touch-lr", "双指放在 触控板 并左右移动可水平滚动"],
  ["popup-ctrl-touch", "按住 Ctrl 键，双指放在 触控板 上下移动可缩小/放大"],
  ["popup-pinch", "在 触控板 上双指张开可放大"],
  ["popup-zoomkeys", "按下 Ctrl Alt + 键可放大"],
  ["popup-tab", "按下 Tab 键可将焦点置于封装或任意引脚"],
  ["popup-esc", "按下 Escape 键可取消选中已选引脚"],
  ["popup-back", "按下 \u2190Backspace 键可翻转封装"],
  ["popup-page", "按下 Page \u2191 Page \u2193 键可旋转封装"],
]) {
  check("弹窗整句通顺: " + id, T(id), expected);
}
// 标题、键名保持英文（Home 的全局译法是「主页」，弹窗内必须被作用域表压住）
check("弹窗标题被翻译", T("sc-heading"), must("Move/pan") ? pack["Move/pan"] : "Move/pan");
check("弹窗内 Home 不译成「主页」", T("popup-home").indexOf("主页"), -1);

// 反向断言：同样的短词放在弹窗**外面**必须一动不动（这就是要按容器限定的原因）
check("弹窗外 Hold 不翻译", T("outside-hold"), "Hold");
check("弹窗外 Use 不翻译", T("outside-use"), "Use");
check("弹窗外 Press 不翻译", T("outside-press"), "Press");
check("弹窗外 Space 不翻译", T("outside-space"), "Space");

// ---- 运行时数据里的文案（源码里根本没有，只能靠 DOM 通道） ------------------
check("配置面板术语被翻译", T("dbg-title"),
  must("General information") ? pack["General information"] : "General information");

// GPIO 配置面板的标签 / 下拉选项值：同样来自运行时数据，bundle 与 sourcemap 里都搜不到，
// 拼写按界面截图逐字抄。DOM 通道只做整串精确匹配，所以万一某个键抄错，
// 表现是「那一条没翻」而不是翻错别处 —— 可以安全迭代。
for (const [id, en] of [
  ["tb-title", "GPIO Configuration"],
  ["btn-collapse", "Collapse all"],
  ["mi-exclude", "Exclude pin"],
  ["mi-debug", "Configure DEBUG"],
  ["cfg-lbl-pull", "Pull"],
  ["cfg-val-pull", "No pull-up and no pull-down"],
  ["cfg-lbl-init", "Initialization state"],
  ["cfg-val-init", "Low"],
  ["cfg-lbl-active", "Active state"],
  ["cfg-val-active", "High"],
  ["cfg-lbl-speed", "Speed"],
  ["cfg-lbl-otype", "Output type"],
  ["cfg-val-otype", "Push pull"],
  ["cfg-val-mode", "Input"],
  ["cfg-val-exti", "Disabled"],
  ["cfg-val-layer", "Callable"],
  ["cfg-lbl-swlabel", "SW Label for signal"],
]) {
  if (must(en)) check("配置面板: " + id, T(id), pack[en]);
}
// 反向断言：专有名词保持英文（EXTI 不在语言包里，必须一动不动）
check("EXTI 保持英文", T("cfg-lbl-exti"), "EXTI");

// ---- 下拉框的「兄弟选项」----------------------------------------------------
// 上一轮只补了截图里高亮的那一项（当前值），同一枚举组的兄弟项整组漏网，
// 于是同一个下拉里出现「低 / Medium / 高 / Very high」这种中英混排。
// 这里按枚举组断言**整组**，把「组内不许中英混排」变成硬门禁：
// 任一键没进语言包，must() 都会推一条失败断言，不会因为「没收录」而静默跳过。
const GPIO_ENUM_GROUPS = {
  "引脚模式": ["Input", "Output", "Eventout", "Analog"],
  "输出类型": ["Push pull", "Open drain"],
  "上拉/下拉": ["No pull-up and no pull-down", "Pull-up", "Pull-down"],
  "速度档位": ["Low", "Medium", "High", "Very high"],
  "代码生成": ["Callable", "Generated", "Not generated"],
};
for (const [group, keys] of Object.entries(GPIO_ENUM_GROUPS)) {
  const missing = keys.filter((k) => !must(k));
  // 注意 check() 用的是 ===，所以这里比长度而不是数组（[] !== []）
  check("枚举组完整无中英混排: " + group, missing.length, 0);
}

for (const [id, en] of [
  ["opt-mode-input", "Input"],
  ["opt-mode-output", "Output"],
  ["opt-mode-eventout", "Eventout"],
  ["opt-mode-analog", "Analog"],
  ["opt-otype-pushpull", "Push pull"],
  ["opt-otype-opendrain", "Open drain"],
  ["opt-pull-none", "No pull-up and no pull-down"],
  ["opt-pull-up", "Pull-up"],
  ["opt-pull-down", "Pull-down"],
  ["opt-speed-low", "Low"],
  ["opt-speed-medium", "Medium"],
  ["opt-speed-high", "High"],
  ["opt-speed-veryhigh", "Very high"],
  ["opt-layer-callable", "Callable"],
  ["opt-layer-generated", "Generated"],
  ["opt-layer-notgenerated", "Not generated"],
]) {
  if (must(en)) check("下拉选项: " + id, T(id), pack[en]);
}

// 同一个英文串在按钮文字与 tooltip 上各出现一次，两条路径都要翻
if (must("Configure GPIO")) {
  check("按钮文字: Configure GPIO", T("tb-gpio"), pack["Configure GPIO"]);
  check("按钮 tooltip: Configure GPIO",
    doc.getElementById("tb-gpio").getAttribute("title"), pack["Configure GPIO"]);
}

// 反向断言：整串匹配不做子串替换 —— 新加的短键 Analog 不能把长串吃掉半截
if (must("Analog signals")) {
  check("长串不被短键污染: Analog signals", T("chk-analog-signals"), pack["Analog signals"]);
}

// ---- 多义词：Low / High 必须按字段区分 --------------------------------------
// 依据 ST 官方中文资料：GPIO 速度档位是「低速 / 中速 / 高速 / 超高速」，
// 而「初始状态 / 有效状态」说的是电平，用「低 / 高」。
// 全局表里只存电平那套（覆盖面更广），速度那套必须靠上下文判定 ——
// 属性行 label（下拉闭合时）或选项集合指纹（下拉展开时）。
// 期望值这里**写死字面量、不查 pack**：词条一旦被改成非官方译法，断言必须红。
check("Speed 展开态: Low → 低速", T("sp-low"), "低速");
check("Speed 展开态: Medium → 中速", T("sp-med"), "中速");
check("Speed 展开态: High → 高速", T("sp-high"), "高速");
check("Speed 展开态: Very high → 超高速", T("sp-vhigh"), "超高速");
check("Active state 展开态: Low 仍是电平「低」", T("ac-low"), "低");
check("Active state 展开态: High 仍是电平「高」", T("ac-high"), "高");
check("Speed 闭合态（靠属性行 label）: Low → 低速", T("speed-closed"), "低速");
check("Initialization state 闭合态: Low → 低", T("init-closed"), "低");
// 反向：拿不到任何字段上下文时**必须**退回全局表，绝不许猜成速度档位
check("无上下文的 Low 退回全局表（电平）", T("loose-low"), "低");

// 引脚术语的真实字符串两端是「不换行空格 + 普通空格」（源码写作 \xA0 转义）。
// 这条例子的要点：**i18n 通道只会按原样查表，没有去空白兜底**，
// 所以构建语言包时必须把 \xA0 还原成真 NBSP，否则 i18n 通道永远命中不了。
const NBSP_KEY = "\u00a0 Pin function \u00a0";
check("NBSP 键已正确还原（i18n 通道依赖）",
  must(NBSP_KEY) ? pack[NBSP_KEY] : null, "\u00a0 \u5f15\u811a\u529f\u80fd \u00a0");
check("NBSP 引脚术语在 DOM 里被翻译", T("nbsp-pin"),
  must(NBSP_KEY) ? pack[NBSP_KEY] : "\u00a0 Pin function \u00a0");

// ---- PWR 电源面板（又是一批运行时数据） -------------------------------------
// 低功耗模式名以参考手册为准：睡眠 / 停止 / 待机 —— 不写「休眠 / 停机 / 待命」
// 这类别称，否则用户拿 ST 中文资料核对时对不上号。
for (const [id, en] of [
  ["pwr-adv", "Advanced features"],
  ["pwr-wakeup", "Wake-up pins"],
  ["pwr-lbl-polarity", "Polarity"],
  ["pwr-status", "Status pins"],
  ["pwr-ramret", "RAM retention in stop mode"],
  ["pwr-flash", "FLASH low power mode"],
  ["pwr-lbl-lpm", "Low power mode"],
  ["pwr-val-lpm", "Sleep"],
  ["pwr-vdet", "Voltage detection"],
  ["pwr-pvd", "Programmable voltage detector"],
  ["pwr-io", "I/O retention in standby mode"],
  ["pwr-lbl-allio", "All I/O retention"],
  ["pwr-lbl-jtagio", "JTAG I/O retention"],
  ["pwr-app", "Applicative services"],
  ["pwr-lbl-rt", "Allow to generate runtime functions"],
  ["pwr-lbl-lpe", "Low power entry"],
  ["pwr-lbl-me", "Mode entry"],
  ["pwr-lbl-lpx", "Low power exit"],
  ["pwr-lbl-lpmc", "Low power mode check"],
]) {
  if (must(en)) check("PWR 面板: " + id, T(id), pack[en]);
}
// 反向断言：PWR 寄存器位名保持英文（CSLEEP 不在语言包里，必须一动不动）
check("CSLEEP 保持英文", T("pwr-csleep"), "CSLEEP");

// 带编号的标签是**模板串**（编号由芯片决定，词条里写不下），走 dom-translate.js 的 RULES。
// 期望值写死字面量，不去查 pack —— 否则「自己等于自己」，断言等于没写。
check("模板串: Wake-up pin 4 → 唤醒引脚 4", T("pwr-lbl-wakeup4"), "唤醒引脚 4");
check("模板串: Pin 4 → 引脚 4", T("pwr-pin4"), "引脚 4");
check("模板串: Pin 1 → 引脚 1", T("pwr-pin1"), "引脚 1");

// ---- ST 配置描述符面板（MPU）------------------------------------------------
// 2026-09-19 找到「配置面板整页英文」的真正源头：文案不在源码里，而在
//   %LOCALAPPDATA%\stm32cube\packs\STMicroelectronics\<pack>\<版本>\.config\*_parameters.json
// 前端是通用渲染器，按描述符画控件。所以静态扫 bundle / sourcemap 永远扫不到 ——
// 之前判成「运行时数据」是对的，但**不等于只能靠截图**：描述符本身就是权威清单，
// tools/extract_st_params.py 一轮就能把某个面板枚举穷尽。
for (const [id, en] of [
  ["mpu-grp-main", "Main features"],
  ["mpu-lbl-mpu", "Use MPU"],
  ["mpu-lbl-fault", "MPU during fault"],
  ["mpu-lbl-mmf", "Memory management fault"],
  ["mpu-grp-default", "Use default map"],
  ["mpu-lbl-memtype", "Memory type"],
  ["mpu-val-normal", "Normal"],
  ["mpu-val-device", "Device"],
  ["mpu-val-nc", "Not cacheable"],
  ["mpu-lbl-wp", "Write policy"],
  ["mpu-val-wt", "Write through"],
  ["mpu-val-wb", "Write back"],
  ["mpu-grp-reg", "Use region"],
  ["mpu-lbl-base", "Base address"],
  ["mpu-lbl-limit", "Limit address"],
  ["mpu-lbl-attrnum", "Attribute number"],
  ["mpu-lbl-ap", "Access permission"],
  ["mpu-val-prw", "Privilege read/write"],
  ["mpu-lbl-ia", "Instruction access"],
  ["mpu-val-allrw", "All read/write"],
  ["mpu-grp-code", "Resource initialization code generation"],
  ["mpu-lbl-layer", "Software layer"],
  ["mpu-val-generated", "Generated"],
  ["mpu-grp-label", "Add a label"],
  ["mpu-grp-note", "Note"],
  ["mpu-grp-gen", "General information"],
]) {
  if (must(en)) check("描述符面板: " + id, T(id), pack[en]);
}
// 反向断言：ARM 总线属性名是协议术语，语义就写在字母里（Gathering / Reordering /
// Early-acknowledge 的缩写），翻成中文反而没法对照 ARM 文档 —— 必须保持原样。
check("nGRE 保持英文", T("mpu-val-gre"), "nGRE");

// 描述符面板的**说明文本 / 校验消息**：面板里最容易被整片漏掉的一类
// （标签往往被注意到，悬停提示与红色校验消息不会）。
// 期望值走 pack（前面已由 must() 保证键存在），键由
// .scratch/sp/gen_mpu_harness.py 从描述符直接生成，逐字节精确、不手抄。
for (const [id, en] of [
  ["mpu-desc-00", "A region overlapping error is found, please check the configured regions."],
  ["mpu-desc-01", "Any value that is not 32-byte aligned will have its lower order bits[4:0] ignored. It is recommended to provide a 32-byte aligned address."],
  ["mpu-desc-02", "Base address of the MPU region. This address must be 32-byte aligned."],
  ["mpu-desc-03", "Choose the type of memory. Normal is used for RAM and Flash and exposes cacheability attributes. Device is used for peripherals, sets a region as non cacheable and exposes bus configuration options."],
  ["mpu-desc-04", "Define the bus access policies of Device Memory accesses (G: Gathering, R: Reordering, E: Early-Acknowledge)."],
  ["mpu-desc-05", "Enable the MPU during non-maskable interrupt (NMI) and hard fault events."],
  ["mpu-desc-06", "Enable the default MPU memory configuration. If an address is not covered by any MPU region is accessed with this option enabled the base memory mapping applies. If the option is disabled, any memory access not covered by an MPU region triggers a memory management fault."],
  ["mpu-desc-07", "Initialization code is generated and called in peripheral initialization."],
  ["mpu-desc-08", "Initialization code is generated but not called in peripheral initialization."],
  ["mpu-desc-09", "Initialization code is not generated."],
  ["mpu-desc-10", "Labels allow to create aliases inside mx_hal_def.h file like '<label>_init', '<label>_deinit' and '<label>_gethandle'. These aliases can be used on application side."],
  ["mpu-desc-11", "Limit address of the region. Last address included in the region (bits[4:0] are not used and considered to be 0x1F)."],
  ["mpu-desc-12", "MPU default configuration:\n\nBecause the instruction cache is enabled, the MPU must be enabled with the OTP/RO data area defined as a non-cacheable read-only region (0x08FF FE00-0x08FF FFFF range cover the full area) if the region is effectively used."],
  ["mpu-desc-13", "Memory management fault is automatically enabled by the drivers. To enable hard fault escalation, please bind the CORTEX SCB panel."],
  ["mpu-desc-14", "Name must be a valid C identifier: start with a letter or underscore, and contain only letters, digits, or underscores."],
  ["mpu-desc-15", "Pick whether the initialization code should be generated and automatically called at startup."],
  ["mpu-desc-16", "Resource initialization code generation"],
  ["mpu-desc-17", "The index of the attribute to apply to this region."],
  ["mpu-desc-18", "The limit address must be greater than or equal to the base address, else the configuration will be ignored."],
  ["mpu-desc-19", "The system escalates to hard fault if you do not enable it."],
  ["mpu-desc-20", "The value of the next address after the limit address must be 32-byte aligned. Therefore, bits[4:0] are not used and considered to be 0x1F."],
  ["mpu-desc-21", "This attribute defines the write policy of the region."],
  ["mpu-desc-22", "This defines which types of accesses are allowed for the region."],
  ["mpu-desc-23", "This note is informational and cannot be edited."],
  ["mpu-desc-24", "This option defines the cache line allocation policy."],
  ["mpu-desc-25", "To modify this parameter, enable the corresponding region first."],
]) {
  if (must(en)) check("描述符面板说明: " + id, T(id), pack[en]);
}
// 多行 desc 必须**整串**命中，且中文要**保持原有的换行结构** ——
// 少一个换行整段就挤成一行，多一个就会错位。这两点都不是「等于自己」的同义反复。
const ML_EN = "MPU default configuration:\n\nBecause the instruction cache is enabled, the MPU must be enabled with the OTP/RO data area defined as a non-cacheable read-only region (0x08FF FE00-0x08FF FFFF range cover the full area) if the region is effectively used.";
check("多行 desc: 整串词条存在", pack[ML_EN] !== undefined, true);
check("多行 desc: 换行结构保持一致",
  pack[ML_EN] ? pack[ML_EN].split("\n").length : -1,
  ML_EN.split("\n").length);

// ---- 描述符：表达式类文案（RULES 按形状命中） ------------------------------
// 期望值**写死字面量**，不去查语言包 —— 这些译法由 dom-translate.js 的 RULES
// 决定，和语言包无关。写死才能真正断言住「形状命中后的输出长什么样」。
// 夹具里的英文是**求值之后**的样子（逐字对齐 helper 源码的输出格式）。
for (const [id, expected] of [
  ["rt-lvl", "电平 1（2.2 V）"],
  ["rt-lvl-ext", "电平 0（外部输入电压，使用 PVD_IN）"],
  ["rt-ch-int", "通道 TIM1_CH1 内部已连接"],
  ["rt-ch-comp", "互补输出通道 CH1N"],
  ["rt-ch-in", "输入通道 CH1"],
  ["rt-ch-out", "输出通道 CH1"],
  ["rt-gpio-use", "使用 ADC1_IN5 GPIO 引脚"],
  ["rt-swap", "数据交换会在加载前和处理后调整 ADC 内核的字节顺序"],
  ["rt-comp-plus", "正输入（COMP2）"],
  ["rt-comp-up", "窗口上限阈值（COMP6 输入）"],
  ["rt-comp-lo", "窗口下限阈值（COMP6 输入）"],
  ["rt-lat", "0（最高 24 MHz）"],
  ["rt-na", "ADC1_IN5 不在此封装的引脚上提供。"],
  ["rt-pulse", "脉冲（16 位值）必须介于 0 与计数器周期 = 65535 之间。"],
  ["rt-bitt", "没有与比特率 500 kbps、采样点 750\u2030、容差 1\u2030、内核时钟 80 MHz 匹配的标称位时序。请尝试其他采样点、更宽的容差或不同的时钟分频。"],
  ["rt-bitt2", "没有与比特率 2000 kbps、采样点 800\u2030、容差 5\u2030、内核时钟 80 MHz 匹配的数据阶段位时序。请尝试其他采样点、更宽的容差或不同的时钟分频。"],
  ["rt-ram", "报文 RAM 分配超出 FDCAN1 的可用 RAM（可用 2560 个字，已分配 3000 个字）。请减少 Tx/Rx FIFO、缓冲区或滤波器的数量或大小。"],
  ["rt-eid", "扩展滤波器 ID1（0x1FFFFFFF）与当前扩展 ID 掩码冲突。请更新滤波器 ID1 或更改扩展 ID 掩码。"],
]) {
  check("表达式文案: " + id, T(id), expected);
}

// ---- 描述符：标签类文案（整串词条，期望值查包 + must() 门禁） ---------------
for (const [id, en] of [
  ["lb-16bits", "16 bits"],
  ["lb-8bits", "8 bits"],
  ["lb-ws0", "0 WS"],
  ["lb-ws15", "15 WS"],
  ["lb-stop1", "1 stop bit"],
  ["lb-stop15", "1.5 stop bits"],
  ["lb-i2s16", "16-bit on 16-bit channel"],
  ["lb-i2s32", "16-bit on 32-bit channel"],
  ["lb-cmp", "Compare - oc3refc"],
  ["lb-cmpp", "Compare pulse - oc4refc rising oc6refc falling"],
  ["lb-q3", "3 quarts full"],
  ["lb-way", "1-way"],
  ["lb-hour", "12-hour"],
  ["lb-dsize", "1 x data-size"],
]) {
  if (must(en)) check("标签文案: " + id, T(id), pack[en]);
}
// 反向断言：单位 / 算法名 / ARM 属性名必须**一动不动**。
// 这批是 gen_labels.py 里写了理由的「保持英文」表，翻错了反而没法对照手册。
check("保持英文: 192 kHz", T("lb-keep-hz"), "192 kHz");
check("保持英文: AES CBC", T("lb-keep-aes"), "AES CBC");
check("保持英文: nGRE", T("lb-keep-ngre"), "nGRE");

// ---- 第二个来源：helper JS 返回的界面文案 ----------------------------------
for (const [id, en] of [
  ["hp-phy-hs", "Embedded High Speed PHY"],
  ["hp-phy-fs", "Embedded Full Speed PHY"],
  ["hp-noviol", "No violation detected."],
  ["hp-maskfail", "Extended ID mask check failed."],
  ["hp-rangestart", "The current extended ID mask suppresses the configured range start, so this range cannot be matched. Adjust the range or change the extended ID mask."],
]) {
  if (must(en)) check("helper 文案: " + id, T(id), pack[en]);
}
// 反向断言：helper 的**开发者异常**文本不该被翻译。
// 它们是 `throw new Error('...')` 的参数，只进控制台与异常栈。
// 真在界面上看到这句，说明是我们的判定错了 —— 不是「翻了更好」。
check("保持英文: helper 异常文本", T("hp-throw"), "Input must be a string");

// ---- ST 自绘 ConfirmDialog 家族（整句写死在源码里，只能靠 DOM 通道） ----------
// 这批的成因和 PWR/GPIO 不同：PWR 是**运行时数据**（源码里根本没有），
// 这批是**源码里就有、但没走框架 i18n 的裸字符串**。
// 判定依据：模块 824589 是本族组件本体，调用方 934490 / 317245 / 47293 / 100815 /
// 83578 / 8516xxx 把 title·header·message·confirmText 以字面量传进 props。
// 期望值用 pack，但先过 must() 门禁保证键真的在包里 ——
// 否则键写错时断言会退化成「期望英文」，等于没写。
const DIALOG_TERMS = [
  ["dlg-exit-title", "Exit ?"],
  ["dlg-exit-header", "Your changes will be lost"],
  ["dlg-exit-msg", "To keep your modifications, save and close."],
  ["dlg-exit-discard", "Discard changes & Exit"],
  ["dlg-exit-confirm", "Save & Exit"],
  ["dlg-ro-title", "Exit [read-only] ?"],
  ["dlg-ro-header", "Your changes will be lost (project is read-only)"],
  ["dlg-ro-msg", "To keep your modifications, save project to a new location."],
  ["dlg-rc-title", "Reset configuration"],
  ["dlg-rc-header", "Reset to default settings"],
  ["dlg-rc-msg1", "This will restore all settings to their default values."],
  ["dlg-rc-msg2", "Your current configuration will be lost."],
  ["dlg-rp-title", "Reset pins"],
  ["dlg-rp-header", "All GPIO-configured pins will be reset, and their configuration will be lost."],
  ["dlg-rp-msg", "Other configured pins will be preserved. Reserved pins will be reset."],
  ["dlg-gp-title", "Deactivate GPIO"],
  ["dlg-gp-header", "The current GPIO configuration of this pin will be lost."],
  ["dlg-gp-msg", "If you configure this pin again, all settings will be reset to their default values."],
];
for (const [id, en] of DIALOG_TERMS) {
  if (must(en)) check("弹窗文案: " + id, T(id), pack[en]);
}
// 图标按钮：文字节点在 svg 外面，必须翻到（svg 内部才是跳过区）
check("弹窗图标按钮文字被翻译", T("dlg-exit-confirm"),
  must("Save & Exit") ? pack["Save & Exit"] : "Save & Exit");
check("弹窗 Cancel 沿用已发布词条", T("dlg-exit-cancel"),
  must("Cancel") ? pack["Cancel"] : "Cancel");
// 反向断言：不在表里的整句必须一动不动（整串匹配，不做子串替换）
check("未收录的句子保持英文", T("dlg-unknown"), "This sentence is not in the dictionary at all");
check("带问号的未收录句子保持英文", T("dlg-unknown-q"), "Is this sentence in the dictionary?");

// ---- 未收录文案收集器 -------------------------------------------------------
// 运行时数据静态穷举不出来（PWR 面板就是证据：整个安装目录零命中），
// 唯一可靠的信息源是「界面上真正显示过什么」。收集器把查表失败的文案攒在本地，
// 用户在 Console 里一句 __cubemx2zhMiss() 就能拿走完整清单 —— 不用再一张张截图。
const missed = window.__cubemx2zhMiss();
check("收集器抓到未收录的 UI 文案", missed.indexOf("Totally not in the pack ZZZ") >= 0, true);
// 2026-09-19 放宽了过滤条件（原先把 ? [ ] 和省略号排除、长度只到 60、词数只到 8），
// 结果恰恰漏掉了弹窗整句。这两条断言就是那次放宽的回归测试。
check("收集器抓到问号结尾的句子", missed.indexOf("Is this sentence in the dictionary?") >= 0, true);
check("收集器抓到长句（超过 8 个词）",
  missed.indexOf("This sentence is not in the dictionary at all") >= 0, true);
check("收集器不收录已翻译的文案（GPIO）", missed.indexOf("Advanced features"), -1);
check("收集器不收录已翻译的文案（PWR）", missed.indexOf("Applicative services"), -1);
check("收集器不收录中文", missed.some((s) => /[\u4e00-\u9fff]/.test(s)), false);
check("收集器不收录纯数字/符号", missed.some((s) => !/[A-Za-z]/.test(s)), false);
const missApi = window.__cubemx2zhMiss("text");
check("收集器支持 text 导出", typeof missApi, "string");
check("收集器清空接口可用", window.__cubemx2zhMissClear(), 0);

// ---- 不该翻的地方 ---------------------------------------------------------
check("编辑器内文本不动", T("monaco-text"), "Reset pins");
check("编辑器内 placeholder 不动", doc.getElementById("monaco-input").getAttribute("placeholder"), "Sort by");
check("console/pre 内文本不动", T("console-text"), "Reset pins");
check("data-cubemx2zh-skip 生效", T("skipme"), "Reset pins");
check("拼接文本不被子串替换", T("mixed"), "Pins: 12");
check("未收录英文保持原样", T("notinpack"), "Totally not in the pack ZZZ");
check("中文键不参与替换（防替换链）", T("cjk"), "\u4e2d\u6587\u952e");
check("保留首尾空白", doc.getElementById("padded").firstChild.nodeValue,
  must("Pins") ? "   " + pack["Pins"] + "   " : "   Pins   ");

// ---- 模板串规则（Search for any X...） ------------------------------------
// 这是唯一一条规则：``Search for any ${O}...`` 是拼出来的，整串匹配够不到。
const inner = must("text") ? pack["text"] : "text";
check("模板串规则命中", doc.getElementById("pin-search").getAttribute("placeholder"),
  "\u6309" + inner + "\u641c\u7d22...");

// ---- 动态渲染（MutationObserver 通道） ------------------------------------
async function dynamic() {
  const host = doc.getElementById("dyn-host");
  const d = doc.createElement("div");
  d.innerHTML = '<button id="dyn-btn">Reset pins</button><input id="dyn-input" placeholder="Sort by" />';
  host.appendChild(d);
  await new Promise((r) => window.setTimeout(r, 60));
  check("动态插入的文本被翻译", doc.getElementById("dyn-btn").textContent,
    must("Reset pins") ? pack["Reset pins"] : "Reset pins");
  check("动态插入的 placeholder 被翻译", doc.getElementById("dyn-input").getAttribute("placeholder"),
    must("Sort by") ? pack["Sort by"] : "Sort by");

  // 动态插入一个「没有省略号」的近似串：规则是整串匹配，必须不误伤。
  // 放在动态段里才有意义 —— MutationObserver 是微任务，同步断言测不到。
  const neg = doc.createElement("div");
  neg.id = "rule-neg";
  neg.textContent = "Search for any text";
  host.appendChild(neg);
  await new Promise((r) => window.setTimeout(r, 30));
  check("模板串规则不误伤（缺省略号）", doc.getElementById("rule-neg").textContent,
    "Search for any text");

  // 幂等：再注入一次不应该报错、也不该把词条数量算两遍
  const before = JSON.parse(JSON.stringify(window.__CUBEMX2ZH_DOM__.stats));
  let secondErr = null;
  try { window.eval(block); } catch (e) { secondErr = String(e); }
  check("重复注入不报错", secondErr, null);
  check("重复注入不重复统计", JSON.stringify(window.__CUBEMX2ZH_DOM__.stats), JSON.stringify(before));

  const failed = checks.filter((c) => !c.ok);
  console.log(JSON.stringify({ diag, total: checks.length, failed }, null, 1));
}

dynamic().catch((e) => {
  checks.push({ name: "动态测试异常", ok: false, actual: String(e), expected: null });
  console.log(JSON.stringify({ diag, total: checks.length, failed: checks.filter((c) => !c.ok) }, null, 1));
});
