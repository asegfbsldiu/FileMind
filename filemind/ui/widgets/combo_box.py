"""Shared rounded combo popups without native menu frames or focus rectangles."""

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QHideEvent, QKeyEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QListView, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QVBoxLayout, QWidget,
)

from filemind.ui.styles.theme import COLORS


class ComboItemDelegate(QStyledItemDelegate):
    """Keep keyboard selection visible using the same rounded row as hover."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex) -> None:
        item = QStyleOptionViewItem(option)
        self.initStyleOption(item, index)
        selected = item.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver)
        painter.save()
        if selected:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS["primary_soft"]))
            painter.drawRoundedRect(item.rect.adjusted(3, 2, -3, -2), 7, 7)
        item.state &= ~(QStyle.StateFlag.State_HasFocus | QStyle.StateFlag.State_Selected |
                        QStyle.StateFlag.State_MouseOver)
        item.rect.adjust(8, 0, -8, 0)
        super().paint(painter, item, index)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width() + 22, max(36, size.height() + 14))


class ComboPopupView(QListView):
    """A regular item view with keyboard activation and no native menu delegate."""

    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ComboPopupList")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setItemDelegate(ComboItemDelegate(self))
        self.viewport().setAutoFillBackground(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.dismissed.emit()
            event.accept()
        elif event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.activated.emit(self.currentIndex())
            event.accept()
        else:
            super().keyPressEvent(event)


class ComboPopup(QWidget):
    """Own the popup surface so Qt's private menu panel cannot add a frame."""

    closed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.NoDropShadowWindowHint)
        self.setObjectName("ComboPopupWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.list_view = ComboPopupView(self)
        layout.addWidget(self.list_view)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(COLORS["card"]))
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 11, 11)

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self.closed.emit()


class StyledComboBox(QComboBox):
    """Reuse normal combo signals and keyboard navigation with a frameless popup."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaxVisibleItems(8)
        self._popup = ComboPopup(self)
        self._popup.list_view.clicked.connect(self._choose_item)
        self._popup.list_view.activated.connect(self._choose_item)
        self._popup.list_view.dismissed.connect(self.hidePopup)
        self._popup.closed.connect(self._reset_popup_state)

    def view(self) -> QListView:
        """Expose the actual popup list for inspection and keyboard navigation."""
        return self._popup.list_view

    def showPopup(self) -> None:
        """Open a rounded popup while retaining the standard selection behavior."""
        if not self.isEnabled() or not self.count():
            return
        view = self.view()
        view.setModel(self.model())
        view.setModelColumn(self.modelColumn())
        view.setIconSize(self.iconSize())
        view.setRootIndex(self.rootModelIndex())
        view.setCurrentIndex(self.model().index(self.currentIndex(), self.modelColumn(), self.rootModelIndex()))
        bounds = self._popup_bounds()
        self._popup.setFixedSize(bounds.size())
        self._popup.move(bounds.topLeft())
        self._popup.show()
        view.scrollTo(view.currentIndex())
        view.setFocus(Qt.FocusReason.PopupFocusReason)
        self.update()

    def _popup_bounds(self) -> QRect:
        screen = self.screen().availableGeometry()
        anchor = self.mapToGlobal(QPoint(0, self.height() + 4))
        row_height = self.view().sizeHintForRow(0)
        height = max(36, row_height) * min(self.count(), self.maxVisibleItems()) + 12
        text_width = max(self.fontMetrics().horizontalAdvance(self.itemText(index)) for index in range(self.count()))
        width = min(screen.width() - 12, max(self.width(), min(520, text_width + 68)))
        x = max(screen.left() + 6, min(anchor.x(), screen.right() - width - 5))
        if anchor.y() + height > screen.bottom() - 6:
            anchor.setY(self.mapToGlobal(QPoint()).y() - height - 4)
        y = max(screen.top() + 6, anchor.y())
        return QRect(x, y, width, min(height, screen.bottom() - y - 5))

    def _choose_item(self, index: QModelIndex) -> None:
        if not index.isValid() or not index.flags() & Qt.ItemFlag.ItemIsEnabled:
            return
        self.setCurrentIndex(index.row())
        self.activated.emit(index.row())
        self.textActivated.emit(self.itemText(index.row()))
        self.hidePopup()

    def hidePopup(self) -> None:
        """Dismiss the owned popup and reset the standard combo's internal state."""
        self._popup.hide()
        self._reset_popup_state()

    def _reset_popup_state(self) -> None:
        super().hidePopup()
        self.update()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange and not self.isEnabled() and hasattr(self, "_popup"):
            self.hidePopup()

    def hideEvent(self, event: QHideEvent) -> None:
        if hasattr(self, "_popup"):
            self.hidePopup()
        super().hideEvent(event)
