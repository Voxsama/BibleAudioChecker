"""Render the repo's SVG logo into an Apple iconset."""

from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "logo.svg"
OUTPUT = ROOT / "icon.iconset"
SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise RuntimeError("Could not load %s" % SOURCE)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, size in SIZES.items():
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        if not pixmap.save(str(OUTPUT / name), "PNG"):
            raise RuntimeError("Could not write %s" % (OUTPUT / name))
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
