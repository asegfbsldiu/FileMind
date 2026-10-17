"""Compact conversation metadata and the shared rounded action surface."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import (
    QColor, QFontMetrics, QHideEvent, QKeyEvent, QMouseEvent, QResizeEvent, QStandardItem, QStandardItemModel,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from filemind.ui.styles.icons import svg_icon
from filemind.ui.styles.theme import COLORS
from filemind.ui.widgets.combo_box import ComboPopup


ROW_HEIGHT = 52


class ConversationList(QListWidget):
    """Give conversation activation the same Return and Enter keys on every OS."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle confirmation once before platform-specific item-view bindings."""
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() in (Qt.KeyboardModifier.NoModifier,
                                          Qt.KeyboardModifier.KeypadModifier)):
            item = self.currentItem()
            if item is not None and not item.isHidden():
                self.itemActivated.emit(item)
            event.accept()
            return
        super().keyPressEvent(event)


def conversation_activity(updated_at: str, message_count: int, now: datetime | None = None) -> str:
    """Format local activity time without dropping older conversations."""
    try:
        updated = datetime.fromisoformat(updated_at).astimezone()
        current = (now or datetime.now().astimezone()).astimezone()
        days = (current.date() - updated.date()).days
        if days in {0, 1}:
            label = ("今天" if days == 0 else "昨天") + updated.strftime(" %H:%M")
        else:
            label = updated.strftime("%m-%d %H:%M" if updated.year == current.year else "%Y-%m-%d")
    except (ValueError, OverflowError):
        label = "时间未知"
    count = f"{message_count} 条消息" if message_count else "尚未发送消息"
    return f"{label} · {count}"


class ConversationRow(QFrame):
    """A readable two-line chat row with a lightweight, frameless action popup."""

    activated = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, conversation_id: str, title: str, parent: QWidget | None = None,
                 updated_at: str = "", message_count: int = 0) -> None:
        super().__init__(parent)
        self.conversation_id = conversation_id
        self.full_title = title
        self._action_popup: ComboPopup | None = None
        self.setObjectName("OrbitConversationRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 4, 5)
        layout.setSpacing(8)
        self.chat_icon = QLabel()
        self.chat_icon.setObjectName("OrbitConversationIcon")
        self.chat_icon.setFixedSize(28, 28)
        self.chat_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chat_icon.setPixmap(svg_icon("assistant", COLORS["purple"], 17).pixmap(17, 17))
        self.chat_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.chat_icon)
        layout.addLayout(self._build_text(title, updated_at, message_count), 1)
        self.more_button = QToolButton()
        self.more_button.setObjectName("OrbitConversationMore")
        self.more_button.setText("⋯")
        self.more_button.setToolTip("对话选项")
        self.more_button.setAccessibleName(f"对话选项：{title}")
        self.more_button.clicked.connect(self._show_menu)
        layout.addWidget(self.more_button)
        self.set_selected(False)
        self._elide_title()

    @property
    def action_popup(self) -> ComboPopup:
        """Allocate a native popup only when this conversation needs its menu."""
        if self._action_popup is None:
            self._build_menu()
        return self._action_popup

    def _build_text(self, title: str, updated_at: str, message_count: int) -> QVBoxLayout:
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        self.title_label = QLabel()
        self.title_label.setObjectName("OrbitConversationTitle")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setToolTip(title)
        self.activity_label = QLabel(conversation_activity(updated_at, message_count))
        self.activity_label.setObjectName("OrbitConversationActivity")
        self.activity_label.setTextFormat(Qt.TextFormat.PlainText)
        self.activity_label.setToolTip(self.activity_label.text())
        for label in (self.title_label, self.activity_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            text.addWidget(label)
        return text

    def _build_menu(self) -> None:
        # Reusing the model popup also avoids QMenu's native rectangular shadow.
        self._action_popup = ComboPopup(self)
        self.action_model = QStandardItemModel(self._action_popup)
        action = QStandardItem(svg_icon("trash", COLORS["danger"], 18), "删除对话")
        action.setEditable(False)
        action.setForeground(QColor(COLORS["danger"]))
        self.action_model.appendRow(action)
        view = self._action_popup.list_view
        view.setModel(self.action_model)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.clicked.connect(self._delete_from_menu)
        view.activated.connect(self._delete_from_menu)
        view.dismissed.connect(self._action_popup.hide)
        self._action_popup.closed.connect(self._menu_closed)

    def set_selected(self, selected: bool) -> None:
        """Refresh selection while retaining the list's keyboard navigation."""
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide_title()

    def hideEvent(self, event: QHideEvent) -> None:
        if self._action_popup is not None:
            self._action_popup.hide()
        super().hideEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.conversation_id)
        super().mouseReleaseEvent(event)

    def _elide_title(self) -> None:
        available = max(20, self.title_label.width())
        self.title_label.setText(QFontMetrics(self.title_label.font()).elidedText(
            self.full_title, Qt.TextElideMode.ElideRight, available))

    def _show_menu(self) -> None:
        if self.action_popup.isVisible():
            self.action_popup.hide()
            return
        popup = self.action_popup
        popup.setFixedSize(184, 52)
        anchor = self.more_button.mapToGlobal(self.more_button.rect().bottomRight())
        bounds = self.more_button.screen().availableGeometry()
        x = max(bounds.left() + 6, min(anchor.x() - popup.width(), bounds.right() - popup.width() - 5))
        y = anchor.y() + 4
        if y + popup.height() > bounds.bottom() - 6:
            y = self.more_button.mapToGlobal(QPoint()).y() - popup.height() - 4
        popup.move(x, max(bounds.top() + 6, y))
        popup.list_view.setCurrentIndex(self.action_model.index(0, 0))
        self.more_button.setDown(True)
        popup.show()
        popup.list_view.setFocus(Qt.FocusReason.PopupFocusReason)

    def _menu_closed(self) -> None:
        self.more_button.setDown(False)
        if self.isVisible():
            self.more_button.setFocus(Qt.FocusReason.PopupFocusReason)

    def _delete_from_menu(self, _index: object) -> None:
        self.action_popup.hide()
        self.delete_requested.emit(self.conversation_id)
