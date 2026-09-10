from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import backup, gzip_sync, patcher
from .locate import bundle_js_path


@dataclass
class PatchReport:
    ok: bool
    root: Path
    target: Path | None
    results: list[patcher.ReplaceResult] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    rolled_back: bool = False


def dry_run(root: Path, dictionary: dict) -> PatchReport:
    target = bundle_js_path(root)
    if not target:
        return PatchReport(False, root, None, messages=["未找到 bundle.js"])
    data = target.read_bytes()
    rel_key = "lib/frontend/bundle.js"
    file_cfg = (dictionary.get("files") or {}).get(rel_key) or {}
    entries = file_cfg.get("entries") or []
    _, results = patcher.apply_entries(data, entries)
    return PatchReport(True, root, target, results=results)


def apply_patch(root: Path, dictionary: dict, dict_source: str = "") -> PatchReport:
    target = bundle_js_path(root)
    if not target:
        return PatchReport(False, root, None, messages=["未找到 bundle.js"])

    rel_key = "lib/frontend/bundle.js"
    file_cfg = (dictionary.get("files") or {}).get(rel_key) or {}
    entries = file_cfg.get("entries") or []
    if not entries:
        return PatchReport(False, root, target, messages=["词典中没有 bundle.js 条目"])

    try:
        original = target.read_bytes()
        backup.ensure_backup(target)
        gz_target = target.with_name(target.name + ".gz")
        if gz_target.is_file():
            backup.ensure_backup(gz_target)

        patched, results = patcher.apply_entries(original, entries)
        ok_all = all(r.ok for r in results) and any(r.ok for r in results)
        if not any(r.replaced for r in results):
            # 全部未命中 → 可能已汉化
            already = all(r.found == 0 for r in results)
            msg = "已是汉化状态或全部未命中" if already else "没有任何条目被替换"
            return PatchReport(False, root, target, results=results, messages=[msg])

        if not ok_all:
            # 部分失败：仍写入成功的？为安全整文件回滚
            failed = [r for r in results if not r.ok]
            # 若有成功也有失败，采用「成功子集写入」更实用
            # 这里选择：写入已成功替换的结果（apply_entries 已处理跳过项）
            pass

        target.write_bytes(patched)
        if file_cfg.get("gz", True) and gz_target.is_file():
            gzip_sync.write_gz_from_bytes(patched, gz_target)

        backup.write_state(
            root,
            {
                "tool": "STM32CubeMX2-Chinese",
                "dictSource": dict_source,
                "dictVersion": dictionary.get("version"),
                "target": str(target),
                "sha1Before": backup.sha1_file(backup.backup_path(target)),
                "sha1After": backup.sha1_file(target),
                "replaced": sum(r.replaced for r in results),
                "failed": sum(1 for r in results if not r.ok),
            },
        )
        return PatchReport(True, root, target, results=results, messages=["汉化完成"])
    except OSError as e:
        # 尽力回滚
        rolled = backup.restore_from_backup(target)
        return PatchReport(
            False,
            root,
            target,
            messages=[f"写入失败: {e}", "已尝试回滚" if rolled else "回滚失败"],
            rolled_back=rolled,
        )


def rollback(root: Path) -> PatchReport:
    target = bundle_js_path(root)
    if not target:
        return PatchReport(False, root, None, messages=["未找到 bundle.js"])
    msgs: list[str] = []
    ok_js = backup.restore_from_backup(target)
    msgs.append("已恢复 bundle.js" if ok_js else "无 bundle.js.orig 备份")
    gz = target.with_name(target.name + ".gz")
    if gz.is_file() and backup.backup_path(gz).is_file():
        ok_gz = backup.restore_from_backup(gz)
        msgs.append("已恢复 bundle.js.gz" if ok_gz else "gz 恢复失败")
    backup.clear_state(root)
    return PatchReport(ok_js, root, target, messages=msgs)
