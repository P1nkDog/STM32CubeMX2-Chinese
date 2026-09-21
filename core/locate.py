from __future__ import annotations

import json
import os
import re
import stat
import winreg
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

# 安装根的特征路径。中间那段是版本号，所以用通配：判据只认「这一层下面有没有
# 可注入的 bundle」，不认具体版本 —— 写死 1.1.1 会让应用一升级整套定位就失效。
APP_GLOB = "resources/stm32cubemx-application/*/dist/resources/app"

# 只用于猜常见安装位置；真正认根靠上面的 APP_GLOB 判据。
APP_DIRNAME = "STM32CubeMX2"


def _candidates_from_env() -> list[Path]:
    out: list[Path] = []
    for key in ("STM32CUBEMX2_PATH", "STM32CubeMX2_PATH"):
        v = os.environ.get(key)
        if v:
            out.append(Path(v))
    return out


def candidates_from_uninstall(key_name: str, values: dict[str, str]) -> list[str]:
    """从一条卸载记录里抠出所有可能的安装位置。

    纯函数 —— 注册表遍历交给 ``_candidates_from_registry()``，这样各种安装器的
    真实形态都能直接喂进来测。

    以前这里是按**键名**过滤的（键名含 cubemx 才去读值），本机键名恰好是
    ``STM32CubeMX2_1.1.1`` 才走得通；Inno Setup 一类安装器默认写 GUID 键名，
    那种机器上这一路会整个漏掉 —— 而注册表是这套逻辑里唯一通用的发现机制。
    现在键名和 ``DisplayName`` 一起看。

    宁可多匹配几个兄弟产品也不要漏：判伪始终交给 ``is_install_root``，
    CubeProgrammer 之类过不了判据，多读几个键没有副作用。
    """
    haystack = f"{key_name} {values.get('DisplayName', '')}".lower()
    if "cubemx" not in haystack:
        return []
    out: list[str] = []
    loc = clean_path(values.get("InstallLocation", ""))
    if loc:
        out.append(loc)
    for vk in ("DisplayIcon", "UninstallString", "QuietUninstallString", "ModifyPath"):
        s = clean_path(exe_from_command(values.get(vk, "")) or "")
        if s and s not in out:
            out.append(s)
    return out


def _iter_uninstall_records() -> tuple[list[tuple[str, dict[str, str]]], bool]:
    """遍历三处卸载表，返回 (记录, 是否至少成功打开了一处)。

    「读不到注册表」和「注册表里确实没有」要分开 —— 前者不能拿来告诉用户
    「你没装」。
    """
    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    value_names = (
        "DisplayName",
        "InstallLocation",
        "DisplayIcon",
        "UninstallString",
        "QuietUninstallString",
        "ModifyPath",
    )
    records: list[tuple[str, dict[str, str]]] = []
    readable = False
    for root, sub in keys:
        try:
            with winreg.OpenKey(root, sub) as k:
                readable = True
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    i += 1
                    vals: dict[str, str] = {}
                    try:
                        with winreg.OpenKey(k, name) as ik:
                            for vk in value_names:
                                try:
                                    val, _ = winreg.QueryValueEx(ik, vk)
                                except OSError:
                                    continue
                                if isinstance(val, str) and val.strip():
                                    vals[vk] = val
                    except OSError:
                        continue
                    records.append((name, vals))
        except OSError:
            continue
    return records, readable


def _candidates_from_registry() -> list[Path]:
    """从卸载表反推候选目录。注册表读不动就当没有这一路。"""
    records, _ = _iter_uninstall_records()
    out: list[Path] = []
    for name, vals in records:
        out.extend(Path(s) for s in candidates_from_uninstall(name, vals))
    return out


def _install_bases() -> list[Path]:
    """可能承载安装目录的基址，全部从环境变量取。

    不写死 ``C:\\``：``%ProgramFiles%`` 可以被挪到别的盘，装在 D 盘的用户
    以前那一版一个都探不到。
    """
    out: list[Path] = []
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "APPDATA"):
        v = os.environ.get(key)
        if v:
            out.append(Path(v))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        # 卸载键写在 HKCU，说明这个安装器走的是「仅为当前用户」模式，
        # 那么它的默认落点就是 %LOCALAPPDATA%\Programs —— 别人机器上
        # 最可能装着的地方。
        out.append(Path(local) / "Programs")
    sysdrive = os.environ.get("SystemDrive") or "C:"
    # %SystemDrive% 的值是 ``C:`` 不带斜杠。Path("C:") / "X" 得到的是 ``C:X`` ——
    # 那是「C 盘当前工作目录下的 X」这种驱动器相对路径，几乎不存在但会误导，
    # 所以必须先把尾分隔符补回来。
    if not sysdrive.endswith("\\"):
        sysdrive += "\\"
    out.append(Path(sysdrive))
    for extra in ("ST", "STMicroelectronics", "Programs"):
        out.append(Path(sysdrive) / extra)
    out.append(Path.home())
    return out


_SUBDIRS = ("STMicroelectronics", "ST", "STM32")


def _candidates_common() -> list[Path]:
    """常见安装位置 = 基址 ×（厂商子目录）× 目录名。

    刻意不含任何具体机器上的路径：以前清单里写着 ``C:\\mysoftware\\cubemx2``，
    那是维护者自己的目录，打进发布包对别人一点用没有。
    """
    out: list[Path] = []
    for base in _install_bases():
        out.append(base / APP_DIRNAME)
        for sub in _SUBDIRS:
            out.append(base / sub / APP_DIRNAME)
    out.append(Path.home() / ".local" / "stm32cube")
    return out


def is_install_root(path: Path) -> bool:
    if not path or not path.is_dir():
        return False
    apps = list(path.glob(APP_GLOB))
    return any((a / "lib/frontend/bundle.js").is_file() for a in apps)


def find_install_roots(extra: Path | None = None) -> list[Path]:
    """按 命令行 > 环境变量 > 注册表 > 常见位置 的顺序找安装根。

    每个候选都过 ``resolve_root()``，所以「注册表把目录写成了 exe 所在那一层」
    这类错位也能纠正 —— 以前只认逐字相等的那一个目录。
    这里一律 ``allow_down=False``：自动扫描阶段不许乱翻盘，向下搜只在
    用户手动给出路径之后才开（见 ``resolve_root``）。
    """
    seen: list[Path] = []
    cands: list[Path] = []
    if extra:
        cands.append(extra)
    cands.extend(_candidates_from_env())
    cands.extend(_candidates_from_registry())
    cands.extend(_candidates_common())
    for c in cands:
        r = resolve_root(c, allow_down=False)
        if r.ok and r.root not in seen:
            seen.append(r.root)
    return seen


def app_dir(root: Path) -> Path | None:
    apps = sorted(root.glob(APP_GLOB))
    return apps[-1] if apps else None


# ---------------------------------------------------------------------------
# 用户手输路径 -> 安装根
# ---------------------------------------------------------------------------
#
# 用户手输路径最常见的错法**不是给了一棵别的树，而是层级不对**。实测本机布局
# （相对安装根的层数）：
#
#     <root>\stm32cubemx2-1.1.1.exe                     +1   根启动器，快捷方式指这里
#     <root>\resources\stm32cubemx-application\1.1.1\dist\   +4  任务管理器「打开文件
#                                                            所在的位置」的落点，里面
#                                                            就是 STM32CubeMX2.exe，
#                                                            看起来极像正确的安装目录
#     <root>\...\dist\resources\app                     +6   我们真正操作的 app 目录
#     <root>\...\app\lib\frontend\bundle.js             +9   照文档去翻文件能到的最深
#
# 往上走是**零风险**的：祖先链唯一，不可能搜到别处去，而每一级的代价只是一次
# glob。所以这里留足余量，不为省几次统计把用户挡在门外。
MAX_WALK_UP = 12

# 向下搜是另一回事：它可能命中用户并没有指的东西，所以默认关闭（只在用户手动
# 给出路径之后才允许），并且必须有「深度」和「目录数」两道预算封顶 —— 否则起点
# 一旦是 C:\Users\<用户> 这种目录，就会去遍历整个用户配置目录。
MAX_SEARCH_DOWN = 3
MAX_DIRS_VISITED = 3000

# 跳过这些目录：底下不可能有 CubeMX2 的安装根，却动辄几万子项，
# 不跳过的话目录预算全烧在噪声里。
_PRUNE_DIRS = frozenset(
    {
        "node_modules",
        "__pycache__",
        "$recycle.bin",
        "system volume information",
        ".git",
        ".svn",
        ".gradle",
        ".m2",
    }
)

# 中文输入法下用户可能打出全角冒号/反斜杠；NBSP 和全角空格也按空白处理。
_FULLWIDTH = str.maketrans(
    {
        "＼": "\\",
        "／": "/",
        "：": ":",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "\u00a0": " ",
        "\u3000": " ",
    }
)

_ICON_INDEX = re.compile(r",\s*\d+$")
_EXE_TAIL = re.compile(r"^(.*?\.(?:exe|dll|ico))(?:\s.*)?$", re.IGNORECASE)
_BARE_DRIVE = re.compile(r"^[A-Za-z]:$")


def clean_path(raw: str | Path) -> str | None:
    """把用户可能粘进控制台的各种形态收敛成一个可打开的路径字符串。

    只处理**输入形态**，不判断存在性 —— 判伪交给 resolve_root()。
    """
    s = str(raw or "").strip().translate(_FULLWIDTH)
    s = os.path.expandvars(s)
    s = s.strip().strip('"').strip("'").strip()
    s = _ICON_INDEX.sub("", s)
    s = s.replace("/", "\\").strip().rstrip("\\ \t").strip()
    if _BARE_DRIVE.match(s):  # "C:\" 去掉尾斜杠会变成 "C:"，那是驱动器相对路径
        s += "\\"
    return s or None


def exe_from_command(val: str) -> str | None:
    """从 UninstallString / DisplayIcon 这类命令行串里取出 exe 路径。

    三种真实形态都得吃下，注册表里都见得到：

        "C:\\...\\uninstall.exe" /S          带引号带参数
        C:\\Program Files\\x\\uninstall.exe   不带引号，路径里还有空格
        C:\\...\\STM32CubeMX2.exe,0          注册表图标索引后缀
    """
    s = str(val or "").strip().translate(_FULLWIDTH)
    s = os.path.expandvars(s)
    if s.startswith('"'):
        end = s.find('"', 1)
        if end > 0:
            return s[1:end].strip() or None
    s = _ICON_INDEX.sub("", s).strip()
    m = _EXE_TAIL.match(s)
    if m:
        return m.group(1)
    return s or None


def root_by_walking_up(start: Path, max_up: int = MAX_WALK_UP) -> Path | None:
    """从给定位置（含其祖先）找安装根；给定的是文件时先取父目录。"""
    cur = start
    try:
        if cur.is_file():
            cur = cur.parent
    except OSError:
        pass
    for _ in range(max_up + 1):
        if is_install_root(cur):
            return cur
        parent = cur.parent
        if parent == cur:  # 到盘根了
            return None
        cur = parent
    return None


def _is_reparse(entry: os.DirEntry) -> bool:
    """联接点（junction）不是符号链接，``is_symlink()`` 认不出来，但它会让
    BFS 绕圈（``C:\\Users\\All Users`` -> ``C:\\ProgramData`` 就是这种）。
    """
    try:
        attrs = entry.stat(follow_symlinks=False).st_file_attributes
    except OSError:
        return True  # 读不动的目录一律不进队
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _subdirs(path: Path) -> list[Path]:
    out: list[Path] = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.name.lower() in _PRUNE_DIRS:
                        continue
                    if not entry.is_dir():
                        continue
                    if entry.is_symlink() or _is_reparse(entry):
                        continue
                except OSError:
                    continue
                out.append(Path(entry.path))
    except OSError:
        pass
    return out


@dataclass
class Search:
    """``roots_under()`` 的结果。``truncated`` 要能被测试断言住，
    否则「有预算封顶」只是写在注释里好看。"""

    hits: list[Path] = field(default_factory=list)
    visited: int = 0
    truncated: bool = False


def roots_under(
    start: Path,
    max_depth: int = MAX_SEARCH_DOWN,
    max_visit: int = MAX_DIRS_VISITED,
) -> Search:
    """在 ``start`` 之下做**有界**广度优先搜索，找出所有安装根。

    调用方必须清楚：这里返回的东西用户并没有指，所以只能拿来**问**，
    不能直接拿来改文件。
    """
    out = Search()
    if not start.is_dir():
        return out
    queue: deque[tuple[Path, int]] = deque([(start, 0)])
    seen: set[str] = set()
    while queue:
        if out.visited >= max_visit:
            out.truncated = True
            break
        cur, depth = queue.popleft()
        out.visited += 1
        if is_install_root(cur):
            key = str(cur).lower()
            if key not in seen:
                seen.add(key)
                out.hits.append(cur)
            continue  # 命中了就不必再往它那棵巨大的子树里钻
        if depth >= max_depth:
            continue
        queue.extend((c, depth + 1) for c in _subdirs(cur))
    out.hits.sort(key=lambda p: (len(p.parts), str(p).lower()))
    return out


@dataclass
class Resolved:
    root: Path | None
    how: str  # exact | up | down | miss | empty
    alternates: list[Path] = field(default_factory=list)
    visited: int = 0
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.root is not None

    @property
    def needs_confirm(self) -> bool:
        """``down`` 意味着这个目录是我们在用户给的路径**下面**搜到的，
        不是他指的那一个 —— 必须回显让他确认后才能动手。"""
        return self.how == "down"


def _canon(path: Path) -> Path:
    """归一路径写法。

    用户可能打 `C:\\MYSOFTWARE\\cubemx2`，注册表里是 `c:\\mysoftware\\cubemx2` ——
    不统一成同一个形状，「同一个安装根」就会被当成两个候选，去重和
    「记住的安装根」的比对都会失配。
    """
    try:
        return path.resolve()
    except OSError:
        return path


def resolve_root(raw: str | Path, allow_down: bool = False) -> Resolved:
    """把任意形态的输入收敛成安装根。

    ``allow_down`` 默认 False：自动扫描阶段绝不乱翻盘，向下搜只在用户
    手动给出路径之后开。
    """
    s = clean_path(raw)
    if not s:
        return Resolved(None, "empty")
    start = Path(s)
    try:
        base = start.parent if start.is_file() else start
    except OSError:
        base = start
    if is_install_root(base):
        return Resolved(_canon(base), "exact")
    up = root_by_walking_up(start)
    if up is not None:
        return Resolved(_canon(up), "up")
    if allow_down:
        r = roots_under(base)
        hits = [_canon(p) for p in r.hits]
        if hits:
            return Resolved(hits[0], "down", hits[1:], r.visited, r.truncated)
        return Resolved(None, "miss", [], r.visited, r.truncated)
    return Resolved(None, "miss")


@dataclass
class Picked:
    """``pick_root()`` 的结果：一个根 + 它是怎么来的。

    来源一定要跟着返回 —— 验证跑在另一台安装上是**假绿**，比跑失败更糟，
    所以调用方必须把它打印出来。
    """

    root: Path | None
    source: str
    roots: list[Path] = field(default_factory=list)
    asked: str = ""

    def problem(self) -> str:
        if self.source == "多个":
            lines = [f"自动定位找到 {len(self.roots)} 个安装目录，不猜，请用 -g 指定："]
            lines += [f"  - {r}" for r in self.roots]
            return "\n".join(lines)
        if self.source == "无效":
            return (
                f"[错误] 不是有效的安装目录: {self.asked}"
                "（试过它本身和它的祖先目录；脚本里不启用向下搜）"
            )
        return (
            "自动定位没找到安装目录。请先跑 `python main.py --doctor` 看诊断，"
            "或用 -g <安装目录> 显式指定。"
        )


def pick_root(explicit: str | Path | None = None) -> Picked:
    """开发脚本用的「给我一个安装根」：给了就归一化用，没给就自动定位。

    与 ``main._pick_root`` 的三处刻意差别，都是因为脚本会被管道和批处理调用：

    * **不弹输入框** —— 问也没人答，直接返回失败并说清下一步；
    * **不向下搜**（``allow_down=False``）—— 向下搜出来的东西在 main.py 里要
      用户点头才敢用，脚本里没有这个环节，所以干脆不开；
    * **多个根不选第一个** —— 猜错对象会产出一条看起来完全正常的绿。
    """
    if explicit:
        r = resolve_root(explicit, allow_down=False)
        if r.ok and r.root is not None:
            return Picked(r.root, "命令行 -g")
        return Picked(None, "无效", [], asked=str(explicit))
    roots = find_install_roots()
    remembered = remembered_root()
    if remembered and (not roots or remembered in roots):
        return Picked(remembered, "记住的安装根")
    if len(roots) == 1:
        return Picked(roots[0], "自动扫描")
    if not roots:
        return Picked(None, "未找到", [])
    return Picked(None, "多个", roots)


# ---------------------------------------------------------------------------
# 扫不到时：到底是没装、装的是老版、还是装了但没找到
# ---------------------------------------------------------------------------


def _norm_product(text: str) -> str:
    """把键名和显示名揉成同一种形状再比对：``STM32CubeMX2_1.1.1`` 和
    ``STM32 Cube MX 2`` 应该算同一个产品名。
    """
    return re.sub(r"[\s_\-\.]+", "", (text or "").lower())


def _describe_record(name: str, vals: dict[str, str]) -> str:
    bits = [vals.get("DisplayName") or name]
    for vk in ("InstallLocation", "DisplayIcon", "UninstallString"):
        v = vals.get(vk)
        if v:
            bits.append(f"{vk}={v}")
    return "  · " + "    ".join(bits)


@dataclass
class Diagnosis:
    """``kind`` 的四种取值对应四句完全不同的话。

    合成一句「未找到安装目录」等于什么也没说：没装的人要的是「本工具不支持
    老版 CubeMX」，装了没找到的人要的是「请把目录告诉我」。
    """

    kind: str  # not_installed | old_cubemx_only | registered_but_unreachable | registry_unreadable
    cubemx2: list[str] = field(default_factory=list)
    old: list[str] = field(default_factory=list)

    def brief(self) -> str:
        if self.kind == "registry_unreadable":
            return (
                "读不到系统的卸载记录（注册表被安全策略挡住，或以受限账户运行）。\n"
                "  这种情况下工具无法自动判断你有没有安装，请直接输入安装目录。"
            )
        if self.kind == "registered_but_unreachable":
            lines = [
                "注册表里有 STM32CubeMX2 的卸载记录，但它给出的目录里"
                "没有可注入的文件。常见原因：装在另一个 Windows 账户下、"
                "装完又被手动挪过位置、或者安装器没写目录。"
            ]
            lines += self.cubemx2
            if self.old:
                lines.append("另外也找到了老版 STM32CubeMX 的记录：")
                lines += self.old
            lines.append("  请把安装目录手动告诉工具（下面会提示输入）。")
            return "\n".join(lines)
        if self.kind == "old_cubemx_only":
            lines = [
                "只找到**老版 STM32CubeMX** 的卸载记录，没有找到 CubeMX2。\n"
                "  本工具只汉化 Theia 版的 STM32CubeMX2（1.1.x），"
                "老版（5.x/6.x，Java 程序）结构完全不同，汉化不了，"
                "STM32CubeIDE 也一样。"
            ]
            lines += self.old
            lines.append("  如果你确实装了 CubeMX2，请把它的安装目录手动告诉工具。")
            return "\n".join(lines)
        return (
            "系统的卸载记录里没有任何 CubeMX2 的痕迹，这台机器上很可能没装。\n"
            "  本工具只支持 Theia 版的 STM32CubeMX2（1.1.x）。"
        )


def diagnose_missing() -> Diagnosis:
    records, readable = _iter_uninstall_records()
    if not readable:
        return Diagnosis("registry_unreadable")
    cube2: list[str] = []
    old: list[str] = []
    for name, vals in records:
        hay = _norm_product(f"{name} {vals.get('DisplayName', '')}")
        if "cubemx2" in hay:
            cube2.append(_describe_record(name, vals))
        elif "cubemx" in hay:
            old.append(_describe_record(name, vals))
    if cube2:
        return Diagnosis("registered_but_unreachable", cube2, old)
    if old:
        return Diagnosis("old_cubemx_only", [], old)
    return Diagnosis("not_installed")


# ---------------------------------------------------------------------------
# 记住由用户亲手确认过的安装根
# ---------------------------------------------------------------------------


def remembered_root() -> Path | None:
    """上次由用户确认过的安装根；对不上就返回 None。

    只存用户亲手给的或从列表里挑的那一个，自动扫描的唯一命中**不写**——
    那种情况下次照样能扫出来（52 毫秒），记下来反而会把一次偶然的误判固化。
    失效（卸载了、挪走了、手输错了又改）就静默回退到扫描，宁可不记。
    """
    p = paths.config_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        raw = data.get("installRoot")
    except (OSError, ValueError):
        return None
    if not isinstance(raw, str) or not raw.strip():
        return None
    r = resolve_root(raw, allow_down=False)
    return r.root if r.ok else None


def remember_root(root: Path) -> bool:
    """写下用户确认过的安装根。写失败不算错 —— 下次重新问一次而已。"""
    if not is_install_root(root):
        return False
    try:
        p = paths.config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"installRoot": str(root)}
        p.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True
    except OSError:
        return False
