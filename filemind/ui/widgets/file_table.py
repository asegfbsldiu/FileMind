"""Qt model/view table with reviewed per-row edits and a category badge delegate."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from filemind.core.plan_editor import PlanEditor
from filemind.models import OperationPlan, PlannedOperation


HEADERS = ("原路径", "目标路径", "原文件名", "建议新文件名", "分类", "整理理由", "来源", "校验状态", "执行")
NAME_COLUMN = 3
CATEGORY_COLUMN = 4
STATUS_COLUMN = 7
EXECUTE_COLUMN = 8
EDITABLE_COLUMNS = (NAME_COLUMN, CATEGORY_COLUMN)
CATEGORY_COLORS = {"文档": "#EEF2FF", "图片": "#F3E8FF", "视频": "#E0F2FE", "其他": "#F1F5F9"}


class FilePlanTableModel(QAbstractTableModel):
    """Expose a validated plan and accept the user's per-row corrections."""

    plan_changed = Signal()
    edit_rejected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.operations: tuple[PlannedOperation, ...] = ()
        self.editor: PlanEditor | None = None

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.operations)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(HEADERS)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.operations):
            return None
        operation = self.operations[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_data(operation, index.column())
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == EXECUTE_COLUMN:
            return Qt.CheckState.Unchecked if operation.excluded else Qt.CheckState.Checked
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(operation, index.column())
        if role == Qt.ItemDataRole.ForegroundRole:
            if operation.excluded:
                return QColor("#94A3B8")
            if operation.warning:
                return QColor("#D97706")
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in (CATEGORY_COLUMN, EXECUTE_COLUMN):
            return Qt.AlignmentFlag.AlignCenter
        return None

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        if index.isValid() and self.editor is not None:
            if index.column() in EDITABLE_COLUMNS:
                flags |= Qt.ItemFlag.ItemIsEditable
            elif index.column() == EXECUTE_COLUMN:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        """Apply one reviewed edit; an unsafe value is refused and explained."""
        if not index.isValid() or self.editor is None or index.row() >= len(self.operations):
            return False
        source = self.operations[index.row()].source
        column = index.column()
        try:
            if role == Qt.ItemDataRole.CheckStateRole and column == EXECUTE_COLUMN:
                self.editor.set_excluded(source, Qt.CheckState(value) == Qt.CheckState.Unchecked)
            elif role == Qt.ItemDataRole.EditRole and column == CATEGORY_COLUMN:
                self.editor.set_category(source, str(value))
            elif role == Qt.ItemDataRole.EditRole and column == NAME_COLUMN:
                self.editor.set_new_name(source, str(value))
            else:
                return False
            self._apply()
        except ValueError as error:
            self._rollback()
            self.edit_rejected.emit(str(error))
            return False
        return True

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def set_plan(self, plan: OperationPlan | None) -> None:
        """Replace preview rows from a complete plan and start a fresh edit session."""
        self.beginResetModel()
        self.operations = plan.operations if plan else ()
        self.editor = PlanEditor(plan) if plan else None
        self.endResetModel()

    def current_plan(self) -> OperationPlan | None:
        """Return the plan including this session's edits, if a plan is loaded."""
        if self.editor is None:
            return None
        return OperationPlan(self.editor.root, self.operations)

    def _apply(self) -> None:
        """Recompute targets for all rows and notify the views."""
        plan = self.editor.build()
        self.beginResetModel()
        self.operations = plan.operations
        self.endResetModel()
        self.plan_changed.emit()

    def _rollback(self) -> None:
        """Restore the last accepted plan after a rejected change."""
        if self.editor is not None:
            self.set_plan(OperationPlan(self.editor.root, self.operations))

    def _display_data(self, operation: PlannedOperation, column: int) -> str:
        values = (str(operation.source), str(operation.target), operation.original_name, operation.new_name,
                  operation.classification.category, operation.classification.reason,
                  operation.classification.source, self._status_text(operation), "")
        return values[column]

    def _status_text(self, operation: PlannedOperation) -> str:
        if operation.excluded:
            return "已排除，不会移动"
        return operation.warning or "通过"

    def _tooltip(self, operation: PlannedOperation, column: int) -> str:
        if column == 0:
            return str(operation.source)
        if column == 1:
            return str(operation.target)
        if column == 5:
            return operation.classification.reason
        if column == STATUS_COLUMN:
            if operation.excluded:
                return "这一行已被排除，本次不会移动该文件"
            return operation.warning or "本地安全校验通过；尚未执行"
        if column == EXECUTE_COLUMN:
            return "取消勾选可跳过这一行，不会移动该文件"
        if column in EDITABLE_COLUMNS:
            return "双击可直接修改；分类和文件名会立即重新校验"
        return self._display_data(operation, column)


class CategoryDelegate(QStyledItemDelegate):
    """Draw category cells as soft pills without replacing the model data."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index.column() != CATEGORY_COLUMN or option.state & QStyle.StateFlag.State_Editing:
            super().paint(painter, option, index)
            return
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        background = CATEGORY_COLORS.get(text, "#F1F5F9")
        rect = option.rect.adjusted(12, 8, -12, -8)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QColor("#475569"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
