"""Responsive pastel format cards with explicit implementation states."""

from html import escape

from PySide6.QtCore import QThreadPool, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from filemind.conversion.capabilities import FormatCapability, capabilities
from filemind.ui.workers import TaskWorker


class FormatCards(QWidget):
    """Show concrete local capabilities and limitations instead of format claims."""

    discovery_finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("FormatCapabilities")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(14)
        title = QLabel("本机可用格式")
        title.setObjectName("FormatSectionTitle")
        root.addWidget(title)
        self.note = QLabel("选择文件后仅显示对应目标；格式列表用逗号分隔，源文件始终保留。")
        self.note.setObjectName("FormatSectionNote")
        self.note.setWordWrap(True)
        root.addWidget(self.note)
        self.grid = QGridLayout()
        root.addLayout(self.grid)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.cards = [self._card(item) for item in capabilities()]
        self._columns = 0
        self._reflow()
        self.is_discovering = True
        self._discovery = TaskWorker(lambda _progress, _cancel: capabilities(detect_codecs=True))
        self._discovery.signals.completed.connect(self._set_capabilities)
        self._discovery.signals.failed.connect(self._discovery_failed)
        QThreadPool.globalInstance().start(self._discovery)

    def cancel_discovery(self) -> None:
        """Keep the shell open until the bounded local codec probe returns."""
        if self.is_discovering:
            self._discovery.cancel()

    def _set_capabilities(self, result: object) -> None:
        if not isinstance(result, tuple) or not all(isinstance(item, FormatCapability) for item in result):
            return
        while self.grid.count():
            self.grid.takeAt(0)
        for card in self.cards:
            card.deleteLater()
        self.cards = [self._card(item) for item in result]
        self._columns = 0
        self._reflow()
        self.is_discovering = False
        self.discovery_finished.emit()

    def _discovery_failed(self, _message: str) -> None:
        self.note.setText("音视频编码器检查失败，已隐藏相关卡片；其他格式仍可本机转换。")
        self._set_capabilities(tuple(item for item in capabilities() if item.title not in {"音频", "视频"}))

    @staticmethod
    def _card(item: FormatCapability) -> QFrame:
        card = QFrame()
        card.setMinimumWidth(0)
        card.setObjectName("CapabilityTile")
        card.setProperty("tint", item.tint)
        column = QVBoxLayout(card)
        column.setContentsMargins(18, 18, 18, 18)
        column.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel(item.title)
        title.setObjectName("TileTitle")
        title.setWordWrap(True)
        top.addWidget(title, 1)
        state = QLabel(item.state)
        state.setObjectName("CapabilityState")
        state.setWordWrap(True)
        # Long state labels belong below the title, keeping narrow cards readable.
        column.addLayout(top)
        column.addWidget(state)
        for prefix, text in (("输入", item.inputs), ("输出", item.outputs), ("", item.detail)):
            label = QLabel(f"<b>{prefix}：</b>{escape(text)}" if prefix else escape(text))
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setObjectName("CapabilityDetail")
            label.setProperty("formatList", bool(prefix))
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            column.addWidget(label)
        column.addStretch(1)
        return card

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self) -> None:
        columns = 5 if self.width() >= 1450 else 4 if self.width() >= 1150 else 3 if self.width() >= 850 else 2 if self.width() >= 530 else 1
        if columns == self._columns:
            return
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(5):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
        self._columns = columns
