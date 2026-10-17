"""Targeted checks for application branding and release resource references."""

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QLabel

from filemind import __version__
from filemind.ui import branding
from tools.review_ui import build_review


def test_supplied_icon_has_required_windows_sizes_and_png_fallback(tmp_path: Path) -> None:
    with Image.open(branding.ASSETS_DIRECTORY / "FileMind_AppIcon.ico") as icon:
        assert {(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)} <= icon.ico.sizes()
    assert not branding.application_icon().pixmap(QSize(32, 32)).isNull()
    png = branding.ASSETS_DIRECTORY / "FileMind_AppIcon.png"
    (tmp_path / png.name).write_bytes(png.read_bytes())
    with patch.object(branding, "ASSETS_DIRECTORY", tmp_path):
        assert not branding.application_icon().isNull()


@pytest.mark.parametrize("size", [16, 24, 32, 48, 64, 128, 256])
def test_every_icon_layer_has_transparent_corners(size: int) -> None:
    """Prevent a flattened export background from reappearing in any ICO layer."""
    with Image.open(branding.ASSETS_DIRECTORY / "FileMind_AppIcon.ico") as icon:
        layer = icon.ico.getimage((size, size)).convert("RGBA")
        corners = ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1))
        assert all(layer.getpixel(corner)[3] == 0 for corner in corners)
        assert layer.getchannel("A").getextrema() == (0, 255)
    rendered = branding.application_icon().pixmap(QSize(size, size)).toImage()
    right, bottom = rendered.width() - 1, rendered.height() - 1
    assert all(rendered.pixelColor(*corner).alpha() == 0
               for corner in ((0, 0), (right, 0), (0, bottom), (right, bottom)))


def test_png_fallback_is_transparent_and_keeps_the_white_document() -> None:
    """Remove only the canvas background while preserving the actual logo."""
    with Image.open(branding.ASSETS_DIRECTORY / "FileMind_AppIcon.png") as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        corners = ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))
        assert all(rgba.getpixel(corner)[3] == 0 for corner in corners)
        assert rgba.getpixel((width // 2, height // 3)) == (255, 255, 255, 255)


def test_svg_source_has_no_opaque_canvas_background() -> None:
    """Keep future raster exports transparent at their vector source."""
    renderer = QSvgRenderer(str(branding.ASSETS_DIRECTORY / "FileMind_AppIcon.svg"))
    assert renderer.isValid()
    canvas = QImage(208, 208, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    assert all(canvas.pixelColor(*corner).alpha() == 0
               for corner in ((0, 0), (207, 0), (0, 207), (207, 207)))


def test_startup_identity_uses_shared_icon_and_version() -> None:
    application = QApplication.instance()
    previous = (application.applicationName(), application.applicationDisplayName(),
                application.applicationVersion(), application.windowIcon())
    try:
        with patch.object(branding, "_set_windows_app_id") as taskbar:
            branding.configure_application_identity(application)
        taskbar.assert_called_once()
        assert application.applicationName() == "FileMind"
        assert application.applicationVersion() == __version__
        expected = branding.application_icon().pixmap(32, 32).toImage()
        assert application.windowIcon().pixmap(32, 32).toImage() == expected
    finally:
        application.setApplicationName(previous[0])
        application.setApplicationDisplayName(previous[1])
        application.setApplicationVersion(previous[2])
        application.setWindowIcon(previous[3])


def test_main_window_sidebar_and_lock_screen_use_new_icon(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    expected = branding.application_icon().pixmap(32, 32).toImage()
    assert window.windowIcon().pixmap(32, 32).toImage() == expected
    mark = window.findChild(QLabel, "BrandMark")
    assert not mark.pixmap().isNull()
    assert mark.text() == ""
    lock_root = tmp_path / "lock-preview"
    lock_root.mkdir()
    lock, _ = build_review(lock_root, "setup")
    assert lock.windowIcon().pixmap(32, 32).toImage() == expected
    lock.close()
    window.close()


def test_installer_uses_same_icon_and_taskbar_identity() -> None:
    root = Path(__file__).parents[1]
    installer = (root / "packaging/FileMind.iss").read_text("utf-8")
    assert "FileMind_AppIcon.ico" in installer
    assert f'AppUserModelID: "{branding.APP_USER_MODEL_ID}"' in installer
    assert "UninstallDisplayIcon={app}\\FileMind.exe" in installer
    assert "dist\\FileMind\\*" in installer
    assert "[UninstallDelete]" not in installer
