"""Compact, actionable organizer guidance that disappears after import."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from filemind.ui.styles.icons import svg_icon


class OrganizerEmpty(QWidget):
    """Guide first import with real local directory selection."""

    choose_requested = Signal()
    read_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._selected = False
        self._scanned = False
        self.setObjectName("OrganizerEmpty")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(8)
        layout.addStretch(1)
        self.title = QLabel("让文件各归其位")
        self.title.setObjectName("EmptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        self.description = QLabel("选择一个本机文件夹，先核对文件清单，再生成整理建议。")
        self.description.setObjectName("Muted")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.description)
        self.action_button = QPushButton("选择文件夹")
        self.action_button.setObjectName("PrimaryButton")
        self.action_button.setIcon(svg_icon("folder"))
        self.action_button.clicked.connect(self._activate)
        layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignCenter)
        self._build_tiles(layout)
        layout.addStretch(1)
        self.set_selected(False)

    def _build_tiles(self, layout: QVBoxLayout) -> None:
        self.tile_widget = QWidget()
        self.tile_widget.setMinimumWidth(0)
        self.tile_widget.setMaximumWidth(700)
        self.tiles = QGridLayout(self.tile_widget)
        self.tiles.setContentsMargins(0, 0, 0, 0)
        self.tiles.setSpacing(10)
        self.tile_cards: list[QFrame] = []
        for index, (title, detail, tint, icon) in enumerate((
                ("文档与笔记", "PDF · Word · TXT", "blue", "document"),
                ("图片与素材", "PNG · JPEG · WebP", "mint", "image_file"),
                ("代码与项目", "Python · Java · C", "lavender", "code"),
                ("音频与视频", "MP3 · WAV · MP4", "amber", "document"))):
            tile = self._tile(title, detail, tint, icon)
            self.tile_cards.append(tile)
            self.tiles.addWidget(tile, index // 2, index % 2)
        self.tile_widget.hide()
        layout.addWidget(self.tile_widget, 0, Qt.AlignmentFlag.AlignHCenter)

    @staticmethod
    def _tile(title: str, description: str, tint: str, icon: str) -> QFrame:
        tile = QFrame()
        tile.setObjectName("CapabilityTile")
        tile.setProperty("tint", tint)
        row = QHBoxLayout(tile)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(9)
        graphic = QLabel()
        graphic.setPixmap(svg_icon(icon).pixmap(22, 22))
        graphic.setFixedSize(24, 24)
        row.addWidget(graphic)
        column = QVBoxLayout()
        column.setSpacing(3)
        label = QLabel(title)
        label.setObjectName("TileTitle")
        column.addWidget(label)
        subtitle = QLabel(description)
        subtitle.setObjectName("CapabilityDetail")
        column.addWidget(subtitle)
        row.addLayout(column, 1)
        return tile

    def set_selected(self, selected: bool, scanned: bool = False) -> None:
        """Distinguish selection from a completed scan of an empty folder."""
        self._selected, self._scanned = selected, scanned
        self.title.setText("这个目录暂无待整理文件" if selected and scanned else
                           "先看看这个文件夹" if selected else "让文件各归其位")
        self.description.setText("仅扫描所选目录第一层普通文件；可以选择其他文件夹。" if selected and scanned else
                                 "点击读取文件，核对名称、类型和修改时间；尚未请求 AI。" if selected else
                                 "选择本机文件夹 → 核对文件 → 生成建议 → 预览并确认。")
        self.action_button.setText("选择其他文件夹" if scanned else "读取文件" if selected else "选择文件夹")

    def _activate(self) -> None:
        if self._selected and not self._scanned:
            self.read_requested.emit()
        else:
            self.choose_requested.emit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        compact = self.height() < 340
        columns = 4 if compact and self.width() >= 600 else 2
        self.tile_widget.setVisible(self.height() >= 230)
        while self.tiles.count():
            self.tiles.takeAt(0)
        for index, tile in enumerate(self.tile_cards):
            tile.findChild(QLabel, "CapabilityDetail").setVisible(not compact)
            self.tiles.addWidget(tile, index // columns, index % columns)
