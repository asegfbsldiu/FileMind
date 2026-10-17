"""Imported files and checked destination plans share the main work area."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QSplitter, QTableView, QTabWidget,
    QVBoxLayout, QWidget, QStackedWidget,
)

from filemind.models import OperationPlan
from filemind.ui.widgets.plan_filter import PlanFilterModel
from filemind.ui.widgets.file_table import (
    CATEGORY_COLUMN, EXECUTE_COLUMN, STATUS_COLUMN, CategoryDelegate,
    FilePlanTableModel, PlanStatusDelegate,
)
from filemind.ui.widgets.imported_files import ImportedFilesModel
from filemind.ui.widgets.plan_tree import KIND_ROLE, PATH_ROLE, PlanTargetTree
from filemind.ui.widgets.organizer_empty import OrganizerEmpty


def configure_file_view(view: QTableView) -> None:
    """Keep metadata tables usable with long Chinese names and narrow windows."""
    view.setShowGrid(False)
    view.setAlternatingRowColors(True)
    view.setWordWrap(False)
    view.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.verticalHeader().hide()
    view.verticalHeader().setDefaultSectionSize(36)
    view.horizontalHeader().setStretchLastSection(True)


class OrganizationWorkspace(QTabWidget):
    """Browse imported metadata first, then inspect locally checked suggestions."""

    choose_requested = Signal()
    read_requested = Signal()

    def __init__(self, imports: ImportedFilesModel, plans: FilePlanTableModel) -> None:
        super().__init__()
        self.setObjectName("OrganizationWorkspace")
        self.imports_view = QTableView()
        self.imports_view.setModel(imports)
        configure_file_view(self.imports_view)
        self.imports_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.import_stack = QStackedWidget()
        self.import_empty = OrganizerEmpty()
        self._selected = False
        self._scanned = False
        self.import_empty.choose_requested.connect(self.choose_requested.emit)
        self.import_empty.read_requested.connect(self.read_requested.emit)
        self.import_stack.addWidget(self.import_empty)
        self.import_stack.addWidget(self.imports_view)
        self.addTab(self.import_stack, "导入文件 · 整理前")
        imports.modelReset.connect(self._refresh_import_content)
        self.target_page = QWidget()
        self.target_layout = QVBoxLayout(self.target_page)
        self.target_layout.setContentsMargins(0, 0, 0, 0)
        self.empty = QLabel("先读取目录中的文件，再生成规则或 AI 整理建议。")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setMargin(24)
        self.empty.setObjectName("Muted")
        self.target_layout.addWidget(self.empty)
        self.addTab(self.target_page, "目标目录 · 待确认")
        self.plans = plans
        self.target_tree: PlanTargetTree | None = None
        self.splitter: QSplitter | None = None

    def set_import_state(self, selected: bool, *, scanned: bool | None = None) -> None:
        """Keep guidance out of the way once real metadata exists."""
        self._selected = selected
        if scanned is not None:
            self._scanned = scanned
        self._refresh_import_content()

    def _refresh_import_content(self) -> None:
        self.import_empty.set_selected(self._selected, self._scanned)
        populated = bool(self.imports_view.model().rowCount())
        self.import_stack.setCurrentWidget(self.imports_view if populated else self.import_empty)

    def set_plan(self, plan: OperationPlan | None) -> None:
        """Replace only the plan view; imported file metadata remains visible."""
        if self.splitter is not None:
            self.target_layout.removeWidget(self.splitter)
            self.splitter.deleteLater()
            self.splitter = None
        self.target_tree = None
        self.empty.setVisible(plan is None or not plan.operations)
        if plan is None or not plan.operations:
            return
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.target_tree = PlanTargetTree(plan)
        self.splitter.addWidget(self.target_tree)
        proxy = PlanFilterModel(self.splitter)
        proxy.setSourceModel(self.plans)
        target_view = QTableView()
        target_view.setModel(proxy)
        target_view.setItemDelegateForColumn(CATEGORY_COLUMN, CategoryDelegate(target_view))
        target_view.setItemDelegateForColumn(STATUS_COLUMN, PlanStatusDelegate(target_view))
        configure_file_view(target_view)
        target_view.setColumnHidden(0, True)
        target_view.setColumnHidden(EXECUTE_COLUMN, True)
        for column, width in ((1, 240), (2, 160), (3, 160), (4, 90), (5, 220), (6, 70), (7, 180)):
            target_view.setColumnWidth(column, width)
        header = target_view.horizontalHeader()
        header.moveSection(header.visualIndex(2), 0)
        header.moveSection(header.visualIndex(3), 1)
        self.target_tree.currentItemChanged.connect(lambda item, _old: proxy.set_target(
            plan.root / str(item.data(0, PATH_ROLE)) if item and item.data(0, PATH_ROLE) else None,
            bool(item and item.data(0, KIND_ROLE) == "file")))
        self.splitter.addWidget(target_view)
        self.splitter.setSizes([330, 500])
        self.target_layout.addWidget(self.splitter)
        self.setCurrentWidget(self.target_page)
