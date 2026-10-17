"""Editable provider profiles, credential handling, and real connection testing."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from filemind.ai.providers import PROVIDERS, PROVIDER_BY_ID
from filemind.ai.providers import is_local_connection
from filemind.storage.settings import AISettings, SettingsError, SettingsStore
from filemind.ui.widgets.card import Card
from filemind.ui.widgets.combo_box import StyledComboBox
from filemind.ui.styles.icons import provider_icon
from filemind.ui.widgets.model_selector import ModelSelector


class SettingsPage(QWidget):
    """Edit stored provider profiles without placing API calls on the UI thread."""

    test_requested = Signal(object)
    cancel_requested = Signal()
    configuration_changed = Signal()
    parallel_test_requested = Signal(object)
    refresh_models_requested = Signal(str)
    ollama_models_requested = Signal()

    def __init__(self, store: SettingsStore | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store or SettingsStore()
        self._provider_id = "deepseek"
        self._dirty = False
        self._known_model_options: list[str] = []
        self._build_ui()
        self._load_provider()
        self._load_multi_model()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        scroll_area = QScrollArea()
        scroll_area.setObjectName("SettingsScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        card = Card()
        title = QLabel("模型服务配置")
        title.setStyleSheet("font-size:12pt;font-weight:650;")
        card.layout.addWidget(title)
        self._build_configuration_fields(card)
        self._build_configuration_actions(card)
        layout.addWidget(card)
        layout.addWidget(self._multi_model_card())
        layout.addStretch(1)
        scroll_area.setWidget(body)
        root_layout.addWidget(scroll_area)

    def _build_configuration_fields(self, card: Card) -> None:
        self.provider_combo = StyledComboBox()
        self.provider_combo.setIconSize(QSize(24, 24))
        for provider in PROVIDERS:
            self.provider_combo.addItem(provider_icon(provider.provider_id), provider.name, provider.provider_id)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(13)
        form.addRow("服务商", self.provider_combo)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("https://api.example.com/v1")
        form.addRow("API Base URL", self.base_url_edit)
        self.model_combo = StyledComboBox()
        self.model_combo.setObjectName("ModelConfigChoice")
        self.model_combo.setEditable(True)
        self.model_edit = self.model_combo.lineEdit()
        self.model_edit.setPlaceholderText("填写服务商提供的模型 ID")
        self.detect_ollama_button = QPushButton("检测本机模型")
        self.detect_ollama_button.clicked.connect(self.ollama_models_requested.emit)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(self.detect_ollama_button)
        form.addRow("模型名称", model_row)
        self._build_secret_fields(form)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 180)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setValue(45)
        form.addRow("请求超时", self.timeout_spin)
        card.layout.addLayout(form)
        self.provider_note = QLabel()
        self.provider_note.setObjectName("Muted")
        self.provider_note.setWordWrap(True)
        card.layout.addWidget(self.provider_note)
        self.local_key_checkbox = QCheckBox("在本机配置文件中明文保存密钥（不推荐）")
        card.layout.addWidget(self.local_key_checkbox)
        self.local_key_warning = QLabel(
            "启用后密钥将以明文保存在当前用户应用数据目录，并限制文件权限。仅在系统凭据存储不可用且你接受风险时选择。"
        )
        self.local_key_warning.setObjectName("Muted")
        self.local_key_warning.setWordWrap(True)
        self.local_key_warning.setVisible(False)
        card.layout.addWidget(self.local_key_warning)

    def _build_secret_fields(self, form: QFormLayout) -> None:
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("API Key；默认由 Windows 凭据管理器保护")
        self.show_key_button = QPushButton("显示")
        self.show_key_button.setFixedWidth(72)
        self.show_key_button.clicked.connect(self._toggle_key_visibility)
        secret_row = QHBoxLayout()
        secret_row.addWidget(self.api_key_edit, 1)
        secret_row.addWidget(self.show_key_button)
        self.secret_container = QWidget()
        self.secret_container.setLayout(secret_row)
        form.addRow("API Key", self.secret_container)
        self.secret_label = form.labelForField(self.secret_container)

    def _build_configuration_actions(self, card: Card) -> None:
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.status_label = QLabel("密钥不会写入项目源码或操作历史。")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        actions.addWidget(self.status_label, 1)
        self.test_button = QPushButton("测试连接")
        self.test_button.clicked.connect(self._request_test)
        actions.addWidget(self.test_button)
        self.cancel_button = QPushButton("取消测试")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        actions.addWidget(self.cancel_button)
        self.save_button = QPushButton("保存配置")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_current)
        actions.addWidget(self.save_button)
        card.layout.addLayout(actions)
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        for widget in (self.base_url_edit, self.model_edit, self.api_key_edit):
            widget.textChanged.connect(self._mark_dirty)
        self.timeout_spin.valueChanged.connect(self._mark_dirty)
        self.local_key_checkbox.toggled.connect(self._local_key_changed)

    def _set_status_tone(self, tone: str) -> None:
        self.status_label.setProperty("statusTone", tone)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def reapply_theme(self) -> None:
        """Refresh provider artwork without reloading or changing the form."""
        for index in range(self.provider_combo.count()):
            self.provider_combo.setItemIcon(index, provider_icon(str(self.provider_combo.itemData(index))))

    def _provider_changed(self, index: int) -> None:
        selected_id = str(self.provider_combo.itemData(index))
        if selected_id == self._provider_id:
            return
        if self._dirty and not self._resolve_unsaved_changes():
            self.provider_combo.blockSignals(True)
            self.provider_combo.setCurrentIndex(self.provider_combo.findData(self._provider_id))
            self.provider_combo.blockSignals(False)
            return
        self._load_provider(selected_id)
        self._dirty = True
        self.status_label.setText("已切换服务商，请保存后再用于整理。")

    def _resolve_unsaved_changes(self) -> bool:
        choice = QMessageBox.question(
            self, "尚未保存配置", "当前服务商配置已修改。保存后再切换吗？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save_current()
        return choice == QMessageBox.StandardButton.Discard

    def _load_provider(self, provider_id: str | None = None) -> None:
        settings = self.store.load(provider_id)
        self._provider_id = settings.provider_id
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentIndex(self.provider_combo.findData(settings.provider_id))
        self.provider_combo.blockSignals(False)
        self.base_url_edit.setText(settings.base_url)
        self.model_edit.setText(settings.model)
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self._known_model_options = list(settings.model_options)
        self.model_combo.addItems(list(dict.fromkeys([settings.model, *settings.model_options])))
        self.model_combo.setCurrentText(settings.model)
        self.model_combo.blockSignals(False)
        self.api_key_edit.setText(settings.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_key_button.setText("显示")
        self.timeout_spin.setValue(settings.timeout_seconds)
        self.local_key_checkbox.setChecked(settings.store_key_locally)
        local = settings.provider_id == "ollama"
        self.detect_ollama_button.setVisible(local)
        self.secret_container.setVisible(not local)
        self.secret_label.setVisible(not local)
        self.local_key_checkbox.setVisible(not local)
        self.local_key_warning.setVisible(not local and settings.store_key_locally)
        self.provider_note.setText(PROVIDER_BY_ID[settings.provider_id].note)
        self._dirty = False
        self._set_status_tone("")
        self.status_label.setText(f"已加载配置 · API Key 来源：{settings.api_key_source}；尚未验证当前连接。")
        self._update_test_enabled()

    def _mark_dirty(self, *_args) -> None:
        self._dirty = True
        self._set_status_tone("")
        self.status_label.setText("配置有修改，保存后生效。")
        self._update_test_enabled()

    @property
    def has_unsaved_changes(self) -> bool:
        """Tell the organizer whether the visible profile differs from storage."""
        return self._dirty

    def _local_key_changed(self, enabled: bool) -> None:
        self.local_key_warning.setVisible(enabled)
        self._mark_dirty()

    def _toggle_key_visibility(self) -> None:
        visible = self.api_key_edit.echoMode() == QLineEdit.EchoMode.Password
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.show_key_button.setText("隐藏" if visible else "显示")

    def _collect_settings(self) -> AISettings:
        return AISettings(self._provider_id, self.base_url_edit.text().strip(), self.model_edit.text().strip(),
                          self.timeout_spin.value(), self.api_key_edit.text().strip(),
                          self.local_key_checkbox.isChecked(),
                          local=is_local_connection(self._provider_id, self.base_url_edit.text()),
                          model_options=tuple(self._known_model_options))

    def save_current(self) -> bool:
        """Persist the visible provider profile and show its actual storage mode."""
        try:
            settings = self._collect_settings()
            self.store.save(settings)
        except (SettingsError, OSError, ValueError) as error:
            message = self._safe_message(str(error))
            self.status_label.setText(message)
            QMessageBox.warning(self, "保存失败", message)
            return False
        self._dirty = False
        self._set_status_tone("")
        if settings.local:
            message = "本机 Ollama 配置已保存；无需 API Key，尚未测试连接。"
        elif not settings.api_key:
            message = "配置已保存；尚未配置 API Key，填写密钥后才能发送 AI 请求。"
        elif settings.store_key_locally:
            message = "配置已保存；API Key 使用本机明文配置文件。尚未验证当前连接。"
        else:
            backend = getattr(self.store, "credential_storage_label", "系统凭据存储")
            message = f"配置已保存；API Key 使用{backend}。尚未验证当前连接。"
        self.status_label.setText(message)
        self._update_test_enabled()
        self.configuration_changed.emit()
        return True

    def _request_test(self) -> None:
        settings = self._collect_settings()
        if not settings.api_key and not settings.local:
            self.status_label.setText("请先填写 API Key。")
            return
        self.set_test_running()
        self.test_requested.emit(settings)

    def set_test_running(self) -> None:
        """Lock the tested values until the worker returns."""
        for widget in (self.provider_combo, self.base_url_edit, self.model_edit, self.api_key_edit,
                       self.show_key_button, self.timeout_spin, self.local_key_checkbox,
                       self.save_button, self.test_button):
            widget.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status_label.setText("正在向服务商发送真实连接测试请求…")

    def set_test_result(self, success: bool, message: str) -> None:
        """Show the result of a completed background connection request."""
        for widget in (self.provider_combo, self.base_url_edit, self.model_edit, self.api_key_edit,
                       self.show_key_button, self.timeout_spin, self.local_key_checkbox, self.save_button):
            widget.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_label.setText(self._safe_message(message))
        self._update_test_enabled()
        if success:
            self._set_status_tone("success")
        else:
            self._set_status_tone("danger")

    def _update_test_enabled(self) -> None:
        self.test_button.setEnabled(bool(self.base_url_edit.text().strip() and self.model_edit.text().strip()
                                         and (self.api_key_edit.text().strip() or is_local_connection(
                                             self._provider_id, self.base_url_edit.text()))))

    def _safe_message(self, message: str) -> str:
        """Avoid echoing the visible credential if an adapter returns unsafe text."""
        key = self.api_key_edit.text().strip()
        return message.replace(key, "[已隐藏密钥]") if key else message

    def _multi_model_card(self) -> Card:
        card = Card()
        title = QLabel("多模型（并行调用）")
        title.setStyleSheet("font-size:12pt;font-weight:650;")
        detail = QLabel(
            "勾选、排序并保存模型列表。并行模式默认关闭；开启后，每条消息与近期上下文会分别发送给所选模型，"
            "可能产生多份费用。最多同时启用 4 个模型；附件须关闭并行后单独确认发送。"
        )
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        self.model_selector = ModelSelector()
        self.model_selector.changed.connect(self._mark_multi_dirty)
        self.model_selector.refresh_local_requested.connect(self.refresh_models_requested.emit)
        self.parallel_checkbox = QCheckBox("Orbit 发送时并行调用所有已选模型")
        self.parallel_checkbox.toggled.connect(self._mark_multi_dirty)
        self.multi_cancel_button = QPushButton("取消并行测试")
        self.multi_cancel_button.setEnabled(False)
        self.multi_cancel_button.clicked.connect(self.cancel_requested.emit)
        actions = QHBoxLayout()
        self.multi_status = QLabel("模型选择只保存在本机；不会写入任何密钥。")
        self.multi_status.setObjectName("Muted")
        self.multi_status.setWordWrap(True)
        actions.addWidget(self.multi_status, 1)
        self.multi_test_button = QPushButton("并行测试已选模型")
        self.multi_test_button.clicked.connect(self._request_parallel_test)
        actions.addWidget(self.multi_test_button)
        self.multi_save_button = QPushButton("保存模型选择")
        self.multi_save_button.setObjectName("PrimaryButton")
        self.multi_save_button.clicked.connect(self.save_models)
        actions.addWidget(self.multi_save_button)
        card.layout.addWidget(title)
        card.layout.addWidget(detail)
        card.layout.addWidget(self.model_selector)
        card.layout.addWidget(self.parallel_checkbox)
        card.layout.addWidget(self.multi_cancel_button, 0, Qt.AlignmentFlag.AlignRight)
        card.layout.addLayout(actions)
        return card

    def _load_multi_model(self) -> None:
        """Load the saved selection and parallel preference without failing the page."""
        try:
            loader = getattr(self.store, "load_models", None)
            mode = getattr(self.store, "is_parallel_mode_enabled", None)
            self.model_selector.set_configs(loader() if callable(loader) else [])
            self.parallel_checkbox.setChecked(mode() if callable(mode) else False)
        except (SettingsError, OSError, ValueError) as error:
            self.multi_status.setText(f"无法读取多模型配置：{error}")

    def _mark_multi_dirty(self) -> None:
        self.multi_status.setToolTip("")
        self.multi_status.setText("模型选择有修改，保存后生效。")

    def save_models(self) -> bool:
        """Persist the ordered selection and the parallel preference."""
        try:
            self.store.save_models(self.model_selector.configs(), self.parallel_checkbox.isChecked())
        except (SettingsError, OSError, ValueError) as error:
            self.multi_status.setText(str(error))
            QMessageBox.warning(self, "保存失败", str(error))
            return False
        self.multi_status.setText("模型选择已保存到本机。")
        self.configuration_changed.emit()
        return True

    def _request_parallel_test(self) -> None:
        configs = [config for config in self.model_selector.configs() if config.enabled]
        if not configs:
            self.multi_status.setText("请先勾选至少一个模型。")
            return
        self.multi_test_button.setEnabled(False)
        self.multi_cancel_button.setEnabled(True)
        self.multi_status.setText("正在并行调用已选模型…")
        self.parallel_test_requested.emit(configs)

    def set_parallel_test_result(self, result: object) -> None:
        """Show how many selected models answered a parallel probe."""
        self.multi_test_button.setEnabled(True)
        self.multi_cancel_button.setEnabled(False)
        results = list(getattr(result, "results", ()) or ())
        if not results:
            self.multi_status.setText("没有可用结果。")
            return
        succeeded = sum(1 for item in results if getattr(item, "ok", False))
        self.multi_status.setText(f"并行测试完成：{succeeded}/{len(results)} 个模型返回结果。")
        self.multi_status.setToolTip(_format_parallel_summary(results))

    def set_parallel_test_failed(self, message: str) -> None:
        """Restore test actions after a failed or cancelled parallel probe."""
        self.multi_test_button.setEnabled(True)
        self.multi_cancel_button.setEnabled(False)
        self.multi_status.setText(f"并行测试失败：{message}")

    def set_local_models(self, models: object) -> None:
        names = [str(name) for name in models if str(name).strip()] if isinstance(models, (list, tuple)) else []
        self.model_selector.set_local_models(names)

    def set_local_models_failed(self, message: str) -> None:
        self.model_selector.set_add_status(message)

    def set_ollama_detect_running(self, running: bool) -> None:
        """Lock only the detection button while the local model listing is in flight."""
        for widget in (self.detect_ollama_button, self.provider_combo, self.base_url_edit,
                       self.model_combo, self.save_button):
            widget.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        if running:
            self.status_label.setText("正在检测本机 Ollama 已安装的模型…")

    def set_ollama_models(self, models: list[str], error: str | None) -> None:
        """Show detected Ollama models and keep them for the next save."""
        self.set_ollama_detect_running(False)
        if error:
            self.status_label.setText(error)
            self._set_status_tone("danger")
            return
        self._known_model_options = list(dict.fromkeys(models))
        current_text = self.model_combo.currentText().strip()
        self._populate_model_options()
        if current_text:
            self.model_combo.blockSignals(True)
            self.model_combo.setCurrentText(current_text)
            self.model_combo.blockSignals(False)
        self._dirty = True
        self._set_status_tone("success")
        self.status_label.setText(f"已检测到本机 {len(models)} 个 Ollama 模型，可下拉选择后保存。")

    def _populate_model_options(self) -> None:
        current = self.model_edit.text()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(list(dict.fromkeys([current, *self._known_model_options])))
        self.model_combo.setCurrentText(current)
        self.model_combo.blockSignals(False)


def _format_parallel_summary(results: list[object]) -> str:
    """Build the tooltip that lists each selected model's probe outcome."""
    lines: list[str] = []
    for item in results:
        label = getattr(item, "label", None) or f"{getattr(item, 'provider', '')} · {getattr(item, 'model', '')}"
        error = getattr(item, "error", None)
        if error:
            lines.append(f"{label}：失败（{error}）")
        else:
            preview = str(getattr(item, "content", ""))[:120].replace("\n", " ")
            lines.append(f"{label}：{preview}")
    return "\n".join(lines)
