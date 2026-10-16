"""Explicit local conversion flow: choose, inspect, convert and reveal result."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Callable

from PySide6.QtCore import Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from filemind.conversion.models import ConversionInput, ConversionResult
from filemind.conversion.service import convert_file, inspect_input
from filemind.ui.styles.icons import svg_icon
from filemind.ui.widgets.card import Card
from filemind.ui.workers import TaskWorker
from filemind.ui.widgets.format_cards import FormatCards


ConversionTask = Callable[[Callable[[int, int], None], Event], object]
CompletionCallback = Callable[[object], None]


class FileDropZone(QFrame):
    """Accept a single explicitly dropped local file, never a remote URL."""

    file_dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ConversionDropZone")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if self.isEnabled() and len(urls) == 1 and urls[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if self.isEnabled() and len(urls) == 1 and urls[0].isLocalFile():
            self.file_dropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()


class ConversionPage(QWidget):
    """Use background local adapters with explicit capabilities and cancellation."""

    job_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: TaskWorker | None = None
        self.input_info: ConversionInput | None = None
        self.result: ConversionResult | None = None
        self._build_ui()
        self._update_actions()

    @property
    def is_busy(self) -> bool:
        """Let the shell wait for safe cancellation before locking or closing."""
        return self._worker is not None

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("ConversionScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        steps = QLabel("选择文件    →    识别格式    →    本地转换    →    查看结果")
        steps.setObjectName("ConversionSteps")
        steps.setWordWrap(True)
        layout.addWidget(steps)
        workspace = QHBoxLayout()
        workspace.setSpacing(16)
        workspace.addWidget(self._build_drop_zone(), 3)
        workspace.addWidget(self._build_options(), 2)
        layout.addLayout(workspace, 1)
        layout.addWidget(self._build_capabilities())
        layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    def _build_drop_zone(self) -> FileDropZone:
        self.drop_zone = FileDropZone()
        column = QVBoxLayout(self.drop_zone)
        column.setContentsMargins(22, 28, 22, 28)
        column.setSpacing(14)
        icon = QLabel()
        icon.setPixmap(svg_icon("convert", "#7C5CE7", 64).pixmap(64, 64))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addStretch(1)
        column.addWidget(icon)
        title = QLabel("把文件交给 FileMind")
        title.setObjectName("ConversionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(title)
        self.file_label = QLabel("拖入一个文件，或点击下方按钮选择")
        self.file_label.setTextFormat(Qt.TextFormat.PlainText)
        self.file_label.setWordWrap(True)
        self.file_label.setMinimumWidth(0)
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.file_label)
        self.choose_button = QPushButton("选择本机文件")
        self.choose_button.setObjectName("PrimaryButton")
        self.choose_button.clicked.connect(self._pick_file)
        column.addWidget(self.choose_button, 0, Qt.AlignmentFlag.AlignCenter)
        column.addStretch(1)
        self.drop_zone.file_dropped.connect(self.select_file)
        return self.drop_zone

    def _build_options(self) -> Card:
        card = Card()
        card.setMinimumWidth(240)
        card.layout.addWidget(QLabel("目标格式"))
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(0)
        self.target_combo.addItem("先选择文件")
        self.target_combo.currentIndexChanged.connect(self._target_changed)
        card.layout.addWidget(self.target_combo)
        self.target_note = QLabel("只显示本机已实现、当前文件可用的目标。")
        self.target_note.setObjectName("Muted")
        self.target_note.setWordWrap(True)
        card.layout.addWidget(self.target_note)
        self.convert_button = QPushButton("开始转换并保存…")
        self.convert_button.setObjectName("PrimaryButton")
        self.convert_button.clicked.connect(self._choose_output)
        card.layout.addWidget(self.convert_button)
        self.cancel_button = QPushButton("取消转换")
        self.cancel_button.clicked.connect(self.cancel)
        card.layout.addWidget(self.cancel_button)
        self.progress = QProgressBar()
        card.layout.addWidget(self.progress)
        self.status_label = QLabel("文件在本机处理，不会上传到模型服务。")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        card.layout.addWidget(self.status_label)
        self.output_label = QLabel()
        self.output_label.setWordWrap(True)
        self.output_label.setTextFormat(Qt.TextFormat.PlainText)
        self.output_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.layout.addWidget(self.output_label)
        self.open_result_button = QPushButton("打开输出位置")
        self.open_result_button.clicked.connect(self._open_result)
        card.layout.addWidget(self.open_result_button)
        card.layout.addStretch(1)
        return card

    def _build_capabilities(self) -> QWidget:
        return FormatCards()

    def _pick_file(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(self, "选择要转换的本机文件")
        if filename:
            self.select_file(filename)

    def select_file(self, filename: str) -> None:
        """Inspect one user-selected input on a worker without reading other files."""
        if self.is_busy:
            return
        self.input_info = None
        self.result = None
        self.output_label.clear()
        self.file_label.setText(Path(filename).name)
        self.file_label.setToolTip(filename)

        def inspect(_progress: Callable[[int, int], None], cancel: Event) -> ConversionInput:
            if cancel.is_set():
                raise InterruptedError("识别已取消")
            result = inspect_input(Path(filename))
            if cancel.is_set():
                raise InterruptedError("识别已取消")
            return result

        self._start(inspect, self._inspected, "正在本机识别输入格式…")

    def _inspected(self, result: object) -> None:
        if not isinstance(result, ConversionInput):
            return
        self.input_info = result
        self.target_combo.clear()
        for target in result.targets:
            self.target_combo.addItem(target.title, target.key)
        self.status_label.setText(result.description)
        self._target_changed()

    def _target_changed(self, *_args: object) -> None:
        if self.input_info:
            target = next((item for item in self.input_info.targets if item.key == self.target_combo.currentData()), None)
            self.target_note.setText(target.note if target else "请选择可用目标格式。")
        self._update_actions()

    def _choose_output(self) -> None:
        if not self.input_info or self.is_busy:
            return
        target = next((item for item in self.input_info.targets if item.key == self.target_combo.currentData()), None)
        if target is None:
            return
        suggested = self.input_info.path.with_name(f"{self.input_info.path.stem}.converted{target.extension}")
        filename, _filter = QFileDialog.getSaveFileName(self, "选择新的输出文件（不覆盖）", str(suggested),
                                                       f"{target.title} (*{target.extension})",
                                                       options=QFileDialog.Option.DontConfirmOverwrite)
        if filename:
            self.start_conversion(Path(filename))
        else:
            self.status_label.setText("已取消选择输出位置，未执行转换。")

    def start_conversion(self, output: Path) -> None:
        """Convert only after a valid target and explicit save destination exist."""
        if self.input_info is None or self.is_busy:
            return
        item, key = self.input_info, str(self.target_combo.currentData())
        self.result = None
        self.output_label.clear()
        self._start(lambda progress, cancel: convert_file(item, key, output, progress, cancel),
                    self._converted, "正在本机转换，源文件保持不变…")

    def _converted(self, result: object) -> None:
        if isinstance(result, ConversionResult):
            self.result = result
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.status_label.setText(f"转换完成 · {result.target_title} · {result.bytes_written:,} B")
            self.output_label.setText(str(result.output))
            self.output_label.setToolTip(str(result.output))

    def _start(self, task: ConversionTask, completed: CompletionCallback, message: str) -> None:
        self._worker = TaskWorker(task)
        worker = self._worker
        worker.signals.progress.connect(self._progress_changed)
        worker.signals.completed.connect(lambda value: self._done(worker, completed, value))
        worker.signals.failed.connect(lambda error: self._failed(worker, error))
        worker.signals.cancelled.connect(lambda error: self._failed(worker, error))
        self.status_label.setText(message)
        self.progress.setRange(0, 0)
        self._update_actions()
        QThreadPool.globalInstance().start(worker)

    def _progress_changed(self, completed: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(completed)

    def _done(self, worker: TaskWorker, callback: CompletionCallback, result: object) -> None:
        if self._worker is not worker:
            return
        self._worker = None
        callback(result)
        self._update_actions()
        self.job_finished.emit()

    def _failed(self, worker: TaskWorker, message: str) -> None:
        if self._worker is not worker:
            return
        self._worker = None
        self.status_label.setText(message)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._update_actions()
        self.job_finished.emit()

    def _update_actions(self) -> None:
        busy = self.is_busy
        self.choose_button.setEnabled(not busy)
        self.drop_zone.setEnabled(not busy)
        self.target_combo.setEnabled(not busy and self.input_info is not None)
        valid = self.input_info and any(target.key == self.target_combo.currentData() for target in self.input_info.targets)
        self.convert_button.setEnabled(not busy and bool(valid))
        self.cancel_button.setEnabled(busy)
        self.open_result_button.setEnabled(not busy and self.result is not None)

    def cancel(self) -> None:
        """Request cooperative cancellation before the output publication boundary."""
        if self._worker:
            self._worker.cancel()
            self.status_label.setText("已请求取消，正在等待安全停止点…")

    def _open_result(self) -> None:
        if self.result and self.result.output.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.output.parent)))
