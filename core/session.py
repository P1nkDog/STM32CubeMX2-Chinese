from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import backup, gzip_sync, i18n, langpack, locate


@dataclass
class PatchReport:
    ok: bool
    root: Path
    target: Path | None = None
    messages: list[str] = field(default_factory=list)


# ===========================================================================
# i18n 注入（机制说明见 core/i18n.py 顶部）
# ===========================================================================


@dataclass
class I18nReport:
    """i18n 注入结果。"""

    ok: bool
    root: Path
    app_dir: Path | None = None
    messages: list[str] = field(default_factory=list)
    files: list[tuple[str, int, int]] = field(default_factory=list)  # (相对路径, 前, 后)
    problems: list[str] = field(default_factory=list)


def i18n_target_paths(root: Path) -> list[tuple[i18n.Target, Path]]:
    """返回 i18n 策略要改的文件 (目标定义, 磁盘路径)。"""
    a = locate.app_dir(root)
    if not a:
        return []
    out: list[tuple[i18n.Target, Path]] = []
    for t in i18n.TARGETS:
        p = a / t.rel
        if p.is_file():
            out.append((t, p))
    return out


def _clean_base(path: Path) -> tuple[bytes | None, str]:
    """取干净基线：优先 .orig；已注入但无备份则拒绝。

    这样「重复执行汉化」等价于「从干净基线重新注入」，
    翻译更新后重新跑一次即可，不需要用户手动回滚。
    """
    bak = backup.backup_path(path)
    if bak.is_file():
        return bak.read_bytes(), f"从 .orig 基线重建"
    raw = path.read_bytes()
    if i18n.MARKER.encode("utf-8") in raw:
        return None, "已注入但缺少 .orig 备份，无法安全重建"
    return raw, "首次注入"


def apply_i18n_patch(
    root: Path,
    pack: dict[str, str],
    dict_source: str = "",
    *,
    verify_syntax: bool = True,
) -> I18nReport:
    """执行 i18n 注入。

    每个文件独立处理，任一文件失败**只回滚该文件**，不影响其它文件；
    写盘前先用 node --check 做语法门禁（校验失败则整文件不落盘）。
    """
    rep = I18nReport(ok=False, root=root)
    a = locate.app_dir(root)
    rep.app_dir = a
    if not a:
        rep.problems.append("未找到 app 目录")
        return rep

    node = i18n.find_node()
    if verify_syntax and not node:
        rep.problems.append("未找到 node，跳过语法门禁（建议安装 Node.js 后重试）")

    targets = i18n_target_paths(root)
    if not targets:
        rep.problems.append("未找到任何待注入文件")
        return rep

    any_ok = False
    for target, path in targets:
        before = path.stat().st_size
        base, why = _clean_base(path)
        if base is None:
            rep.problems.append(f"{path.name}: {why}")
            continue
        try:
            text = base.decode("utf-8")
            new_text, logs = i18n.inject_text(text, target, pack)
        except (ValueError, KeyError, UnicodeDecodeError) as e:  # noqa: BLE001
            rep.problems.append(f"{path.name}: 注入失败 {e}")
            continue

        # ---- 语法门禁：先写带 .js 扩展名的临时文件校验，通过才落盘
        # 注意：node --check 会按扩展名选 loader，用 .tmp 会报
        # ERR_UNKNOWN_FILE_EXTENSION，所以临时文件必须是 .js，
        # 且放在系统临时目录，避免在 app 目录里留下会被加载的文件。
        with tempfile.TemporaryDirectory(prefix="cubemx2zh_gate_") as td:
            gate = Path(td) / (Path(target.rel).name + ".js")
            try:
                gate.write_text(new_text, encoding="utf-8")
                if verify_syntax:
                    ok, msg = i18n.node_check(gate)
                    if not ok:
                        rep.problems.append(f"{path.name}: {msg}（未落盘，原文件未改动）")
                        continue
                backup.ensure_backup(path)
                path.write_bytes(new_text.encode("utf-8"))
            except OSError as e:  # noqa: BLE001
                rep.problems.append(f"{path.name}: 写盘失败 {e}")
                backup.restore_from_backup(path)
                continue

        after = path.stat().st_size
        rep.files.append((target.rel, before, after))
        rep.messages.append(f"{path.name}: {why}，{before:,} -> {after:,} 字节")
        for line in logs:
            rep.messages.append(line)
        any_ok = True

        # ---- bundle.js 还有 .gz 副本需要同步
        if target.gz:
            gz = path.with_name(path.name + ".gz")
            if gz.is_file():
                try:
                    backup.ensure_backup(gz)
                    size = gzip_sync.write_gz_from_bytes(path.read_bytes(), gz)
                    rep.messages.append(f"{gz.name}: 已同步重压（{size:,} 字节）")
                except OSError as e:  # noqa: BLE001
                    rep.problems.append(f"{gz.name}: 重压失败 {e}")

    if any_ok:
        backup.write_state(
            root,
            {
                "tool": "STM32CubeMX2-Chinese",
                "strategy": "i18n",
                "dictSource": dict_source,
                "locale": langpack.LOCALE_ID,
                "entries": len(pack),
                "files": [rel for rel, _, _ in rep.files],
            },
        )
        rep.messages.append(f"已写入状态: {backup.state_path(root)}")

    rep.ok = any_ok
    if not rep.messages:
        rep.messages.append("没有文件被注入")
    return rep


def rollback_i18n(root: Path) -> PatchReport:
    """回滚 i18n 注入：把每个目标文件及 .gz 从 .orig 还原。"""
    msgs: list[str] = []
    ok = False
    primary: Path | None = None
    a = locate.app_dir(root)
    if not a:
        return PatchReport(False, root, None, messages=["未找到 app 目录"])
    for target in i18n.TARGETS:
        path = a / target.rel
        if not path.is_file():
            continue
        primary = primary or path
        restored = backup.restore_from_backup(path)
        msgs.append(f"{path.name}: {'已恢复' if restored else '无 .orig 备份'}")
        ok = ok or restored
        if target.gz:
            gz = path.with_name(path.name + ".gz")
            if gz.is_file() and backup.backup_path(gz).is_file():
                msgs.append(
                    f"{gz.name}: {'已恢复' if backup.restore_from_backup(gz) else '恢复失败'}"
                )
    backup.clear_state(root)
    return PatchReport(ok, root, primary, messages=msgs)
