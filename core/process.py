from __future__ import annotations

import subprocess


IMAGE_NAME = "STM32CubeMX2.exe"


def running_cube_processes() -> list[str]:
    """返回正在运行的 STM32CubeMX2 进程行；兼容中英文 tasklist 空结果提示。"""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {IMAGE_NAME}", "/FO", "CSV", "/NH"],
            text=True,
            errors="replace",
            encoding="utf-8",
            # 中文系统 codepage 可能是 GBK，fallback 再试
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    except UnicodeDecodeError:
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"IMAGENAME eq {IMAGE_NAME}", "/FO", "CSV", "/NH"],
                errors="replace",
            ).decode("gbk", errors="replace")
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    lines: list[str] = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        # tasklist 信息行：中英文都不含镜像名引号，直接跳过
        # 合法 CSV： "STM32CubeMX2.exe","1234",...
        if not ln.startswith('"'):
            continue
        if IMAGE_NAME.lower() not in ln.lower():
            continue
        lines.append(ln)
    return lines


def is_cube_running() -> bool:
    return bool(running_cube_processes())
