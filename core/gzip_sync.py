from __future__ import annotations

import gzip
from pathlib import Path

from .backup import replace_into


def write_gz_from_bytes(js_bytes: bytes, gz_path: Path, compresslevel: int = 9) -> int:
    gz_path.parent.mkdir(parents=True, exist_ok=True)

    def fill(tmp: Path) -> None:
        # 写的是临时文件，但 gzip 头里的原始文件名仍按 gz_path 记（bundle.js）
        with open(tmp, "wb") as raw, gzip.GzipFile(
            filename=gz_path.name, mode="wb", compresslevel=compresslevel, fileobj=raw
        ) as f:
            f.write(js_bytes)

    replace_into(gz_path, fill)
    return gz_path.stat().st_size
