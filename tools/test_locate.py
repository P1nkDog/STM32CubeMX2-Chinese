"""core/locate.py 路径归一化的离线测试：不碰真实安装目录，全在临时目录里搭假布局。

    python tools/test_locate.py

为什么值得单独写一份：安装目录定位是「改文件之前唯一那道门」。它认错目录的
后果不是报错，而是**把中文注入到别的程序里去**。所以这里除了断言「对的输入能
归一到根」，更要紧的是断言三道门禁**会拦**：

  · ``allow_down=False`` 时向下搜绝不发生（自动扫描阶段不许乱翻盘）；
  · 深度预算用完就停，不会因为「多套了几层壳」而搜到远处的东西；
  · 目录预算用完会置 ``truncated``，而不是静悄悄少报。
"""
from __future__ import annotations

import builtins
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):  # 英文系统下控制台可能是 GBK
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core import locate  # noqa: E402

APP_TAIL = Path("resources/stm32cubemx-application/1.1.1/dist/resources/app")

PASSED = 0
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASSED
    if cond:
        PASSED += 1
    else:
        FAILED.append(f"{name}{('：' + detail) if detail else ''}")
        print(f"  [FAIL] {name}{('：' + detail) if detail else ''}")


def make_install_root(base: Path) -> Path:
    """造一棵尽量贴近真实布局的安装树，返回安装根。"""
    root = base / "CubeMX2"
    app = root / APP_TAIL
    (app / "lib/frontend").mkdir(parents=True, exist_ok=True)
    (app / "lib/backend").mkdir(parents=True, exist_ok=True)
    (app / "lib/frontend/bundle.js").write_text("//", encoding="utf-8")
    (app / "lib/frontend/secondary-window.js").write_text("//", encoding="utf-8")
    (app / "lib/backend/main.js").write_text("//", encoding="utf-8")
    dist = root / APP_TAIL.parent.parent
    (dist / "STM32CubeMX2.exe").write_text("MZ", encoding="utf-8")
    (root / "stm32cubemx2-1.1.1.exe").write_text("MZ", encoding="utf-8")
    (root / "uninstall.exe").write_text("MZ", encoding="utf-8")
    return root


def rel(root: Path, *parts: str) -> Path:
    p = root
    for x in parts:
        p = p / x
    return p


def cases(tmp: Path) -> None:
    root = make_install_root(tmp)
    dist = root / APP_TAIL.parent.parent
    app = root / APP_TAIL
    bundle = app / "lib/frontend/bundle.js"

    # --- 1. 用户指对了 / 指深了，都该归一到根 -----------------------------
    for name, raw, how in [
        ("根目录本身", str(root), "exact"),
        ("根目录带尾斜杠", str(root) + "\\", "exact"),
        ("根目录用正斜杠", str(root).replace("\\", "/"), "exact"),
        ("根启动器 exe（文件）", str(root / "stm32cubemx2-1.1.1.exe"), "exact"),
        ("dist 层（任务管理器进来的落点）", str(dist), "up"),
        ("dist 里的真身 exe", str(dist / "STM32CubeMX2.exe"), "up"),
        ("带引号的 exe", f'"{dist / "STM32CubeMX2.exe"}"', "up"),
        ("注册表图标式 ,0 后缀", str(dist / "STM32CubeMX2.exe") + ",0", "up"),
        ("app 目录（root+6）", str(app), "up"),
        ("bundle.js（root+9，翻文件能到的最深）", str(bundle), "up"),
    ]:
        r = locate.resolve_root(raw)
        check(f"归一：{name}", r.ok and r.root == root, f"how={r.how} root={r.root}")

    check(
        "门禁：向上预算用完就停（不会一路爬到盘根去猜）",
        locate.root_by_walking_up(bundle, max_up=3) is None
        and locate.root_by_walking_up(bundle) == root,
    )

    # --- 2. 输入形态清洗 --------------------------------------------------
    fullwidth = str(root).replace(":", "：").replace("\\", "＼")
    check("归一：全角冒号与反斜杠", locate.resolve_root(fullwidth).root == root)

    os.environ["FAKE_CUBEMX_ROOT"] = str(root)
    try:
        check("归一：%VAR% 展开", locate.resolve_root("%FAKE_CUBEMX_ROOT%").root == root)
    finally:
        del os.environ["FAKE_CUBEMX_ROOT"]

    check("归一：混合斜杠", locate.resolve_root(str(app).replace("\\", "/")).root == root)
    check(
        "清洗：裸盘符不被削成 'C:'",
        locate.clean_path("C:\\") == "C:\\",
        repr(locate.clean_path("C:\\")),
    )
    check("清洗：空输入", locate.resolve_root("   ").how == "empty")
    check(
        "不存在的路径不抛异常，且能靠祖先归到根",
        locate.resolve_root(str(root / "nope" / "deeper")).root == root,
    )
    ghost = Path(tempfile.mkdtemp(dir=tmp)) / "ghost" / "inside"
    check("与任何根无关的不存在路径判 miss", locate.resolve_root(str(ghost)).how == "miss")

    # --- 3. 门禁：向下搜索默认关着 ----------------------------------------
    parent = tmp  # tmp 下面恰好有一棵 CubeMX2
    check(
        "门禁：allow_down=False 时绝不向下搜（自动扫描阶段）",
        locate.resolve_root(parent, allow_down=False).root is None,
        "向下搜被关着却仍找到了根，说明门禁没生效",
    )
    down = locate.resolve_root(parent, allow_down=True)
    check(
        "保底：用户手输父目录时能搜到子目录里的根",
        down.root == root and down.how == "down",
        f"how={down.how} root={down.root}",
    )
    check("向下命中标成需确认", down.needs_confirm is True)
    check("向上/精确不算需确认", locate.resolve_root(root).needs_confirm is False)

    # --- 4. 门禁：深度预算 --------------------------------------------------
    deep_base = Path(tempfile.mkdtemp(dir=tmp)) / "shell"
    deep_root = make_install_root(deep_base / "a" / "b" / "c" / "d")
    check("建树自检：深层根确实是个根", locate.is_install_root(deep_root))
    shallow = locate.roots_under(deep_base, max_depth=2)
    check("门禁：深度封顶会拦", shallow.hits == [], f"竟命中 {shallow.hits}")
    enough = locate.roots_under(deep_base, max_depth=6)
    check("放开深度后同一棵树能命中", enough.hits == [deep_root], f"{enough.hits}")

    # --- 5. 门禁：目录预算 --------------------------------------------------
    wide = Path(tempfile.mkdtemp(dir=tmp))
    for i in range(12):
        (wide / f"d{i:02d}").mkdir()
    budget = locate.roots_under(wide, max_depth=3, max_visit=3)
    check("门禁：目录预算用完会置 truncated", budget.truncated is True)
    check("预算内的访问数不超过上限", budget.visited <= 3, f"visited={budget.visited}")

    # --- 6. 假根必须判伪 ----------------------------------------------------
    decoy = tmp / "Decoy"
    (decoy / APP_TAIL / "lib/frontend").mkdir(parents=True, exist_ok=True)
    check(
        "门禁：空壳目录树判伪（没有 bundle.js 就不是根）",
        not locate.is_install_root(decoy)
        and locate.resolve_root(str(decoy), allow_down=True).root is None,
    )

    # --- 7. 多个根要都摆出来，别只报第一个 --------------------------------
    multi = Path(tempfile.mkdtemp(dir=tmp))
    r1 = make_install_root(multi / "one")
    r2 = make_install_root(multi / "two")
    res = locate.resolve_root(multi, allow_down=True)
    check(
        "多根：主结果 + alternates 合计两个",
        res.ok and {res.root, *res.alternates} == {r1, r2},
        f"root={res.root} alt={res.alternates}",
    )
    check("多根：结果按层浅优先", res.root == r1)

    # --- 8. exe_from_command 的三种真实形态 --------------------------------
    for raw, want in [
        (f'"{root / "uninstall.exe"}" /S', str(root / "uninstall.exe")),
        (
            "C:\\Program Files\\STMicroelectronics\\STM32CubeMX2\\uninstall.exe /S",
            "C:\\Program Files\\STMicroelectronics\\STM32CubeMX2\\uninstall.exe",
        ),
        (str(dist / "STM32CubeMX2.exe") + ",0", str(dist / "STM32CubeMX2.exe")),
        ("", None),
    ]:
        got = locate.exe_from_command(raw)
        check(f"命令行取 exe：{raw[:34]!r}", got == want, f"得到 {got!r}，期望 {want!r}")

    # --- 9. 卸载记录的各种真实形态 -----------------------------------------
    b = chr(92)

    def j(*parts: str) -> str:
        return b.join(parts)

    real = {
        "DisplayName": "STM32CubeMX2",
        "InstallLocation": j("C:", "mysoftware", "cubemx2"),
        "DisplayIcon": j("C:", "mysoftware", "cubemx2", "uninstall.exe"),
    }
    check(
        "卸载表：本机真实形态（键名带版本号）两项都收",
        len(locate.candidates_from_uninstall("STM32CubeMX2_1.1.1", real)) == 2,
    )
    guid = {
        "DisplayName": "STM32CubeMX2",
        "UninstallString": f'"{j("D:", "Apps", "STM32CubeMX2", "uninstall.exe")}" /S',
    }
    check(
        "卸载表：GUID 键名 + 只有 UninstallString 也能命中（旧版整个漏掉的那种）",
        locate.candidates_from_uninstall("{7A7F4D2C}_is1", guid)
        == [j("D:", "Apps", "STM32CubeMX2", "uninstall.exe")],
    )
    icon = {
        "DisplayName": "STM32CubeMX2",
        "InstallLocation": "",
        "DisplayIcon": j("E:", "Program Files", "STM32CubeMX2", "STM32CubeMX2.exe") + ",0",
    }
    check(
        "卸载表：InstallLocation 空着时从 DisplayIcon 反推，且吃掉 ,0 后缀",
        locate.candidates_from_uninstall("STM32CubeMX2", icon)
        == [j("E:", "Program Files", "STM32CubeMX2", "STM32CubeMX2.exe")],
    )
    check("卸载表：老版 STM32CubeMX 只有空键时不产出候选",
          locate.candidates_from_uninstall("STM32CubeMX", {}) == [])
    check("卸载表：兄弟产品 CubeProgrammer 不误伤",
          locate.candidates_from_uninstall("STM32CubeProgrammer",
                                           {"DisplayName": "STM32CubeProgrammer"}) == [])

    # --- 10. 候选清单不写死机器 --------------------------------------------
    cands = [str(c) for c in locate._candidates_common()]
    check("候选清单：不再塞维护者自己机器的路径",
          not any("mysoftware" in c.lower() for c in cands))
    check(
        "候选清单：全是绝对路径（'C:X' 那种驱动器相对路径会指向 C 盘当前目录）",
        all(re.match(r"^[A-Za-z]:\\", c) or c.startswith("\\\\") for c in cands),
        next((c for c in cands if not (re.match(r"^[A-Za-z]:\\", c) or c.startswith("\\\\"))), ""),
    )
    saved = dict(os.environ)
    try:
        os.environ["SystemDrive"] = "E:"
        os.environ["LOCALAPPDATA"] = j("E:", "LAD")
        moved = {str(x).lower() for x in locate._candidates_common()}
        for want in (
            j("E:", "STM32CubeMX2"),
            j("E:", "ST", "STM32CubeMX2"),
            j("E:", "STMicroelectronics", "STM32CubeMX2"),
            j("E:", "LAD", "Programs", "STM32CubeMX2"),
        ):
            check(f"候选清单跟着环境变量走：{want}", want.lower() in moved)
    finally:
        os.environ.clear()
        os.environ.update(saved)

    # --- 11. 集成：真实机器上的完整扫描 ------------------------------------
    t0 = time.perf_counter()
    roots = locate.find_install_roots()
    cost_scan = time.perf_counter() - t0
    if roots:
        check("集成：扫到的每个根都过判据", all(locate.is_install_root(r) for r in roots), f"{roots}")
        check("集成：结果不重复", len({str(r).lower() for r in roots}) == len(roots), f"{roots}")
        print(f"  [本机] 定位到 {len(roots)} 个安装根，扫描耗时 {cost_scan * 1000:.0f} 毫秒")
    else:
        print("  [跳过] 本机没有 CubeMX2，不断言扫描结果（干净机器上就是这样）")
    check("完整扫描够快（<=5 秒）", cost_scan <= 5.0, f"{cost_scan:.1f} 秒")

    # --- 12. 别在真机上把预算烧光 -------------------------------------------
    # 本机实测：从 C:\Windows 起搜，预算 3000 个目录烧完约 1.4 秒；GitHub Actions
    # runner 上同一棵树实测 19.4 秒（曾经贴着 20 秒的线过）。留 60 秒是给慢盘
    # 虚拟机和 CI 的余量 —— 真正失控的搜索要跑好几分钟，仍然拦得住。
    t0 = time.perf_counter()
    win = locate.roots_under(Path(os.environ.get("SYSTEMROOT", "C:\\Windows")))
    cost = time.perf_counter() - t0
    check(
        "有界搜索在真实大目录树上也要够快（<=60 秒）",
        cost <= 60.0,
        f"耗时 {cost:.1f} 秒",
    )
    check(
        "真实机器上访问数也不越预算",
        win.visited <= locate.MAX_DIRS_VISITED,
        f"visited={win.visited}",
    )
    print(f"  [本机] 从 Windows 目录起搜：访问 {win.visited} 个目录，"
          f"truncated={win.truncated}，耗时 {cost:.1f} 秒")

    # --- 13. 交互保底：不点头就不许动手 ------------------------------------
    import main as tool  # 被测的是 main._ask_for_root

    cfg = tmp / "config.json"
    real_config_path = locate.paths.config_path
    locate.paths.config_path = lambda: cfg

    def run_inputs(inputs: list[str]):
        """把一串输入喂给 _ask_for_root，返回 (选中的根, 配置文件里的 installRoot)。"""
        queue = list(inputs)

        def fake_input(prompt="", *a, **kw):
            if not queue:
                raise EOFError
            return queue.pop(0)

        real_input = builtins.input
        builtins.input = fake_input
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                got = tool._ask_for_root()
        finally:
            builtins.input = real_input
        saved = None
        if cfg.is_file():
            try:
                saved = json.loads(cfg.read_text(encoding="utf-8")).get("installRoot")
            except ValueError:
                saved = "<坏文件>"
        return got, saved

    try:
        got, saved = run_inputs([str(dist)])
        check("保底：用户给 dist 层，归一化后拿到根", got == root, f"{got}")
        check("保底：拿到根就写下记忆", saved is not None and Path(saved) == root, f"{saved!r}")

        cfg.unlink(missing_ok=True)
        got, saved = run_inputs([str(tmp), "y"])
        check("保底：向下搜到的目录，用户同意后才采用", got == root and Path(saved or "") == root)

        cfg.unlink(missing_ok=True)
        got, saved = run_inputs([str(tmp), "n"])
        check(
            "门禁：向下搜到的目录，用户不点头就绝不采用、也不写记忆",
            got is None and saved is None,
            f"got={got} saved={saved!r}",
        )

        cfg.unlink(missing_ok=True)
        got, saved = run_inputs([""])
        check("保底：留空即放弃且不写记忆", got is None and not cfg.exists())

        cfg.unlink(missing_ok=True)
        got, saved = run_inputs([str(tmp / "nowhere"), ""])
        check("保底：填了个无关路径，问一次就放弃", got is None and not cfg.exists())

        # 记忆失效（目录被挪走）时必须回退，而不是抱着一个错路径不放
        cfg.write_text(json.dumps({"installRoot": str(root)}), encoding="utf-8")
        check("记忆：有效时读得回来", locate.remembered_root() == root)
        cfg.write_text(json.dumps({"installRoot": str(tmp / "gone")}), encoding="utf-8")
        check("门禁：记忆指向不存在的目录时读成 None", locate.remembered_root() is None)
        cfg.write_text("{ 这不是 json", encoding="utf-8")
        check("门禁：配置文件坏了也不炸，读成 None", locate.remembered_root() is None)
        check("拒绝记住假根", not locate.remember_root(decoy))
    finally:
        locate.paths.config_path = real_config_path
        cfg.unlink(missing_ok=True)

    # --- 14. pick_root：开发脚本用的非交互定位 ------------------------------
    check(
        "pick_root 显式给根 → 用它并标明来源",
        locate.pick_root(str(root)).root == root
        and locate.pick_root(str(root)).source == "命令行 -g",
    )
    check("pick_root 显式给 dist 层 → 往上归一到根", locate.pick_root(str(dist)).root == root)
    bad = locate.pick_root(str(tmp / "nope"))
    check(
        "pick_root 坏路径 → 不给根，报错里带上用户输入的那串",
        bad.root is None and bad.source == "无效" and "nope" in bad.problem(),
        bad.problem(),
    )
    # 脚本非交互，拿不到「用户点头」，所以向下搜必须关着。同一个父目录：
    # main._ask_for_root 能搜出根，pick_root 必须搜不出 —— 这条差异就是要钉住的行为。
    check(
        "门禁：pick_root 不向下搜（父目录输入要失败，不能悄悄搜到一个根）",
        locate.pick_root(str(tmp)).root is None
        and locate.resolve_root(str(tmp), allow_down=True).root == root,
    )

    real_find, real_mem = locate.find_install_roots, locate.remembered_root
    try:
        locate.find_install_roots = lambda extra=None: [root]
        locate.remembered_root = lambda: None
        one = locate.pick_root()
        check("pick_root 自动扫到唯一根 → 用它",
              one.root == root and one.source == "自动扫描")

        locate.find_install_roots = lambda extra=None: [root, app]
        many = locate.pick_root()
        check(
            "门禁：扫到多个根时不选第一个，报错让人补 -g",
            many.root is None and many.source == "多个" and "2 个" in many.problem(),
            many.problem(),
        )

        locate.find_install_roots = lambda extra=None: []
        locate.remembered_root = lambda: root
        check("pick_root 扫不到但记忆里有 → 用记忆", locate.pick_root().root == root)

        locate.remembered_root = lambda: None
        none = locate.pick_root()
        check("pick_root 什么都没有 → 报错指向 --doctor 而不是静默",
              none.root is None and "--doctor" in none.problem(), none.problem())
    finally:
        locate.find_install_roots, locate.remembered_root = real_find, real_mem


def main() -> int:
    # 必须 resolve()：TEMP 在 CI 和部分机器上是 8.3 短路径写法（GitHub Actions
    # runner 上 mkdtemp 返回 C:\Users\RUNNER~1\AppData\Local\Temp\...），
    # 而 locate 的 _canon() 按设计返回 resolve() 后的长路径 —— 两边写法不同，
    # Path 相等性（大小写不敏感的逐字比较，不解析短名）就会让**所有**「== root」
    # 断言成批假失败，且 FAIL 明细只打印被测方的 root（长路径），看着完全正常。
    # 期望值先落到同一写法空间，顺带也钉住 _canon 对已归一路径是幂等的。
    tmp = Path(tempfile.mkdtemp(prefix="cubemx2zh-locate-test-")).resolve()
    try:
        cases(tmp)
    finally:
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
