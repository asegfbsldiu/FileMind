"""Clear, compact empty-state presentation."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from filemind.ui.styles.icons import svg_icon


class EmptyState(QWidget):
    """Show a short icon, title, and explanation when a view has no data."""

    def __init__(self, title: str, message: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        self.icon = QLabel()
        self.icon.setObjectName("EmptyIcon")
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setPixmap(svg_icon("spark", "#A5B4FC", 36).pixmap(36, 36))
        self.title = QLabel(title)
        self.title.setStyleSheet("font-size:12pt;font-weight:600;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message = QLabel(message)
        self.message.setObjectName("Muted")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        layout.addWidget(self.icon)
        layout.addWidget(self.title)
        layout.addWidget(self.message)

    def set_message(self, title: str, message: str) -> None:
        """Update the empty-state text without replacing the widget."""
        self.title.setText(title)
        self.message.setText(message)
