from __future__ import annotations

import os
import winreg
from pathlib import Path

# 相对安装根：resources/stm32cubemx-application/<ver>/dist/resources/app
_APP_GLOB = Path("resources/stm32cubemx-application/*/dist/resources/app")
_EXE_REL = Path("resources/stm32cubemx-application/1.1.1/dist/STM32CubeMX2.exe")


def _candidates_from_env() -> list[Path]:
    out: list[Path] = []
    for key in ("STM32CUBEMX2_PATH", "STM32CubeMX2_PATH"):
        v = os.environ.get(key)
        if v:
            out.append(Path(v))
    return out


def _candidates_from_registry() -> list[Path]:
    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    found: list[Path] = []
    for root, sub in keys:
        try:
            with winreg.OpenKey(root, sub) as k:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    i += 1
                    if "stm32cubemx" not in name.lower() and "cubemx2" not in name.lower():
                        continue
                    try:
                        with winreg.OpenKey(k, name) as ik:
                            for vk in ("InstallLocation", "DisplayIcon"):
                                try:
                                    val, _ = winreg.QueryValueEx(ik, vk)
                                except OSError:
                                    continue
                                if not val:
                                    continue
                                p = Path(val)
                                if p.is_file():
                                    p = p.parent
                                found.append(p)
                    except OSError:
                        continue
        except OSError:
            continue
    return found


def _candidates_common() -> list[Path]:
    home = Path.home()
    return [
        Path(r"C:\mysoftware\cubemx2"),
        Path(r"C:\STMicroelectronics\STM32CubeMX2"),
        Path(r"C:\Program Files\STMicroelectronics\STM32CubeMX2"),
        home / "STM32CubeMX2",
        home / ".local" / "stm32cube",
    ]


def is_install_root(path: Path) -> bool:
    if not path or not path.is_dir():
        return False
    apps = list(path.glob("resources/stm32cubemx-application/*/dist/resources/app"))
    return any((a / "lib/frontend/bundle.js").is_file() for a in apps)


def find_install_roots(extra: Path | None = None) -> list[Path]:
    seen: list[Path] = []
    cands: list[Path] = []
    if extra:
        cands.append(extra)
    cands.extend(_candidates_from_env())
    cands.extend(_candidates_from_registry())
    cands.extend(_candidates_common())
    for c in cands:
        try:
            c = c.resolve()
        except OSError:
            continue
        if c in seen:
            continue
        if is_install_root(c):
            seen.append(c)
    return seen


def app_dir(root: Path) -> Path | None:
    apps = sorted(root.glob("resources/stm32cubemx-application/*/dist/resources/app"))
    return apps[-1] if apps else None


def bundle_js_path(root: Path) -> Path | None:
    a = app_dir(root)
    if not a:
        return None
    p = a / "lib/frontend/bundle.js"
    return p if p.is_file() else None
