"""Export committed Windows icon assets from the editable SVG without redrawing it."""

from __future__ import annotations

import os
from contextlib import ExitStack
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def _render_layer(renderer: QSvgRenderer, size: int) -> Image.Image:
    image = QImage(size, size, QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    return Image.frombytes("RGBA", (size, size), image.constBits().tobytes())


def export_icons(assets: Path) -> None:
    """Render the SVG to a transparent PNG and the standard Windows ICO sizes."""
    application = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(assets / "FileMind_AppIcon.svg"))
    if not renderer.isValid():
        raise ValueError("The application SVG is invalid.")
    # Render each vector size directly; raster downsampling can add alpha at corners.
    with ExitStack() as images:
        png = images.enter_context(_render_layer(renderer, 512))
        png.save(assets / "FileMind_AppIcon.png")
        frames = [images.enter_context(_render_layer(renderer, size))
                  for size in (16, 24, 32, 48, 64, 128, 256)]
        frames[-1].save(assets / "FileMind_AppIcon.ico", format="ICO",
                        sizes=[frame.size for frame in frames], append_images=frames[:-1])
    application.processEvents()


def main() -> None:
    """Refresh only this project's app icon exports, preserving the SVG source."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    assets = Path(__file__).resolve().parents[1] / "filemind/ui/assets"
    export_icons(assets)
    print("Exported transparent PNG and seven Windows ICO layers.")


if __name__ == "__main__":
    main()
