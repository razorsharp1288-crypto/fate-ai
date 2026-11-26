"""Render the FATE AI logo to assets/fate_ai.png and a multi-resolution assets/fate_ai.ico."""
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from fate_ai.ui.components.icons import logo_pixmap  # noqa: E402


def png_bytes(size: int) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    logo_pixmap(size).toImage().save(buf, "PNG")
    return bytes(ba)


def main() -> None:
    app = QGuiApplication([])  # noqa: F841
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    (out / "fate_ai.png").write_bytes(png_bytes(512))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [png_bytes(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    (out / "fate_ai.ico").write_bytes(header + entries + b"".join(images))
    print("wrote", out / "fate_ai.ico")


if __name__ == "__main__":
    main()
