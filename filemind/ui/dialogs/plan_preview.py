"""Review a validated operation plan as a target tree and detail table."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QPushButton,
    QFrame,
    QSplitter,
    QTableView,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from filemind.models import OperationPlan
from filemind.ui.styles.icons import svg_icon
from filemind.ui.widgets.file_table import (CategoryDelegate, EXECUTE_COLUMN, FilePlanTableModel,
                                            STATUS_COLUMN, ExecutionDelegate, PlanStatusDelegate)
from filemind.ui.widgets.plan_tree import KIND_ROLE, PATH_ROLE, PlanTargetTree
from filemind.ui.widgets.plan_filter import PlanFilterModel


class PlanPreviewDialog(QDialog):
    """Show target folders and their corresponding validated operations."""

    execute_requested = Signal(object)
    rescan_requested = Signal()

    def __init__(self, plan: OperationPlan, source_model: FilePlanTableModel,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plan = plan
        self.setObjectName("PlanPreviewDialog")
        self.setWindowTitle("整理预览 · FileMind")
        self.setMinimumSize(860, 560)
        if parent is not None:
            self.resize(min(1120, max(860, parent.width() - 56)),
                        min(680, max(560, parent.height() - 76)))
        else:
            self.resize(1120, 680)
        self.source_model = source_model
        self.proxy_model = PlanFilterModel(self)
        self.proxy_model.setSourceModel(source_model)
        self.source_model.plan_changed.connect(self._plan_edited)
        self.source_model.edit_rejected.connect(self._edit_rejected)
        self.finished.connect(self._detach_model)
        self._build_ui()
        self._filter_table(self.tree.currentItem(), None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        self._build_header(layout)
        self._build_toolbar(layout)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.tree = PlanTargetTree(self.plan)
        self.tree.currentItemChanged.connect(self._filter_table)
        self.splitter.addWidget(self.tree)
        self._build_table()
        self._build_details_panel()
        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)
        detail_layout.addWidget(self.table, 1)
        detail_layout.addWidget(self.details_frame)
        self.splitter.addWidget(detail_panel)
        self.splitter.setSizes((280, max(480, self.width() - 340)))
        layout.addWidget(self.splitter, 1)
        self._build_actions(layout)
        self._update_summary()

    def _build_header(self, layout: QVBoxLayout) -> None:
        title_row = QHBoxLayout()
        self.header = QLabel(f"本次整理涉及 {len(self.plan.operations)} 个文件")
        self.header.setObjectName("PreviewTitle")
        title_row.addWidget(self.header, 1)
        self.preview_badge = QLabel("本地校验 · 尚未执行")
        self.preview_badge.setObjectName("PreviewBadge")
        title_row.addWidget(self.preview_badge)
        layout.addLayout(title_row)
        self.summary = QLabel()
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.notice = QLabel("这个计划没有需要整理的文件。可以关闭后选择其他目录。")
        self.notice.setObjectName("PreviewNotice")
        self.notice.setWordWrap(True)
        self.notice.setVisible(True)
        layout.addWidget(self.notice)

    def _build_toolbar(self, layout: QVBoxLayout) -> None:
        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索文件名、目标路径或整理理由")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._search_changed)
        toolbar.addWidget(self.search_edit, 1)
        expand = QPushButton("展开全部")
        collapse = QPushButton("折叠全部")
        expand.setIcon(svg_icon("folder_open"))
        collapse.setIcon(svg_icon("folder_plan"))
        expand.clicked.connect(lambda: self.tree.expandAll())
        collapse.clicked.connect(lambda: self.tree.collapseAll())
        toolbar.addWidget(expand)
        toolbar.addWidget(collapse)
        layout.addLayout(toolbar)

    def _build_table(self) -> None:
        self.table = QTableView()
        self.table.setObjectName("PlanDetailTable")
        self.table.setModel(self.proxy_model)
        self.table.setItemDelegateForColumn(4, CategoryDelegate(self.table))
        self.table.setItemDelegateForColumn(EXECUTE_COLUMN, ExecutionDelegate(self.table))
        self.table.setItemDelegateForColumn(STATUS_COLUMN, PlanStatusDelegate(self.table))
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.DoubleClicked
                                   | QTableView.EditTrigger.EditKeyPressed)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(42)
        for column in (0, 1, 5):
            self.table.setColumnHidden(column, True)
        for column, width in ((2, 145), (3, 145), (4, 80), (6, 60), (STATUS_COLUMN, 140)):
            self.table.setColumnWidth(column, width)
        self.table.setColumnWidth(EXECUTE_COLUMN, 52)
        header = self.table.horizontalHeader()
        header.moveSection(header.visualIndex(EXECUTE_COLUMN), 0)
        self.table.selectionModel().currentRowChanged.connect(self._show_selected_details)

    def _build_details_panel(self) -> None:
        self.details_frame = QFrame()
        self.details_frame.setObjectName("PlanChangeDetails")
        form = QFormLayout(self.details_frame)
        form.setContentsMargins(12, 10, 12, 10)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(5)
        heading = QLabel("文件详情")
        heading.setObjectName("PreviewDetailsTitle")
        form.addRow(heading)
        self.detail_original = self._add_detail_row(form, "原文件")
        self.detail_source = self._add_detail_row(form, "原路径")
        self.detail_target = self._add_detail_row(form, "目标路径")
        self.detail_classification = self._add_detail_row(form, "分类与理由")
        self.detail_operation = self._add_detail_row(form, "操作与校验")

    @staticmethod
    def _add_detail_row(form: QFormLayout, title: str) -> QLabel:
        label = QLabel("选择左侧文件或右侧列表查看完整信息。")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(title, label)
        return label

    def _update_summary(self) -> None:
        """Reflect the current rows, including skips the user just created."""
        operations = self.source_model.operations
        executable = [item for item in operations if not item.excluded and not item.warning]
        skipped = [item for item in operations if item.excluded or item.warning]
        self.header.setText(f"本次整理涉及 {len(operations)} 个文件")
        self.summary.setText(f"{len(executable)} 项将执行    {len(skipped)} 项将跳过    "
                             "尚未执行任何文件操作")
        self.notice.setText(self._notice_text(len(skipped), len(executable)))
        self.notice.setProperty("hasWarnings", bool(skipped))
        self.preview_badge.setText("含跳过项 · 尚未执行" if skipped else "本地校验 · 尚未执行")
        self._refresh_notice_style()
        self.execute_button.setEnabled(bool(executable))

    def _refresh_notice_style(self) -> None:
        """Re-apply the notice styling after its warning property changed."""
        style = self.notice.style()
        style.unpolish(self.notice)
        style.polish(self.notice)

    def _notice_text(self, skipped: int, executable: int) -> str:
        if not self.source_model.operations:
            return "这个计划没有需要整理的文件。可以关闭后选择其他目录。"
        if not executable:
            return "所有行都会被跳过，没有可执行的文件。可以重新扫描或修改规则后再试。"
        if skipped:
            return (f"有 {skipped} 项会跳过（目标冲突、符号链接或你排除的行），其余 {executable} 项照常处理。"
                    "取消勾选“执行”列可以跳过某一行，双击分类或文件名可以修改建议。")
        return "请检查原路径、目标位置和命名建议。双击分类或文件名可直接修改；确认后才会执行移动或重命名。"

    def _plan_edited(self) -> None:
        """Rebuild the destination tree and summary after one accepted edit."""
        current = self.source_model.current_plan()
        if current is not None:
            self.plan = current
        self.notice.setToolTip("")
        self._rebuild_tree()
        self._update_summary()

    def _edit_rejected(self, message: str) -> None:
        """Explain a refused edit; the row keeps its previous valid value."""
        self.notice.setText(f"这次修改没有应用：{message}")
        self.notice.setProperty("hasWarnings", True)
        self._refresh_notice_style()
        self.notice.setToolTip(message)

    def _detach_model(self, _result: int) -> None:
        """Closed previews must not retain subscriptions to later editing sessions."""
        self.source_model.plan_changed.disconnect(self._plan_edited)
        self.source_model.edit_rejected.disconnect(self._edit_rejected)

    def _rebuild_tree(self) -> None:
        """Replace the tree in place so the splitter position is preserved."""
        previous = self.tree
        position = self.splitter.indexOf(previous)
        self.tree = PlanTargetTree(self.plan)
        self.tree.currentItemChanged.connect(self._filter_table)
        replaced = self.splitter.replaceWidget(max(position, 0), self.tree)
        if replaced is not None:
            replaced.deleteLater()
        self.tree.expandToDepth(1)
        self._filter_table(self.tree.currentItem(), None)

    def _build_actions(self, layout: QVBoxLayout) -> None:
        actions = QHBoxLayout()
        self.rescan_button = QPushButton("重新扫描")
        self.rescan_button.setIcon(svg_icon("scan"))
        self.rescan_button.clicked.connect(self._request_rescan)
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.reject)
        self.execute_button = QPushButton("确认并整理")
        self.execute_button.setObjectName("PrimaryButton")
        self.execute_button.setEnabled(False)
        self.execute_button.setToolTip("跳过的行不会移动任何文件；确认后仍会再次校验并使用本地安全执行器。")
        self.execute_button.clicked.connect(self._request_execution)
        actions.addWidget(self.rescan_button)
        actions.addStretch(1)
        actions.addWidget(self.close_button)
        actions.addWidget(self.execute_button)
        layout.addLayout(actions)

    def _filter_table(self, item: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        relative_path = str(item.data(0, PATH_ROLE) or "") if item else ""
        target = self.plan.root / relative_path if relative_path else None
        self.proxy_model.set_target(target, bool(item and item.data(0, KIND_ROLE) == "file"))
        self._select_first_row()

    def _search_changed(self, query: str) -> None:
        self.proxy_model.set_query(query)
        self._select_first_row()

    def _select_first_row(self) -> None:
        if self.proxy_model.rowCount():
            self.table.setCurrentIndex(self.proxy_model.index(0, 2))
        else:
            self.detail_original.setText("当前筛选下没有文件。")
            for label in (self.detail_source, self.detail_target, self.detail_classification,
                          self.detail_operation):
                label.clear()

    def _show_selected_details(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        source_index = self.proxy_model.mapToSource(current)
        operation = self.source_model.operations[source_index.row()]
        self.detail_original.setText(operation.original_name)
        self.detail_source.setText(str(operation.source))
        self.detail_target.setText(str(operation.target))
        self.detail_classification.setText(
            f"{operation.classification.category} · {operation.classification.reason}"
        )
        action = _operation_label(operation.source, operation.target, operation.original_name, operation.new_name)
        state = "已排除，本次不会移动" if operation.excluded else operation.warning or "本地安全校验通过"
        self.detail_operation.setText(f"{action} · {state}")
        self.detail_source.setToolTip(str(operation.source))
        self.detail_target.setToolTip(str(operation.target))

    def _request_execution(self) -> None:
        plan = self.source_model.current_plan()
        if plan is None:
            return
        if not any(not item.excluded and not item.warning for item in plan.operations):
            return
        self.execute_requested.emit(plan)
        self.accept()

    def _request_rescan(self) -> None:
        self.rescan_requested.emit()
        self.accept()


def _operation_label(source: Path, target: Path, original_name: str, new_name: str) -> str:
    moved = source.parent != target.parent
    renamed = original_name != new_name
    if moved and renamed:
        return "移动并重命名"
    if moved:
        return "移动"
    if renamed:
        return "重命名"
    return "保持原位置"
