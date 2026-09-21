"""词典更新链路与命令入口的离线测试：不联网，也能把那条坏掉的路跑通。

    python tools/test_update.py

除 ``core/update.py`` 之外，这里还钉住 ``main.py`` 这个入口的两件事：
退出码要如实反映「检查成没成」，以及输入流结束时菜单要干净退出。

为什么非有这份不可：v0.2.0 的「词典更新」在整个发布周期里都是坏的，而且坏得
看不出来 —— ``validate_dictionary()`` 查的是 v0.1.0 的
``files[<bundle>].entries[]`` 字节片段结构，对**仓库自己那份扁平词典**恒返回
False，于是无论网络通不通都失败，还把原因报成「网络不可用 / 被墙」。
没有任何一条断言碰过这条链，所以它绿了几个月。

这里最要紧的是第 1 组那条回归断言：**校验器必须认得我们自己发出去的那份词典**。
"""
from __future__ import annotations

import builtins
import contextlib
import io
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):  # 英文系统下控制台可能是 GBK
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core import dictionary, paths, update  # noqa: E402

PASSED = 0
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASSED
    if cond:
        PASSED += 1
    else:
        FAILED.append(f"{name}{('：' + detail) if detail else ''}")
        print(f"  [FAIL] {name}{('：' + detail) if detail else ''}")


# 旧版字节片段词典的骨架：v0.1.0 时代长这样，现在必须被拒
OLD_FORMAT = {
    "version": "0.1.0",
    "files": {"lib/frontend/bundle.js": {"entries": [{"en": "Cancel", "zh": "取消"}]}},
}


def cases(tmp: Path) -> None:
    # --- 1. 校验器认得我们自己发出去的那份词典（回归）----------------------
    real = dictionary.load_json_file(dictionary.bundled_dict_path())
    check(
        "仓库自己那份词典必须过 validate_dictionary（这条以前恒 False）",
        update.validate_dictionary(real) is True,
        f"顶层键={sorted(real)[:5]}",
    )
    check(
        "同一份词典也过 is_current_format（两处判据必须是同一个）",
        dictionary.is_current_format(real) is True,
    )

    # 对照组：把旧判据原样重跑一遍。没有它，上面那条「通过」可能只是断言写空了。
    old_files = real.get("files")
    old_cfg = old_files.get("lib/frontend/bundle.js") if isinstance(old_files, dict) else None
    old_verdict = bool(isinstance(old_cfg, dict) and isinstance(old_cfg.get("entries"), list) and old_cfg["entries"])
    check(
        "对照组：旧判据对同一份词典判 False（证明上面两条不是空转）",
        old_verdict is False,
    )

    # --- 2. 该拒的拒得干净，且不抛 ------------------------------------------
    for name, bad in [
        ("旧版 files 片段格式", OLD_FORMAT),
        ("扁平但没有 version", {"entries": {"Cancel": "取消"}}),
        ("version 是空串", {"version": "  ", "entries": {"Cancel": "取消"}}),
        ("entries 为空表", {"version": "0.2.0", "entries": {}}),
        ("entries 不是映射", {"version": "0.2.0", "entries": []}),
        ("只有 version", {"version": "0.2.0"}),
        ("None", None),
        ("字符串", "Cancel=取消"),
        ("列表", [{"version": "0.2.0"}]),
    ]:
        try:
            ok = update.validate_dictionary(bad)
        except Exception as e:  # noqa: BLE001
            check(f"门禁：{name} 判 False 且不抛异常", False, f"抛了 {type(e).__name__}: {e}")
            continue
        check(f"门禁：{name} 判 False", ok is False, "竟判 True")

    # --- 3. 版本比较 --------------------------------------------------------
    for remote, local, want in [
        ("0.2.0", "0.1.9", True),
        ("0.2.0", "0.2.0", False),
        ("v0.2.1", "0.2.0", True),
        ("0.10.0", "0.9.0", True),
        ("", "0.2.0", False),
        ("乱码", "0.2.0", False),
    ]:
        got = update.is_newer(remote, local)
        check(f"版本比较 {remote!r} > {local!r} == {want}", got is want, f"得到 {got}")

    # --- 4. check_dict_update 的三种结局（离线，fetch 被打桩）---------------
    real_fetch = update.fetch_remote
    try:
        update.fetch_remote = lambda *a, **kw: json.loads(json.dumps(real))
        info, err = update.check_dict_update()
        check("成功路径：拿到结果且错误为空", info is not None and err == "", err)
        if info:
            check("成功路径：远程版本读到了真实值", info["remote_version"] == real["version"])
            check("成功路径：本地来源有值", bool(info["local_source"]))
            check("成功路径：has_update 是布尔", isinstance(info["has_update"], bool))
            check("成功路径：raw 原样带回", info["raw"].get("entries"))

        update.fetch_remote = lambda *a, **kw: json.loads(json.dumps(OLD_FORMAT))
        info, err = update.check_dict_update()
        check(
            "门禁：拉到旧格式要说成「格式不对」，不能推给网络",
            info is None and "格式" in err and "网络" not in err,
            err,
        )

        def boom(*a, **kw):
            raise urllib.error.URLError("模拟断网")

        update.fetch_remote = boom
        info, err = update.check_dict_update()
        check(
            "门禁：真断网要说成「拉取失败」，并带上原因",
            info is None and err.startswith("拉取失败") and "模拟断网" in err,
            err,
        )
    finally:
        update.fetch_remote = real_fetch

    # --- 5. update_dict 落盘往返（写到临时目录，不碰真用户目录）-------------
    real_user_dict = paths.user_dict_path
    target = tmp / "localization.json"
    paths.user_dict_path = lambda: target
    try:
        got = update.update_dict({"version": "9.9.9", "entries": {"Cancel": "取消"}})
        check("写到了用户词典位置", got == target and target.is_file(), str(got))
        back = dictionary.load_json_file(target)
        check("写进去的读回来仍是可用词典", update.validate_dictionary(back))
        check("不留 .tmp 残文件", not list(tmp.glob("*.tmp")), str(list(tmp.iterdir())))
        check(
            "用户词典一旦存在就优先于内置（这正是 --update-dict 生效的机制）",
            dictionary.resolve_dictionary()[1].startswith("user:"),
            dictionary.resolve_dictionary()[1],
        )
    finally:
        paths.user_dict_path = real_user_dict
        target.unlink(missing_ok=True)

    # --- 6. 报错文案不许再指向已删除的步骤 ----------------------------------
    # 只查**面向用户的措辞**：`_load_pack` 的 docstring 里合法地记着
    # 「以前忘了跑 --build-langpack 会静默注入旧表」这段历史，所以不能拿
    # 全文子串一刀切 —— 那会把解释来路的注释也判成罪证。
    src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    check(
        "main.py 不再让用户去执行已删除的「构建语言包」步骤",
        "「构建语言包」" not in src and "建议接着执行" not in src,
    )

    # --- 7. 退出码：没检查成不能算检查成功 ----------------------------------
    import main as tool

    try:
        def boom(*a, **kw):
            raise urllib.error.URLError("模拟断网")

        update.fetch_remote = boom
        with contextlib.redirect_stdout(io.StringIO()):
            rc_fail = tool.main(["--check-update"])
        update.fetch_remote = lambda *a, **kw: json.loads(json.dumps(real))
        with contextlib.redirect_stdout(io.StringIO()):
            rc_ok = tool.main(["--check-update"])
        check(
            "拉取失败时退出码非 0（否则脚本会把「没检查成」当成「已是最新」）",
            rc_fail != 0,
            f"{rc_fail}",
        )
        check("检查成功时退出码为 0", rc_ok == 0, f"{rc_ok}")
    finally:
        update.fetch_remote = real_fetch

    # --- 8. 输入流结束时干净退出，不甩 traceback -----------------------------
    # 以前 `interactive_menu` / `dict_menu` 用的是裸 input()：管道喂完就抛
    # EOFError。拿未修的那份跑 `printf "6\n" | python main.py` 能复现裸 traceback。
    def eof_input(prompt="", *a, **kw):
        raise EOFError

    real_input = builtins.input
    builtins.input = eof_input
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rc_menu = tool.interactive_menu(tmp)  # 传个真存在的目录，别去扫注册表
            rc_dict = tool.dict_menu()
        check("输入流结束时主菜单干净退出（返回 0，不抛）", rc_menu == 0, f"{rc_menu}")
        check("输入流结束时高级菜单直接返回而不是一路抛到主循环", rc_dict is None)
    except EOFError:
        check("输入流结束时主菜单干净退出（返回 0，不抛）", False, "抛了 EOFError")
    finally:
        builtins.input = real_input

    # --- 9. 更新前要提示「会整份盖掉工作副本」--------------------------------
    # 接第 5 组：用户词典一存在就优先于内置那份，所以「更新」是覆盖而不是合并
    # —— 手改过的译法会被远程那份整个抹掉。提示必须排在 [y/N] 之前，
    # 用户看到还有机会选 N。
    work = tmp / "work-dict.json"
    real_work_path = tool._work_dict_path
    real_check_update = update.check_dict_update
    real_input_9 = builtins.input
    tool._work_dict_path = lambda: work
    update.check_dict_update = lambda: (
        {
            "remote_version": "9.9.9",
            "local_version": real["version"],
            "has_update": True,
            "local_source": "bundled",
            "raw": {"version": "9.9.9", "entries": {"Cancel": "取消"}},
        },
        "",
    )

    def run_update(answer: str) -> str:
        # 打桩要把提示词原样吐回去：`_ask` 是靠 `input(prompt)` 显示 `[y/N]` 的，
        # 吞掉它就等于把待验证的那一行从输出里删掉，顺序断言会空转。
        def fake_input(prompt="", *a, **kw):
            print(prompt, end="")
            return answer

        builtins.input = fake_input
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            tool.cmd_update_dict()
        return buf.getvalue()

    try:
        work.unlink(missing_ok=True)
        out_new = run_update("n")
        check(
            "工作副本还不存在时不多嘴（干净安装不该看到备份提示）",
            "整份覆盖" not in out_new,
            out_new,
        )

        work.write_text(
            json.dumps({"version": "0.0.1", "entries": {"Ok": "好"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        before = work.read_text(encoding="utf-8")

        out_has = run_update("n")
        check(
            "工作副本已存在时说要「整份覆盖」，并点名是哪份文件",
            "整份覆盖" in out_has and str(work) in out_has,
            out_has,
        )
        check("提示里给了备份这句话", "备份" in out_has, out_has)
        check(
            "门禁：提示排在 [y/N] 之前（看到提示还能放弃）",
            "整份覆盖" in out_has
            and "[y/N]" in out_has
            and out_has.index("整份覆盖") < out_has.index("[y/N]"),
            out_has,
        )
        check("选 N 之后工作副本一个字节都没变", work.read_text(encoding="utf-8") == before)
    finally:
        tool._work_dict_path = real_work_path
        update.check_dict_update = real_check_update
        builtins.input = real_input_9
        work.unlink(missing_ok=True)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cubemx2zh-update-test-"))
    try:
        cases(tmp)
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项 / 通过 {PASSED} 项")
        for f in FAILED:
            print("  -", f)
        return 1
    print(f"结论: 通过（{PASSED} 项断言）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
