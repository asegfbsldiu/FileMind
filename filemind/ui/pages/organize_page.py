"""Compact import, rule submission and plan inspection workspace."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QInputMethodEvent, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QToolButton, QVBoxLayout, QWidget, QSplitter,
)

from filemind.core.organization_presets import PRESETS
from filemind.models import FileInfo, OperationPlan
from filemind.ui.styles.icons import svg_icon
from filemind.ui.widgets.card import Card
from filemind.ui.widgets.combo_box import StyledComboBox
from filemind.ui.widgets.file_table import FilePlanTableModel
from filemind.ui.widgets.imported_files import CompactMetric, ImportedFilesModel
from filemind.ui.widgets.organization_workspace import OrganizationWorkspace


class RuleEditor(QPlainTextEdit):
    """Submit on Enter, keeping Shift+Enter and IME composition editable."""

    submitted = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._composing = False
        self.setTabChangesFocus(True)

    def inputMethodEvent(self, event: QInputMethodEvent) -> None:
        self._composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._composing and event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.submitted.emit()
                event.accept()
                return
        super().keyPressEvent(event)


class OrganizePage(QWidget):
    """Browse selected files, request suggestions, then explicitly review a plan."""

    scan_requested = Signal(str)
    import_requested = Signal(str)
    folder_selected = Signal(str)
    clear_requested = Signal()
    preview_requested = Signal()
    execute_requested = Signal(object)
    history_requested = Signal()
    settings_requested = Signal()
    plan_invalidated = Signal()
    layout_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plan: OperationPlan | None = None
        self.ai_status_message = "未配置：缺少 API Key。"
        self._busy = False
        self._preset_index = 0
        self._preset_prompt = ""
        self._build_ui()
        self.table_model.plan_changed.connect(self._accept_edited_plan)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        self._build_configuration()
        results = self._build_results()
        self._build_splitter(results)
        root.addWidget(self.layout_splitter, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(5)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)
        root.addLayout(self._action_row())
        self._update_mode()
        self.rule_input.textChanged.connect(self._rule_changed)
        self.rename_checkbox.toggled.connect(self._rule_changed)
        self.content_checkbox.toggled.connect(self._content_changed)
        self.setTabOrder(self.preset_combo, self.mode_combo)
        self.setTabOrder(self.mode_combo, self.rule_input)
        self.setTabOrder(self.rule_input, self.rule_send_button)
        self.set_busy(False)

    def _build_configuration(self) -> None:
        self.content_scroll = QScrollArea()
        self.content_scroll.setObjectName("OrganizerContentScroll")
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_scroll.setMinimumHeight(140)
        body = QWidget()
        config = QVBoxLayout(body)
        config.setContentsMargins(0, 0, 0, 0)
        config.setSpacing(8)
        config.addWidget(self._directory_bar())
        config.addWidget(self._rules_card())
        self.content_scroll.setWidget(body)

    def _build_results(self) -> QWidget:
        results = QWidget()
        result_layout = QVBoxLayout(results)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(8)
        result_layout.addLayout(self._summary_row())
        self.import_model = ImportedFilesModel(self)
        self.table_model = FilePlanTableModel(self)
        self.workspace = OrganizationWorkspace(self.import_model, self.table_model)
        self.workspace.choose_requested.connect(self._choose_folder)
        self.workspace.read_requested.connect(self._request_import)
        result_layout.addWidget(self.workspace, 1)
        results.setMinimumHeight(180)
        return results

    def _build_splitter(self, results: QWidget) -> None:
        self.layout_splitter = QSplitter(Qt.Orientation.Vertical)
        self.layout_splitter.setObjectName("OrganizerSplitter")
        self.layout_splitter.setChildrenCollapsible(False)
        self.layout_splitter.setHandleWidth(8)
        self.layout_splitter.addWidget(self.content_scroll)
        self.layout_splitter.addWidget(results)
        self.layout_splitter.setStretchFactor(1, 1)
        self.layout_splitter.setSizes([246, 500])
        self.layout_splitter.handle(1).setAccessibleName("调整规则区和文件区高度")
        self.layout_splitter.handle(1).setToolTip("上下拖动，调整规则区与文件区的高度")
        self.layout_splitter.splitterMoved.connect(self._layout_moved)

    def _layout_moved(self, _position: int, _index: int) -> None:
        self.layout_changed.emit(self.layout_splitter.sizes()[0])

    def _directory_bar(self) -> Card:
        card = Card(padding=10)
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setMinimumWidth(0)
        self.path_edit.setPlaceholderText("选择文件夹，先浏览文件，再生成整理建议")
        row.addWidget(self.path_edit, 1)
        self.clear_directory_button = QToolButton()
        self.clear_directory_button.setObjectName("ClearDirectoryButton")
        self.clear_directory_button.setText("×")
        self.clear_directory_button.setAccessibleName("清除当前目录")
        self.clear_directory_button.clicked.connect(self.clear_requested.emit)
        row.addWidget(self.clear_directory_button)
        self.choose_button = QPushButton("选择目录")
        self.choose_button.setIcon(svg_icon("folder"))
        self.choose_button.clicked.connect(self._choose_folder)
        row.addWidget(self.choose_button)
        self.scan_button = QPushButton("读取文件")
        self.scan_button.clicked.connect(self._request_import)
        row.addWidget(self.scan_button)
        card.layout.addLayout(row)
        return card

    def _rules_card(self) -> Card:
        card = Card(padding=10)
        card.layout.setSpacing(6)
        row = QHBoxLayout()
        self.preset_combo = StyledComboBox()
        self.preset_combo.setMinimumWidth(0)
        for preset in PRESETS:
            self.preset_combo.addItem(preset.title, preset.key)
        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        row.addWidget(self.preset_combo, 1)
        self.mode_combo = StyledComboBox()
        self.mode_combo.addItem("本地规则分类", "rules")
        self.mode_combo.addItem("AI 智能整理", "ai")
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        row.addWidget(self.mode_combo)
        self.rename_checkbox = QCheckBox("应用 AI 改名")
        self.rename_checkbox.setChecked(True)
        row.addWidget(self.rename_checkbox)
        self.settings_link = QPushButton("配置 AI 服务")
        self.settings_link.clicked.connect(self.settings_requested.emit)
        row.addWidget(self.settings_link)
        card.layout.addLayout(row)
        editor_row = QHBoxLayout()
        self.rule_input = RuleEditor()
        self.rule_input.setAccessibleName("文件整理规则")
        self.rule_input.setMinimumHeight(58)
        self.rule_input.setMaximumHeight(68)
        self.rule_input.setPlaceholderText("描述分类规则 · Enter 发送，Shift+Enter 换行")
        self.rule_input.submitted.connect(self._request_scan)
        editor_row.addWidget(self.rule_input, 1)
        self.rule_send_button = QPushButton("生成预览")
        self.rule_send_button.setObjectName("PrimaryButton")
        self.rule_send_button.setToolTip("提交当前整理规则；生成建议后还需预览并确认执行")
        self.rule_send_button.clicked.connect(self._request_scan)
        editor_row.addWidget(self.rule_send_button)
        card.layout.addLayout(editor_row)
        self._build_rule_notes(card)
        return card

    def _build_rule_notes(self, card: Card) -> None:
        self.content_checkbox = QCheckBox("理解文件内容并命名（每次发送前确认）")
        self.content_checkbox.setObjectName("ContentAnalysisToggle")
        self.content_checkbox.setToolTip("文档发送开头片段；图片发送压缩缩略图。默认关闭，凭据文件会排除。")
        options = QHBoxLayout()
        options.addWidget(self.content_checkbox, 1)
        self.ai_model_badge = QLabel("未配置模型")
        self.ai_model_badge.setObjectName("ModelStatusBadge")
        self.ai_model_badge.setMinimumWidth(0)
        self.rule_mode_note = QLabel()
        self.rule_mode_note.setObjectName("Muted")
        self.rule_mode_note.setWordWrap(True)
        options.addWidget(self.ai_model_badge)
        card.layout.addLayout(options)
        card.layout.addWidget(self.rule_mode_note)
        self.ai_privacy_label = QLabel("将文件名、扩展名、大小、修改时间及规则发送给所选服务商；不会上传文件正文。")
        self.ai_privacy_label.setObjectName("Muted")
        self.ai_privacy_label.setWordWrap(True)
        card.layout.addWidget(self.ai_privacy_label)

    def _summary_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.file_count = CompactMetric("个文件")
        self.pending_count = CompactMetric("待整理")
        self.rename_count = CompactMetric("改名")
        self.issue_count = CompactMetric("异常")
        for metric in (self.file_count, self.pending_count, self.rename_count, self.issue_count):
            row.addWidget(metric)
        row.addStretch(1)
        self.summary_label = QLabel("等待导入")
        self.summary_label.setObjectName("Muted")
        self.summary_label.setMinimumWidth(0)
        self.preview_status = self.summary_label
        row.addWidget(self.summary_label)
        return row

    def _action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        self.page_status = QLabel("只读取所选目录第一层文件；执行前需要预览确认。")
        self.page_status.setObjectName("Muted")
        self.page_status.setWordWrap(True)
        self.page_status.setMinimumWidth(0)
        row.addWidget(self.page_status, 1)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self._request_import)
        self.cancel_button = QPushButton("取消")
        self.last_operation_label = QLabel()
        self.last_operation_label.setObjectName("Muted")
        self.last_operation_label.hide()
        self.history_button = QPushButton("整理历史")
        self.history_button.setIcon(svg_icon("history", size=16))
        self.history_button.clicked.connect(self.history_requested.emit)
        self.execute_button = QPushButton("查看预览并确认")
        self.execute_button.setObjectName("PrimaryButton")
        self.execute_button.clicked.connect(self.preview_requested.emit)
        for widget in (self.last_operation_label, self.refresh_button, self.cancel_button,
                       self.history_button, self.execute_button):
            row.addWidget(widget)
        return row

    def _preset_changed(self, index: int) -> None:
        preset = PRESETS[index]
        current = self.rule_input.toPlainText().strip()
        if preset.prompt and current and current != self._preset_prompt:
            answer = QMessageBox.question(self, "替换当前规则", "载入所选预设会替换当前规则文本，继续吗？",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.preset_combo.blockSignals(True)
                self.preset_combo.setCurrentIndex(self._preset_index)
                self.preset_combo.blockSignals(False)
                return
        self._preset_index, self._preset_prompt = index, preset.prompt
        self.mode_combo.setCurrentIndex(1 if preset.mode == "ai" else 0)
        self.content_checkbox.setChecked(preset.key == "content")
        if preset.key == "content":
            self.rename_checkbox.setChecked(True)
        if preset.prompt:
            self.rule_input.setPlainText(preset.prompt)
        self._rule_changed()

    def _mode_changed(self, *_args: object) -> None:
        self._update_mode()
        self._rule_changed()

    def _update_mode(self, *_args: object) -> None:
        ai = self.mode_combo.currentData() == "ai"
        self.rename_checkbox.setEnabled(ai and not self._busy)
        self.rename_checkbox.setVisible(ai)
        self.content_checkbox.setVisible(ai)
        self.content_checkbox.setEnabled(ai and not self._busy)
        self.settings_link.setVisible(ai)
        self.ai_privacy_label.setVisible(ai)
        self.ai_model_badge.setVisible(ai)
        self.rule_mode_note.setVisible(not ai)
        self.rule_mode_note.setText(self.ai_status_message if ai else
                                   "本地按类型或年月日分类，不识别内容、不自动改名；自然语言不会被本地分类器理解。内容命名请选择 AI 内容预设。")
        content = ai and self.content_checkbox.isChecked()
        self.rule_send_button.setText("识别内容并生成建议" if content else "发送 AI 规则" if ai else "生成规则预览")
        self.ai_privacy_label.setText(
            "本次另发送文档开头片段或图片缩略图（含图中可见信息），以及文件元数据和规则；发送前需确认。"
            if content else "将文件名、扩展名、大小、修改时间及规则发送给所选服务商；不会上传文件正文。")
        self.rule_input.setEnabled(True)

    def _content_changed(self, *_args: object) -> None:
        self._update_mode()
        self._rule_changed()

    def _rule_changed(self) -> None:
        if self.plan is not None and not self._busy:
            self.clear_plan()
            self.summary_label.setText("规则有变更，需重新生成")
            self.plan_invalidated.emit()

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择要整理的文件夹", self.path_edit.text())
        if folder:
            self.folder_selected.emit(folder)

    def _request_import(self) -> None:
        if not self._busy and self.path_edit.text().strip():
            self.import_requested.emit(self.path_edit.text().strip())

    def _request_scan(self) -> None:
        if self._busy:
            return
        if not self.path_edit.text().strip():
            self.set_status("请先选择需要整理的目录。")
            return
        self.scan_requested.emit(self.path_edit.text().strip())

    def set_busy(self, busy: bool, message: str = "") -> None:
        """Prevent duplicate submission while leaving rule text accessible."""
        self._busy = busy
        selected = bool(self.path_edit.text().strip())
        for button in (self.scan_button, self.refresh_button, self.rule_send_button):
            button.setEnabled(not busy and selected)
        self.choose_button.setEnabled(not busy)
        self.workspace.import_empty.action_button.setEnabled(not busy)
        self.mode_combo.setEnabled(not busy)
        self.preset_combo.setEnabled(not busy)
        self.content_checkbox.setEnabled(not busy and self.mode_combo.currentData() == "ai")
        self.rename_checkbox.setEnabled(not busy and self.mode_combo.currentData() == "ai")
        self.clear_directory_button.setEnabled(selected)
        self.cancel_button.setEnabled(busy)
        self.execute_button.setEnabled(not busy and bool(self.plan and self.plan.operations))
        self.progress_bar.setVisible(busy)
        if busy:
            self.progress_bar.setRange(0, 0)
        if message:
            self.set_status(message)

    def set_files(self, files: list[FileInfo]) -> None:
        """Display a scan snapshot without claiming that AI has analyzed it."""
        self.import_model.set_files(files)
        self.workspace.set_import_state(bool(self.path_edit.text().strip()), scanned=True)
        self.file_count.set_value(len(files))
        self.workspace.setCurrentIndex(0)
        self.summary_label.setText("已导入，等待生成建议" if files else "所选目录为空")
        self.set_status(f"已读取 {len(files)} 个文件；尚未生成 AI 建议。")

    def set_plan(self, plan: OperationPlan) -> None:
        """Show locally checked suggestions with truthful source counts."""
        self.table_model.set_plan(plan)
        self._display_plan(plan)

    def _accept_edited_plan(self) -> None:
        """Keep inline trees and summaries in sync without resetting the editor."""
        plan = self.table_model.current_plan()
        if plan is not None:
            self._display_plan(plan)

    def _display_plan(self, plan: OperationPlan) -> None:
        self.plan = plan
        self.import_model.set_files([FileInfo(item.source, item.size_bytes, item.modified_ns) for item in plan.operations])
        self.workspace.set_import_state(bool(self.path_edit.text().strip()), scanned=True)
        executable = [item for item in plan.operations if not item.excluded and not item.warning]
        issues = sum(bool(item.warning) and not item.excluded for item in plan.operations)
        renames = sum(item.new_name != item.original_name for item in executable)
        for metric, value in ((self.file_count, len(plan.operations)), (self.pending_count, len(executable)),
                              (self.rename_count, renames), (self.issue_count, issues)):
            metric.set_value(value)
        self.summary_label.setText("待确认" if plan.operations else "目录为空")
        self.workspace.set_plan(plan)
        self.execute_button.setEnabled(bool(plan.operations))
        self.clear_directory_button.setEnabled(bool(self.path_edit.text().strip()))

    def clear_plan(self) -> None:
        """Invalidate only suggestions while keeping imported files browsable."""
        self.plan = None
        self.table_model.set_plan(None)
        self.workspace.set_plan(None)
        for metric in (self.pending_count, self.rename_count, self.issue_count):
            metric.set_value("—")
        self.execute_button.setEnabled(False)
        self.summary_label.setText("等待生成建议")

    def set_directory(self, folder: str) -> None:
        """Replace directory-specific state without changing typed rules."""
        self.path_edit.setText(folder.strip())
        self.path_edit.setToolTip(folder.strip())
        self.import_model.set_files([])
        self.workspace.set_import_state(bool(folder.strip()), scanned=False)
        self.file_count.set_value("—")
        self.clear_plan()
        self.set_busy(self._busy)
        if not folder.strip():
            self.summary_label.setText("等待导入")
            self.set_status("当前目录已清除；没有磁盘文件被删除或移动。")

    def set_ai_configuration_status(self, message: str, is_ready: bool) -> None:
        """Show a compact public provider/model label and a full state tooltip."""
        self.ai_status_message = message
        self.settings_link.setText("管理 AI 服务" if is_ready else "配置 AI 服务")
        self.settings_link.setToolTip(message)
        self.ai_model_badge.setText(message.split("，", 1)[0].removeprefix("已配置 "))
        self.ai_model_badge.setToolTip(message)
        self._update_mode()

    def set_status(self, message: str, tooltip: str = "") -> None:
        """Show the current real task state without replacing the file list."""
        self.page_status.setText(message)
        self.page_status.setToolTip(tooltip)

    def set_progress(self, completed: int, total: int) -> None:
        """Show measured scan or batch progress when a total is known."""
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(completed)

    def set_error(self, message: str) -> None:
        """Keep original files and rules after analysis failure."""
        self.summary_label.setText("请求或扫描失败")
        self.set_status(message)

