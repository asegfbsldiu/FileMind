"""Render native Inno Setup branding using the existing editable FileMind icon."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath
from PySide6.QtSvg import QSvgRenderer


LICENSE_INTRO = """FileMind 开源许可说明

FileMind 自有源码采用 MIT 许可证。

你可以使用、复制、修改、发布、分发、再许可或销售软件副本，
条件是保留著作权声明和许可声明。软件按“原样”提供，不附带担保。
上述中文为阅读提示，完整许可条款见下方英文原文。

随应用分发的 Qt、PDFium、FFmpeg 等组件保留各自许可证。
第三方清单及许可原文位于安装目录的 _internal\\THIRD_PARTY_NOTICES.txt
和 _internal\\THIRD_PARTY_LICENSES 文件夹中。

────────────────────────────────
MIT License — 完整许可原文
────────────────────────────────

"""


def _draw_waves(painter: QPainter) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    for vertical, opacity in ((242, 0.12), (280, 0.09)):
        wave = QPainterPath()
        wave.moveTo(0, vertical)
        wave.cubicTo(54, vertical - 38, 112, vertical + 62, 164, vertical - 10)
        wave.lineTo(164, 314)
        wave.lineTo(0, 314)
        wave.closeSubpath()
        painter.setBrush(QColor.fromRgbF(1, 1, 1, opacity))
        painter.drawPath(wave)


def _sidebar(renderer: QSvgRenderer, wordmark: QSvgRenderer) -> QImage:
    image = QImage(656, 1256, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(4, 4)
        gradient = QLinearGradient(0, 0, 164, 314)
        gradient.setColorAt(0, QColor("#4842C8"))
        gradient.setColorAt(0.6, QColor("#6553E8"))
        gradient.setColorAt(1, QColor("#8366ED"))
        painter.fillRect(QRectF(0, 0, 164, 314), gradient)
        _draw_waves(painter)
        renderer.render(painter, QRectF(40, 47, 84, 84))
        wordmark.render(painter, QRectF(0, 143, 164, 62))
    finally:
        painter.end()
    return image


def _small_icon(renderer: QSvgRenderer) -> QImage:
    image = QImage(232, 232, QImage.Format.Format_RGB32)
    image.fill(QColor("#FFFFFF"))
    painter = QPainter(image)
    try:
        renderer.render(painter, QRectF(16, 16, 200, 200))
    finally:
        painter.end()
    return image


def export_installer_assets(root: Path) -> None:
    """Write DPI-ready wizard BMPs and a notice retaining the full MIT license."""
    application = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(root / "filemind/ui/assets/FileMind_AppIcon.svg"))
    if not renderer.isValid():
        raise ValueError("FileMind's application SVG is invalid.")
    output = root / "packaging/installer"
    wordmark = QSvgRenderer(str(output / "wordmark.svg"))
    if not wordmark.isValid():
        raise ValueError("The outlined installer wordmark is invalid.")
    output.mkdir(parents=True, exist_ok=True)
    for name, image in (("wizard-sidebar.bmp", _sidebar(renderer, wordmark)),
                        ("wizard-small.bmp", _small_icon(renderer))):
        if not image.save(str(output / name), "BMP"):
            raise OSError(f"Could not save installer image: {name}")
    original_license = (root / "LICENSE").read_text("utf-8")
    (output / "LICENSE.zh-CN.txt").write_text(LICENSE_INTRO + original_license, "utf-8-sig")
    application.processEvents()


def main() -> None:
    """Refresh installer inputs without running either packaging program."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    export_installer_assets(Path(__file__).resolve().parents[1])
    print("Exported FileMind wizard artwork and Chinese license introduction.")


if __name__ == "__main__":
    main()
