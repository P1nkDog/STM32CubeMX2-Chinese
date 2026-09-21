from __future__ import annotations

import gzip
from pathlib import Path


def write_gz_from_bytes(js_bytes: bytes, gz_path: Path, compresslevel: int = 9) -> int:
    gz_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(gz_path, "wb", compresslevel=compresslevel) as f:
        f.write(js_bytes)
    return gz_path.stat().st_size
