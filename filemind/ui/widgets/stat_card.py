"""Compact business-state statistic card."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from filemind.ui.widgets.card import Card


class StatCard(Card):
    """Display one live count and its concise label."""

    def __init__(self, label: str, value: str = "0", parent: QWidget | None = None):
        super().__init__(parent, padding=15)
        self.setMinimumWidth(120)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("font-size:21pt;font-weight:700;")
        self.label_label = QLabel(label)
        self.label_label.setObjectName("Muted")
        self.layout.addWidget(self.value_label)
        self.layout.addWidget(self.label_label)

    def set_value(self, value: int | str) -> None:
        """Display a current business count."""
        self.value_label.setText(str(value))
