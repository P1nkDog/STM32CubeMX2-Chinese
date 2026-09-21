from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(__file__).resolve().parent

from core import (  # noqa: E402
    __version__,
    dictionary,
    glossary,
    i18n,
    langpack,
    locate,
    paths,
    process,
    session,
    update,
)

# 控制台直连时 Windows 走 WriteConsoleW，中文跟代码页无关；但输出被重定向到
# 文件或管道时（`> log.txt`、被脚本调用）改用系统 ANSI 代码页编码，英文系统
# 是 cp1252 —— 第一句中文就抛 UnicodeEncodeError，用户看到的是一段 traceback。
# errors="replace" 兜底：最坏是丢字形，不是崩。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _print_header() -> None:
    print("=" * 60)
    print(f"  STM32CubeMX2 中文汉化工具  v{__version__}")
    print("=" * 60)


def _ask(prompt: str = "> ") -> str | None:
    """读一行输入并去首尾空白；输入流结束时返回 ``None``。

    单独抽出来是因为 EXE 经常被非交互方式启动（管道喂脚本、重定向、
    双击后 Ctrl+Z）：直接写 ``input()`` 会抛 ``EOFError``，用户看到的是一堆
    Python 内部 traceback，而不是一句「输入已结束」。调用方拿到 ``None``
    各自决定是退出、放弃还是回主菜单。
    """
    try:
        return input(prompt).strip()
    except EOFError:
        return None


def _confirm_root(r: locate.Resolved) -> bool:
    """向下搜出来的目录并不是用户指的那一个，必须让他点头才能动手。

    这是唯一有实际危害的失误面：认错根 = 往别的程序里写文件。
    """
    print(f"  你给的路径本身不是安装目录，但在它下面找到了：{r.root}")
    for extra in r.alternates:
        print(f"  另外还找到：{extra}")
    if r.truncated:
        print("  （搜索达到目录数上限，可能没搜完）")
    ans = _ask("  用这个目录吗？[y/N] ")
    if ans is None:
        print("  没有交互输入可用。请用 -g 指定安装目录后重试。")
        return False
    return ans.lower() in ("y", "yes")


def _ask_for_root() -> Path | None:
    """保底：自动扫描失败时，请用户把安装目录打进来。

    这里才允许向下搜（``allow_down=True``）—— 自动扫描阶段不许乱翻盘。
    """
    print()
    print(locate.diagnose_missing().brief())
    print()
    print("找到自己的安装目录：")
    print("  右键桌面或开始菜单里的 STM32CubeMX2 快捷方式 →「打开文件所在的位置」，")
    print("  资源管理器地址栏里那个目录就是，把它粘到下面即可。")
    print("  从「任务管理器 → 打开文件所在的位置」进来会停在 dist 那一层，")
    print("  那种也可以，工具会自己往上找到根。")
    print("  留空直接回车放弃。")
    while True:
        raw = _ask("安装目录 > ")
        if raw is None:
            print("没有交互输入可用，已放弃。")
            return None
        if not raw:
            return None
        r = locate.resolve_root(raw, allow_down=True)
        if not r.ok:
            print(f"  「{raw}」本身、它的上层、以及它下面三层里都没有可注入的安装目录。")
            continue
        if r.needs_confirm and not _confirm_root(r):
            continue
        if locate.remember_root(r.root):
            print(f"  已记住：{r.root}")
            print(f"  （要改或想重新扫描，删掉 {paths.config_path()} 就行）")
        return r.root


def _pick_root(explicit: str | None) -> Path | None:
    """定安装目录：命令行 > 上次确认的 > 自动扫描 > 问用户。

    四条路都过同一个 ``resolve_root``，所以「指到 dist 那一层」「路径带引号」
    「注册表写的是 exe 的位置」这类错位在任何一条路上都能被纠正。
    """
    if explicit:
        r = locate.resolve_root(explicit, allow_down=True)
        if not r.ok:
            print(f"[错误] 不是有效的 CubeMX2 安装目录: {explicit}")
            print("       试过它本身、它的上层目录，以及它下面最多三层。")
            return None
        if r.needs_confirm and not _confirm_root(r):
            return None
        locate.remember_root(r.root)
        return r.root

    roots = locate.find_install_roots()
    remembered = locate.remembered_root()
    if remembered and (not roots or remembered in roots):
        print(f"安装目录（上次确认的）: {remembered}")
        return remembered
    if not roots:
        return _ask_for_root()
    if len(roots) == 1:
        return roots[0]
    print("找到多个安装目录：")
    for i, r in enumerate(roots, 1):
        print(f"  [{i}] {r}")
    raw = _ask("选择序号 > ")
    if raw is None:
        return None
    try:
        picked = roots[int(raw) - 1]
    except (ValueError, IndexError):
        return None
    locate.remember_root(picked)
    return picked


def _ensure_not_running() -> bool:
    if process.is_cube_running():
        print("[错误] 检测到 STM32CubeMX2 正在运行，请先完全退出再操作。")
        return False
    return True


# ---------------------------------------------------------------------------
# 词典 -> 语言包
# ---------------------------------------------------------------------------


def _load_pack() -> tuple[dict[str, str], str]:
    """从当前生效的词典现场构建语言包。

    不再有「落盘的语言包」这一层。以前 `--patch` 会优先读 `dict/nls.zh-cn.json`，
    于是「改了词典却忘了跑 `--build-langpack`」就会**静默注入旧表** —— 界面上
    一个字都不变，而且不报错。现在词典是唯一事实来源，每次汉化现场构建。
    """
    return dictionary.current_pack()


def _work_dict_path() -> Path:
    """工作副本词典路径（开发态 = 仓库根，EXE 模式 = EXE 旁）。"""
    return paths.user_dict_path()


def _repo_dict_path() -> Path:
    """仓库里那份要提交的词典。"""
    return paths.bundled_dict_path()


def cmd_export_dict() -> int:
    """导出当前生效的词典到工作副本，供手工编辑。"""
    try:
        d, src = dictionary.resolve_dictionary()
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 读词典失败: {e}")
        return 1
    if not dictionary.is_current_format(d):
        print(f"[错误] 词典 {src} 不是扁平 entries 格式，无法导出")
        return 1
    out = _work_dict_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    print(f"已导出: {out}")
    print(f"来源: {src}（{len(d['entries'])} 条）")
    print("直接编辑这个文件的 entries，改完执行「一键汉化」就会生效 ——")
    print("resolve_dictionary() 优先读工作副本，不需要额外的导入步骤。")
    print("要把成果固化回仓库（好提交 PR），改完再执行 --import-dict。")
    return 0


def cmd_import_dict() -> int:
    """把工作副本词典导回仓库的 dict/localization.json（源码模式、提交前用）。"""
    if paths.is_frozen():
        print("EXE 模式下**不需要**这一步。")
        print("  你编辑的那份工作副本本来就被优先读取 —— 改完直接选「一键汉化」就生效了。")
        print("  「导入」只服务于一种场景：把改好的词典固化进仓库的 dict/，好提交 PR。")
        print("  那需要源码环境（EXE 的内置词典在临时解压目录里，写回去随进程退出就没了）。")
        return 0
    src = _work_dict_path()
    if not src.is_file():
        print(f"[错误] 未找到工作副本 {src}，先执行 --export-dict")
        return 1
    try:
        d = dictionary.load_json_file(src)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[错误] 读 {src} 失败: {e}")
        return 1
    if not dictionary.is_current_format(d):
        print(f"[错误] {src} 缺少扁平 entries 表，拒绝导入")
        return 1

    pack, _ = dictionary.current_pack()
    print("— 术语门禁（对齐 ST 官方中文文档）—")
    if _check_glossary(d["entries"]) != 0:
        print("[中止] 术语门禁未通过，工作副本没有导回仓库。")
        print("       修 rules/glossary.zh.json 或对应词条后重试。")
        return 1

    target = _repo_dict_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    print(f"已导入: {src} -> {target}")
    print(f"词典条目 {len(d['entries'])} 条 -> 注入语言包 {len(pack)} 条")
    print("提示: 工作副本仍会优先于仓库词典被读取；提交前确认两份内容一致。")
    return 0


# ---------------------------------------------------------------------------
# 体检 / 预览 / 评估
# ---------------------------------------------------------------------------


def cmd_doctor(root: Path | None, verbose: bool = False) -> None:
    print("— 安装检测 —")
    if root:
        print(f"安装目录: {root}")
        a = locate.app_dir(root)
        print(f"app 目录: {a if a else '未找到'}")
        if a:
            for name in (
                "lib/frontend/bundle.js",
                "lib/frontend/secondary-window.js",
                "lib/backend/main.js",
            ):
                p = a / name
                print(f"{name}: {'存在' if p.is_file() else '未找到'}")
    else:
        print("未定位安装目录")
    remembered = locate.remembered_root()
    if remembered and remembered != root:
        print(f"配置文件里另记着一个安装目录: {remembered}")
        print(f"  （{paths.config_path()}；删掉它就把记忆清掉）")
    print("— 进程 —")
    print("运行中" if process.is_cube_running() else "未运行")
    print("— 落盘前语法门禁 —")
    node = i18n.find_node()
    if node:
        print(f"可用: {node}")
    else:
        print("不可用（未找到 Node.js）—— 汉化照常进行，只是少一道落盘前的保险")
        print("               想补上：装 Node.js，或设 CUBEMX2ZH_NODE 指向 node.exe")
    print("— 词典 —")
    try:
        d, src = dictionary.resolve_dictionary()
        target = d.get("targetApp") or {}
        app_name = target.get("name") or "STM32CubeMX2"
        tested = target.get("testedVersions") or []
        print(f"来源: {src}")
        print(f"工具版本: v{__version__}")
        print(f"词典版本: v{d.get('version', '?')}")
        print(f"目标软件: {app_name}")
        print(f"已验证版本: {', '.join(tested) if tested else '(未标注)'}")
        pack, _ = _load_pack()
        st = langpack.stats(pack)
        print(f"词典条目: {len(d.get('entries') or {})} 条")
        print(f"注入语言包: {st['count']} 条（{st['bytes'] / 1024:.1f} KB）")
        if verbose:
            print(
                f"源串平均长度 {st['avg_src_len']}，最长 {st['max_src_len']}，"
                f"含占位符 {st['placeholders']} 条"
            )
    except Exception as e:  # noqa: BLE001
        print(f"加载失败: {e}")
    print("— 汉化状态 —")
    from core import backup

    if root:
        st = backup.read_state(root)
        if st:
            for k, v in st.items():
                print(f"  {k}: {v}")
        else:
            print("未汉化（无状态文件）")
    else:
        print("(需先定位安装目录)")


def cmd_probe(root: Path) -> int:
    """锚点探测：检查注入点在当前安装包上是否都能唯一命中。"""
    a = locate.app_dir(root)
    if not a:
        print("[错误] 未找到 app 目录")
        return 1
    print(f"app 目录: {a}")
    print()
    all_ok = True
    for p in i18n.probe(a):
        flag = "OK" if p.ok else "!!"
        print(f"[{flag}] {p.rel}")
        if not p.exists:
            print("      文件不存在")
            all_ok = False
            continue
        print(f"      大小 {p.size:,} 字节，{'已注入' if p.injected else '未注入'}")
        print(f"      锚点命中: {p.hits}")
        for x in p.notes:
            print(f"      [提示] {x}")
        for x in p.problems:
            print(f"      [问题] {x}")
            all_ok = False
    print()
    print(
        "结论:",
        "全部锚点唯一命中，可安全注入"
        if all_ok
        else "存在问题，注入会被拒绝",
    )
    return 0 if all_ok else 1


def cmd_coverage(root: Path, show_missing: int = 30) -> int:
    a = locate.app_dir(root)
    if not a:
        print("[错误] 未找到 app 目录")
        return 1
    pack, src = _load_pack()
    print(f"语言包: {src}")
    cov = i18n.coverage(a, pack)
    print()
    print(cov.brief())
    if show_missing:
        print()
        print(
            f"未覆盖文案 Top {show_missing}"
            "（数字 = 出现过它的目标文件数 1-10，不是字节级出现次数；"
            "同数按文本升序，保证每次跑输出一致）:"
        )
        for lit, n in i18n.missing_report(
            a, pack, frozenset(glossary.keep_english_words())
        )[:show_missing]:
            text = lit if len(lit) <= 78 else lit[:75] + "..."
            print(f"  {n:>3}x  {text}")
    return 0


# ---------------------------------------------------------------------------
# 汉化 / 回滚
# ---------------------------------------------------------------------------


def _check_glossary(pack: dict[str, str], verbose: bool = False) -> int:
    """术语门禁：译法必须与 rules/glossary.zh.json 一致（对齐 ST 官方中文文档）。

    这条门禁存在的意义：把「所有翻译都要和 ST 官方中文文档对齐」从一个口头约定
    变成**落盘前的硬门槛**。早先那种凭语感翻出来的译法（速度档位一度译成
    「低/中/高/非常高」）如果没有门禁，只会在用户看见界面时才被发现。

    **全过时一行都不打**：门禁是保险，不是给用户看的日报 —— 它一开口就说明
    有东西要人处理。要确认它真跑过，加 `-v`。
    """
    rep = glossary.run(pack)
    if rep is None:
        print("  WARN 未找到 rules/glossary.zh.json —— 跳过术语门禁")
        return 0
    if rep.ok and not rep.warns and not verbose:
        return 0
    print("— 术语门禁（对齐 ST 官方中文文档）—")
    print(rep.brief())
    return 0 if rep.ok else 1


def _warn_dict_drift() -> None:
    """工作副本与仓库词典不一致时提醒。

    `resolve_dictionary()` 优先读工作副本（EXE 旁 / 仓库根那份 localization.json），
    所以「改了工作副本、汉化验证通过、却忘了 --import-dict 固化回 dict/」会
    让改动只留在本机 —— 提交出去的词典还是旧的。这一步就是为了不让它静默发生。
    """
    work, repo = _work_dict_path(), _repo_dict_path()
    if paths.is_frozen():
        # EXE 模式下没有「仓库」可提交，工作副本就是用户的词典本身，不存在漂移
        return
    if not work.is_file() or not repo.is_file():
        return
    if work.resolve() == repo.resolve():
        return
    if work.read_bytes() == repo.read_bytes():
        return
    print(
        f"[提醒] 工作副本 {work} 与仓库词典 {repo} 内容不同，"
        "本次汉化用的是工作副本。"
    )
    print("       验证通过后记得执行 --import-dict 把它固化回仓库，否则提交不上去。")


def dict_menu() -> None:
    while True:
        print()
        print("— 高级 —")
        print("1) 导出词典")
        print("2) 导入修改后的词典")
        print("0) 返回主菜单")
        choice = _ask()
        if choice is None:  # 输入流结束：当作返回主菜单，别把 traceback 甩给用户
            print()
            print("输入已结束，返回主菜单。")
            return
        if choice == "0":
            return
        if choice == "1":
            cmd_export_dict()
            _pause()
            continue
        if choice == "2":
            cmd_import_dict()
            _pause()
            continue
        print("无效选项")


def cmd_patch(root: Path, verbose: bool = False) -> int:
    if not _ensure_not_running():
        return 1
    pack, src = _load_pack()
    print(f"语言包: {src}（{len(pack)} 条）")
    _warn_dict_drift()
    if _check_glossary(pack, verbose) != 0:
        print("[中止] 术语门禁未通过 —— 有译法与 ST 官方中文用词不一致（明细见上）。")
        print("       请修 rules/glossary.zh.json 或 dict/localization.json 里的对应词条，")
        print("       改完直接重跑 --patch 即可（语言包每次汉化现场构建，无需单独重建）。")
        return 1

    print("汉化中，请稍后…")
    sys.stdout.flush()
    rep = session.apply_i18n_patch(root, pack, dict_source=src)
    # 缩进行是锚点明细（每个文件 2-4 条，重复 24 遍），默认收起来；
    # 排查「应用升级后哪条锚点失配」时才需要 -v 摊开看。
    for m in rep.messages:
        if verbose or not m.startswith("  "):
            print(m)
    if rep.problems:
        print("— 问题 —")
        for x in rep.problems:
            print(f"  !! {x}")
    # 降级告示走普通一行，不进「— 问题 —」：没装 Node.js 的机器是多数，
    # 顶个 !! 会让人以为这次汉化出了问题。
    for n in rep.notes:
        print(f"提示: {n}")
        if verbose:
            print("      要用非标准位置的 node，设环境变量 CUBEMX2ZH_NODE（优先级最高）。")
    print()
    print("结果:", "汉化完成" if rep.ok else "未完成")
    if rep.ok:
        print("如需还原: 执行「一键回滚」。")
    return 0 if rep.ok else 1


def cmd_rollback(root: Path) -> int:
    if not _ensure_not_running():
        return 1
    rep = session.rollback_i18n(root)
    for m in rep.messages:
        print(m)
    return 0 if rep.ok else 1


def cmd_update_dict() -> int:
    """检查并（经确认后）应用远程词典。返回进程退出码。

    失败必须反映到退出码上：以前无论拉没拉到都返回 0，脚本里
    ``main.py --check-update && ...`` 会把「根本没检查成」当成「已是最新」。
    """
    print("检查词典更新…")
    print(f"远程地址: {update.DEFAULT_REMOTE_URL}")
    info, err = update.check_dict_update()
    if info is None:
        print(f"[错误] {err}")
        print(f"       远程地址: {update.DEFAULT_REMOTE_URL}")
        return 1
    rv, lv = info["remote_version"], info["local_version"]
    print(f"远程词典版本: v{rv}")
    print(f"本地词典版本: v{lv} (来源: {info['local_source']})")
    if not info["has_update"]:
        print("词典已是最新。")
        return 0
    # 工作副本的优先级高于随包词典，所以「更新」是整份覆盖，不是合并。
    # 放在 [y/N] 之前，看到提示还能选 N。
    work = _work_dict_path()
    if work.is_file():
        print(f"注意: 应用新词典会整份覆盖 {work}")
        print("      你在里面手改过的译法会一并丢失，请先自行备份。")
    ans = (_ask("发现新版本词典，是否下载并应用？[y/N] ") or "").lower()
    if ans not in ("y", "yes"):
        print("已取消。")
        return 0
    target = update.update_dict(info["raw"])
    print(f"词典已更新: {target}")
    print("下次执行「一键汉化」就会用上新词典 —— 语言包每次汉化现场构建，没有单独的构建步骤。")
    return 0


def cmd_open_github() -> None:
    print(f"打开软件发布页: {update.RELEASES_PAGE}")
    print("请下载最新版 EXE 后替换当前程序（建议先回滚汉化再替换）。")
    if update.open_releases_page():
        print("已在默认浏览器打开。")
    else:
        print("[错误] 未能自动打开浏览器，请手动访问上面的地址。")


def _pause() -> None:
    _ask("\n按回车返回菜单…")


def interactive_menu(root: Path | None) -> int:
    _print_header()
    while True:
        print()
        print("1) 环境/安装检查")
        print("2) 一键汉化")
        print("3) 一键回滚")
        print("4) 词典更新")
        print("5) 软件更新")
        print("6) 高级")
        print("0) 退出")
        choice = _ask()
        if choice is None:  # 管道喂完 / Ctrl+Z：干净退出，不甩 traceback
            print()
            print("输入已结束，退出。")
            return 0
        if choice == "0":
            print("已退出。")
            return 0
        if choice == "1":
            if root is None:
                root = _pick_root(None)
            cmd_doctor(root)
            _pause()
            continue
        if choice == "2":
            if root is None:
                root = _pick_root(None)
            if root:
                cmd_patch(root)
            _pause()
            continue
        if choice == "3":
            if root is None:
                root = _pick_root(None)
            if root:
                cmd_rollback(root)
            _pause()
            continue
        if choice == "4":
            cmd_update_dict()
            _pause()
            continue
        if choice == "5":
            cmd_open_github()
            _pause()
            continue
        if choice == "6":
            dict_menu()
            continue
        print("无效选项")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="STM32CubeMX2-Chinese",
        description="STM32CubeMX2 界面中文汉化 / 回滚工具（i18n 注入 + DOM 兜底）",
    )
    p.add_argument(
        "-g",
        "--path",
        help="CubeMX2 安装目录（指到 dist/app 那一层也行）",
    )
    p.add_argument("--patch", action="store_true", help="执行汉化（无菜单）")
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="打出细节：锚点命中明细、术语门禁通过项、源串长度统计",
    )
    p.add_argument("--rollback", action="store_true", help="从 .orig 备份回滚")
    p.add_argument("--probe", action="store_true", help="i18n 注入点锚点自检")
    p.add_argument("--coverage", action="store_true", help="评估覆盖率并列出未覆盖文案")
    p.add_argument("--export-dict", action="store_true", help="导出词典到工作副本，供手工编辑")
    p.add_argument("--import-dict", action="store_true", help="把工作副本词典导回仓库 dict/")
    p.add_argument("--doctor", action="store_true", help="体检安装/进程/词典/汉化状态")
    p.add_argument(
        "--check-update",
        action="store_true",
        help="检查并更新词典（兼容旧参数，等价 --update-dict）",
    )
    p.add_argument("--update-dict", action="store_true", help="从 GitHub 拉取最新词典并应用")
    p.add_argument(
        "--open-github",
        action="store_true",
        help="用默认浏览器打开 GitHub Releases 发布页（软件更新）",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.export_dict:
        return cmd_export_dict()
    if args.import_dict:
        return cmd_import_dict()
    if args.doctor:
        cmd_doctor(_pick_root(args.path), args.verbose)
        return 0
    if args.update_dict or args.check_update:
        return cmd_update_dict()
    if args.open_github:
        cmd_open_github()
        return 0

    need_root = any(
        [
            args.path,
            args.patch,
            args.rollback,
            args.probe,
            args.coverage,
        ]
    )
    root = _pick_root(args.path) if need_root else None
    if args.path and root is None:
        return 1

    if args.probe:
        return cmd_probe(root) if root else 1
    if args.coverage:
        return cmd_coverage(root) if root else 1
    if args.patch:
        return cmd_patch(root, args.verbose) if root else 1
    if args.rollback:
        return cmd_rollback(root) if root else 1

    return interactive_menu(root)


if __name__ == "__main__":
    sys.exit(main())
