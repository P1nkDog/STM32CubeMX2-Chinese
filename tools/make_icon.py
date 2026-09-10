"""把 PNG 图标转换为多尺寸 .ico（用于 PyInstaller --icon）。

用法:
    python tools/make_icon.py <源.png> [输出.ico]

默认输出到 <项目根>/icon/icon.ico。源图建议为正方形、带透明通道的 PNG。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "icon" / "icon.ico"

# Windows 图标标准尺寸（256 由 Pillow 以 PNG 形式内嵌）
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def alpha_stats(im: Image.Image) -> tuple[int, int]:
    """返回 (完全不透明像素数, 全透明像素数)。"""
    alpha = im.getchannel("A")
    hist = alpha.histogram()
    opaque = sum(hist[254:])
    transparent = hist[0]
    return opaque, transparent


def make_icon(src: Path, out: Path) -> None:
    im = Image.open(src)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    w, h = im.size
    if w != h:
        print(f"[警告] 图片不是正方形 ({w}x{h})，将按正方形裁切")
        side = min(w, h)
        im = im.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))

    opaque, transparent = alpha_stats(im)
    total = im.width * im.height
    print(f"源图: {src.name} {im.size} RGBA")
    print(f"Alpha: 不透明 {opaque} ({opaque / total * 100:.0f}%), "
          f"全透明 {transparent} ({transparent / total * 100:.0f}%)")

    # 统一缩放到 256，再让 Pillow 生成各尺寸
    im256 = im.resize((256, 256), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    im256.save(out, format="ICO", sizes=SIZES)
    print(f"已生成: {out} ({out.stat().st_size} 字节, 尺寸 {SIZES})")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    if not src.is_file():
        print(f"[错误] 源文件不存在: {src}")
        return 1
    try:
        make_icon(src, out)
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 转换失败: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
