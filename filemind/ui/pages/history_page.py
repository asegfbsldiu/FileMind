"""Operation history and guarded undo controls."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStackedWidget, QTableView, QWidget, QVBoxLayout,
)

from filemind.models import OperationRecord
from filemind.ui.widgets.card import Card
from filemind.ui.widgets.empty_state import EmptyState


HISTORY_HEADERS = ("操作时间", "文件数量", "执行结果", "撤销状态")


class HistoryTableModel(QAbstractTableModel):
    """Present persisted operation records without embedding logic in cells."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records: list[OperationRecord] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(HISTORY_HEADERS)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.records):
            return None
        record = self.records[index.row()]
        succeeded = sum(item.get("status") == "success" for item in record.operations)
        failed = sum(item.get("status") == "failed" for item in record.operations)
        skipped = sum(item.get("status") == "skipped" for item in record.operations)
        if role == Qt.ItemDataRole.DisplayRole:
            values = (
                record.created_at[:19].replace("T", " "),
                str(len(record.operations)),
                f"成功 {succeeded} · 跳过 {skipped} · 失败 {failed}",
                "已全部撤销" if record.undone else self._undo_state(record),
            )
            return values[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._record_tooltip(record)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HISTORY_HEADERS[section]
        return None

    def set_records(self, records: list[OperationRecord]) -> None:
        self.beginResetModel()
        self.records = records
        self.endResetModel()

    @staticmethod
    def _undo_state(record: OperationRecord) -> str:
        successful = [item for item in record.operations if item.get("status") == "success"]
        if any(item.get("undo_status") == "success" for item in successful):
            return "部分撤销"
        return "可撤销" if successful else "无可撤销项目"

    @staticmethod
    def _record_tooltip(record: OperationRecord) -> str:
        errors = [str(item.get("error") or item.get("undo_error")) for item in record.operations
                  if item.get("error") or item.get("undo_error")]
        errors.extend(f"跳过：{item['skip_reason']}" for item in record.operations if item.get("skip_reason"))
        return "\n".join(errors) if errors else f"整理目录：{record.root}"


class HistoryPage(QWidget):
    """Display history records for the currently selected folder."""

    refresh_requested = Signal()
    undo_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        card = Card()
        toolbar = QHBoxLayout()
        self.context_label = QLabel("先在文件整理页选择一个文件夹。")
        self.context_label.setObjectName("Muted")
        self.context_label.setMinimumWidth(0)
        self.context_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(self.context_label, 1)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        toolbar.addWidget(self.refresh_button)
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        toolbar.addWidget(self.cancel_button)
        self.undo_button = QPushButton("撤销选中记录")
        self.undo_button.setObjectName("PrimaryButton")
        self.undo_button.clicked.connect(self._undo_selected)
        toolbar.addWidget(self.undo_button)
        card.layout.addLayout(toolbar)
        self.table_model = HistoryTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 230)
        card.layout.addWidget(self.table, 1)
        self.empty_state = EmptyState("还没有操作历史", "执行整理后，操作记录会保存在所选目录的 .filemind 文件夹中。")
        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self.empty_state)
        self.page_stack.addWidget(card)
        layout.addWidget(self.page_stack, 1)
        self.undo_button.setEnabled(False)
        self.table.selectionModel().selectionChanged.connect(self._update_undo_state)

    def set_records(self, records: list[OperationRecord], folder: str = "") -> None:
        """Refresh the table and its empty state for a selected directory."""
        self.table_model.set_records(records)
        self.context_label.setText(folder or "先在文件整理页选择一个文件夹。")
        self.context_label.setToolTip(folder)
        self.page_stack.setCurrentIndex(1 if records else 0)
        self._update_undo_state()

    def _update_undo_state(self, *_args) -> None:
        selected = self.table.selectionModel().selectedRows()
        record = self.table_model.records[selected[0].row()] if selected else None
        can_undo = bool(record and not record.undone and any(
            item.get("status") == "success" and item.get("undo_status") != "success"
            for item in record.operations))
        self.undo_button.setEnabled(can_undo)

    def _undo_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if selected:
            record = self.table_model.records[selected[0].row()]
            self.undo_requested.emit(record.operation_id)

