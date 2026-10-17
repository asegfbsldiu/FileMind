"""Local-only avatar rendering for the single-user account menu."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPixmap, QResizeEvent
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from filemind.ui.styles.icons import svg_icon


class LocalAccountButton(QPushButton):
    """Keep long local names readable without widening the sidebar."""

    def __init__(self, user_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LocalAccountButton")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(52)
        self.set_user_name(user_name)

    def set_user_name(self, user_name: str) -> None:
        """Keep the full name available to tooltips and accessibility tools."""
        self._user_name = user_name
        self.setAccessibleName(f"{user_name} · 本机账户、设置与锁屏")
        self.setToolTip(f"{user_name}\n应用级本地锁屏 · 当前设备")
        self._update_name()

    def _update_name(self) -> None:
        available = max(30, self.width() - 90)
        label = self.fontMetrics().elidedText(self._user_name, Qt.TextElideMode.ElideRight, available)
        self.setText(label.replace("&", "&&"))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_name()


def avatar_icon(path: Path | None, size: int = 32) -> QIcon:
    """Render only the app-owned thumbnail inside a circular mask."""
    if path is None:
        return svg_icon("user", "#7C5CE7", max(64, size * 2))
    source = QPixmap(str(path))
    if source.isNull():
        return svg_icon("user", size=max(64, size * 2))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(0, 0, size * 2, size * 2)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, source.scaled(size * 2, size * 2,
                                         Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                         Qt.TransformationMode.SmoothTransformation))
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
