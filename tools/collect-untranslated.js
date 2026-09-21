/* STM32CubeMX2-Chinese · 自助收敛工具 —— 采集「页面上还没翻译的英文 UI 文案」
 *
 * 用法
 * ----
 * 启动 STM32CubeMX2 后打开 F12 Console，把本文件内容整段粘贴进去回车。
 * 它会打印出**当前这一屏**里出现的、看起来是英文 UI 文案、但**不在语言包里**的
 * 短文本（去重 + 排序）。把结果贴回来即可补词条 —— 比截图完整，也不会漏掉
 * 下拉框里同组的其它选项（这正是最容易反复漏的一类）。
 *
 * 为什么需要它
 * ------------
 * 界面上的文案有两类来源：
 *   1) 框架 i18n / 源码里的裸字符串 —— 可以扫源码收齐；
 *   2) **运行时数据**（设备/配置描述包）—— 源码树、sourcemap 里都搜不到，
 *      只能等它渲染到 DOM 上才看得见。
 * 第 2 类只能靠「在真实界面上采样」来收集，本工具就是干这个的。
 *
 * 注意事项
 * --------
 * - 只采样**当前这一屏**：Pinout、引脚配置、时钟树、各设置页各跑一次才全；
 * - 是启发式过滤（长度/字符集/是否含中文），会有少量噪音；
 * - 只读 DOM，不改任何东西，也不上传。
 *
 * 过滤条件的坑（2026-09-19 踩过）
 * ------------------------------
 * 第一版把问号、方括号、省略号排除在外，长度只到 60、词数只到 8 ——
 * 结果**恰好把弹窗里的整句文案全过滤掉了**（`Exit ?`、`Exit [read-only] ?`、
 * `Resetting…`、`To keep your modifications, save and close.`）。
 * 过滤规则越"聪明"，越容易挡掉你真正要找的东西。内嵌收集器
 * （assets/dom-translate.js 的 __cubemx2zhMiss）已按同样口径放宽。
 */
(function () {
  var pack = (window.__CUBEMX2ZH__ || {}).replacements || {};
  var out = Object.create(null);

  // 用户内容区一律跳过（与 assets/dom-translate.js 的黑名单保持一致）
  var SKIP = ".monaco-editor,.xterm,.theia-terminal,#theia-debug-console,.theia-output,[contenteditable=true]";

  var nodes = document.querySelectorAll("body *");
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (el.closest(SKIP) || el.childElementCount) continue;   // 只看叶子节点
    var t = (el.textContent || "").trim();
    // 阈值与 assets/dom-translate.js 的 missNote() **必须一致** ——
    // 两个口径一旦分叉，翻译器记下的和你在这里看到的就不是同一批文案。
    // 2026-09-19 第二次放宽：长度 120→400、词数 18→60、字符集改负向判定
    // （原因见 dom-translate.js 里 MISS_TEXT_MAX 的注释：面板 description 全被挡掉了）。
    if (t.length < 2 || t.length > 400) continue;
    if (!/[A-Za-z]/.test(t)) continue;                        // 必须含字母
    if (/[\u4e00-\u9fff]/.test(t)) continue;                  // 已经含中文，跳过
    if (!/^[\x20-\x7e]+$/.test(t)) continue;                  // 负向判定：可打印 ASCII 即收
    if (t.split(/\s+/).length > 60) continue;                 // 太长，多半是正文
    if (t in pack) continue;                                  // 已在语言包里，说明能翻
    out[t] = 1;
  }

  var list = Object.keys(out).sort();
  console.log("[STM32CubeMX2-Chinese] 本屏未收录文案 " + list.length + " 条：\n" + list.join("\n"));
  return list;
})();
