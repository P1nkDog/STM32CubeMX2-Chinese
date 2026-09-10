from __future__ import annotations

import argparse
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(__file__).resolve().parent

from core import __version__, dictionary, locate, manual_csv, process, session, update  # noqa: E402


def _print_header() -> None:
    print("=" * 48)
    print(f"  STM32CubeMX2 中文汉化工具  v{__version__}")
    print("=" * 48)


def _pick_root(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        if locate.is_install_root(p):
            return p.resolve()
        print(f"[错误] 不是有效的 CubeMX2 安装目录: {p}")
        return None
    roots = locate.find_install_roots()
    if not roots:
        print("[错误] 未找到 STM32CubeMX2 安装目录")
        print("       可用 -g <路径> 指定，或设置环境变量 STM32CUBEMX2_PATH")
        return None
    if len(roots) == 1:
        return roots[0]
    print("找到多个安装目录：")
    for i, r in enumerate(roots, 1):
        print(f"  [{i}] {r}")
    raw = input("选择序号 > ").strip()
    try:
        return roots[int(raw) - 1]
    except (ValueError, IndexError):
        return None


def _ensure_not_running() -> bool:
    if process.is_cube_running():
        print("[错误] 检测到 STM32CubeMX2 正在运行，请先完全退出再操作。")
        return False
    return True


def cmd_doctor(root: Path | None) -> None:
    print("— 安装检测 —")
    if root:
        print(f"安装目录: {root}")
        b = locate.bundle_js_path(root)
        print(f"bundle.js: {b if b else '未找到'}")
    else:
        print("未定位安装目录")
    print("— 进程 —")
    print("运行中" if process.is_cube_running() else "未运行")
    print("— 词典 —")
    try:
        d, src = dictionary.resolve_dictionary()
        files = d.get("files") or {}
        n = sum(len(v.get("entries") or []) for v in files.values())
        target = d.get("targetApp") or {}
        app_name = target.get("name") or "STM32CubeMX2"
        tested = target.get("testedVersions") or []
        notes = d.get("notes") or ""
        print(f"来源: {src}")
        print(f"工具版本: v{__version__}")
        print(f"词典版本: v{d.get('version', '?')}")
        print(f"目标软件: {app_name}")
        print(f"已验证版本: {', '.join(tested) if tested else '(未标注)'}")
        print(f"翻译条目: {n} 条")
        if notes:
            print(f"备注: {notes}")
        min_tool = d.get("minToolVersion")
        if min_tool:
            print(f"要求工具版本: >= v{min_tool}")
    except Exception as e:  # noqa: BLE001
        print(f"加载失败: {e}")
    print("— 汉化状态 —")
    from core import backup

    if root:
        st = backup.read_state(root)
        print(st if st else "未汉化（无状态文件）")
    else:
        print("(需先定位安装目录)")


def cmd_dry_run(root: Path) -> None:
    d, src = dictionary.resolve_dictionary()
    print(f"词典: {src}")
    rep = session.dry_run(root, d)
    for r in rep.results:
        flag = "OK" if r.ok else "!!"
        print(f"  [{flag}] {r.entry_id}: found={r.found} expect={r.expect} {r.message}")
    hit = sum(1 for r in rep.results if r.ok)
    print(f"可替换 {hit}/{len(rep.results)} 条（未写盘）")


def cmd_patch(root: Path) -> None:
    if not _ensure_not_running():
        return
    d, src = dictionary.resolve_dictionary()
    print(f"词典: {src}")
    print("汉化中，请稍后…")
    sys.stdout.flush()
    rep = session.apply_patch(root, d, dict_source=src)
    for r in rep.results:
        flag = "OK" if r.ok else "!!"
        print(f"  [{flag}] {r.entry_id}: replaced={r.replaced} {r.message}")
    for m in rep.messages:
        print(m)


def cmd_rollback(root: Path) -> None:
    if not _ensure_not_running():
        return
    rep = session.rollback(root)
    for m in rep.messages:
        print(m)


def cmd_update_dict() -> None:
    print("检查词典更新…")
    print(f"远程地址: {update.DEFAULT_REMOTE_URL}")
    info = update.check_dict_update()
    if info is None:
        print("[错误] 拉取远程词典失败（网络不可用 / 被墙 / 远程地址配置错误）")
        print(f"       远程地址: {update.DEFAULT_REMOTE_URL}")
        return
    rv, lv = info["remote_version"], info["local_version"]
    print(f"远程词典版本: v{rv}")
    print(f"本地词典版本: v{lv} (来源: {info['local_source']})")
    if not info["has_update"]:
        print("词典已是最新。")
        return
    print("发现新版本词典，是否下载并应用？[y/N] ", end="")
    try:
        ans = input().strip().lower()
    except EOFError:
        ans = ""
    if ans not in ("y", "yes"):
        print("已取消。")
        return
    target = update.update_dict(info["raw"])
    print(f"词典已更新: {target}")
    print("下次执行「一键汉化」时将自动优先使用新词典。")


def cmd_open_github() -> None:
    print(f"打开软件发布页: {update.RELEASES_PAGE}")
    print("请下载最新版 EXE 后替换当前程序（建议先回滚汉化再替换）。")
    if update.open_releases_page():
        print("已在默认浏览器打开。")
    else:
        print("[错误] 未能自动打开浏览器，请手动访问上面的地址。")


def cmd_export_csv(root: Path) -> None:
    print("导出中，请稍候…（扫描 bundle.js 并合并词典）")
    sys.stdout.flush()
    try:
        out, total, filled, empty = manual_csv.export_full_csv(root)
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 导出失败: {e}")
        return
    print(f"已导出: {out}")
    print(f"总行数 {total}，已填中文 {filled}，待填 {empty}")
    print("用 Excel 打开填写 zh 列后，再选「导入翻译表并更新词典」。")


def cmd_import_csv(root: Path) -> None:
    path = manual_csv.default_csv_path()
    if not path.is_file():
        print(f"[错误] 未找到 {path}")
        print("       请先执行「导出翻译表」。")
        return
    try:
        added, skipped, bad = manual_csv.import_csv_to_dict(root, path)
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 导入翻译表失败: {e}")
        return
    print(f"已导入翻译表并更新词典: 新增/更新 {added} 条，跳过 {skipped}，结构错误 {bad}")
    print(f"词典文件: {manual_csv.dict_path()}")
    print("可接着执行「一键汉化」。")


def _pause() -> None:
    try:
        input("\n按回车返回菜单…")
    except EOFError:
        pass


def advanced_menu(root: Path | None) -> None:
    while True:
        print()
        print("— 高级 —")
        print("1) 预览替换（不写盘）")
        print("2) 导出翻译表（含词典已有中文）")
        print("3) 导入翻译表并更新词典")
        print("0) 返回主菜单")
        choice = input("> ").strip()
        if choice == "0":
            return
        if choice == "1":
            if root is None:
                root = _pick_root(None)
            if root:
                cmd_dry_run(root)
            _pause()
            continue
        if choice == "2":
            if root is None:
                root = _pick_root(None)
            if root:
                cmd_export_csv(root)
            _pause()
            continue
        if choice == "3":
            if root is None:
                root = _pick_root(None)
            if root:
                cmd_import_csv(root)
            _pause()
            continue
        print("无效选项")


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
        choice = input("> ").strip()
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
            advanced_menu(root)
            continue
        print("无效选项")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="STM32CubeMX2-Chinese",
        description="STM32CubeMX2 界面中文汉化 / 回滚工具",
    )
    p.add_argument("-g", "--path", help="CubeMX2 安装根目录")
    p.add_argument("--rollback", action="store_true", help="从 .orig 备份回滚")
    p.add_argument("--dry-run", action="store_true", help="只统计命中，不写盘")
    p.add_argument("--doctor", action="store_true", help="体检安装/进程/词典")
    p.add_argument("--check-update", action="store_true", help="检查并更新词典（兼容旧参数，等价 --update-dict）")
    p.add_argument("--update-dict", action="store_true", help="从 GitHub 拉取最新词典并应用")
    p.add_argument("--open-github", action="store_true", help="用默认浏览器打开 GitHub Releases 发布页（软件更新）")
    p.add_argument("--patch", action="store_true", help="执行汉化（无菜单）")
    p.add_argument("--export-csv", action="store_true", help="导出翻译表")
    p.add_argument("--import-csv", action="store_true", help="导入翻译表并更新词典")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    need_root = any(
        [
            args.path,
            args.doctor,
            args.dry_run,
            args.patch,
            args.rollback,
            args.export_csv,
            args.import_csv,
        ]
    )
    root = _pick_root(args.path) if need_root else None
    if args.path and root is None:
        return 1

    if args.doctor:
        cmd_doctor(root)
        return 0
    if args.update_dict or args.check_update:
        cmd_update_dict()
        return 0
    if args.open_github:
        cmd_open_github()
        return 0
    if args.dry_run:
        if root is None:
            root = _pick_root(None)
        if root:
            cmd_dry_run(root)
            return 0
        return 1
    if args.export_csv:
        if root is None:
            root = _pick_root(None)
        if root:
            cmd_export_csv(root)
            return 0
        return 1
    if args.import_csv:
        if root is None:
            root = _pick_root(None)
        if root:
            cmd_import_csv(root)
            return 0
        return 1
    if args.patch:
        if root is None:
            root = _pick_root(None)
        if root:
            cmd_patch(root)
            return 0
        return 1
    if args.rollback:
        if root is None:
            root = _pick_root(None)
        if root:
            cmd_rollback(root)
            return 0
        return 1

    return interactive_menu(root)


if __name__ == "__main__":
    sys.exit(main())
