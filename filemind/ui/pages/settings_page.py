"""Editable provider profiles, credential handling, and real connection testing."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from filemind.ai.providers import PROVIDERS, PROVIDER_BY_ID
from filemind.storage.settings import AISettings, SettingsError, SettingsStore
from filemind.ui.widgets.card import Card
from filemind.ui.widgets.privacy_dialog import OrbitPrivacyDialog


class SettingsPage(QWidget):
    """Edit stored provider profiles without placing API calls on the UI thread."""

    test_requested = Signal(object)
    cancel_requested = Signal()
    configuration_changed = Signal()
    local_auth_requested = Signal(str)

    def __init__(self, store: SettingsStore | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store or SettingsStore()
        self._provider_id = "deepseek"
        self._dirty = False
        self._build_ui()
        self._load_provider(self._provider_id)

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
        layout.addWidget(self._local_lock_card())
        layout.addWidget(self._privacy_card())
        layout.addStretch(1)
        scroll_area.setWidget(body)
        root_layout.addWidget(scroll_area)

    def _build_configuration_fields(self, card: Card) -> None:
        self.provider_combo = QComboBox()
        for provider in PROVIDERS:
            self.provider_combo.addItem(provider.name, provider.provider_id)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(13)
        form.addRow("服务商", self.provider_combo)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("https://api.example.com/v1")
        form.addRow("API Base URL", self.base_url_edit)
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("填写服务商提供的模型 ID")
        form.addRow("模型名称", self.model_edit)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("API Key；默认由 Windows 凭据管理器保护")
        self.show_key_button = QPushButton("显示")
        self.show_key_button.setFixedWidth(72)
        self.show_key_button.clicked.connect(self._toggle_key_visibility)
        secret_row = QHBoxLayout()
        secret_row.addWidget(self.api_key_edit, 1)
        secret_row.addWidget(self.show_key_button)
        form.addRow("API Key", secret_row)
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

    def _local_lock_card(self) -> Card:
        card = Card()
        title = QLabel("本机工作空间")
        title.setStyleSheet("font-size:12pt;font-weight:650;")
        detail = QLabel("密码只用于本机应用锁屏，不发送给模型服务。忘记密码可使用首次设置时保存的恢复码。"
                        "记住解锁最多保留 7 天；手动锁定或修改密码会撤销。此功能不提供磁盘加密。")
        detail.setWordWrap(True)
        detail.setObjectName("Muted")
        row = QHBoxLayout()
        self.lock_button = QPushButton("立即锁定")
        self.change_password_button = QPushButton("修改密码")
        self.lock_button.clicked.connect(lambda: self.local_auth_requested.emit("unlock"))
        self.change_password_button.clicked.connect(lambda: self.local_auth_requested.emit("change"))
        row.addWidget(self.lock_button)
        row.addWidget(self.change_password_button)
        row.addStretch(1)
        card.layout.addWidget(title)
        card.layout.addWidget(detail)
        card.layout.addLayout(row)
        return card

    def set_local_lock_available(self, available: bool) -> None:
        """Enable account actions only when the authenticated shell owns a lock."""
        for button in (self.lock_button, self.change_password_button):
            button.setEnabled(available)
            if not available:
                button.setToolTip("通过 main.py 正式入口启动后启用。")

    def _privacy_card(self) -> Card:
        card = Card()
        title = QLabel("数据与隐私")
        title.setStyleSheet("font-size:12pt;font-weight:650;")
        organize_detail = QLabel(
            "AI 整理会向所选服务发送文件名、扩展名、大小、修改时间和你填写的整理规则。在线服务由对应服务商处理这些数据。"
            "不会上传文件正文、整个文件夹或本地绝对路径。服务商会按其隐私政策处理请求。"
        )
        organize_detail.setObjectName("Muted")
        organize_detail.setWordWrap(True)
        orbit_detail = QLabel(
            "Orbit 会向当前服务商发送你输入的消息和最近最多 20 条对话上下文。会话在本机保存。"
        )
        orbit_detail.setObjectName("Muted")
        orbit_detail.setWordWrap(True)
        self.orbit_privacy_button = QPushButton("查看 Orbit 隐私说明")
        self.orbit_privacy_button.setObjectName("OrbitLinkButton")
        self.orbit_privacy_button.clicked.connect(self._show_orbit_privacy)
        card.layout.addWidget(title)
        card.layout.addWidget(organize_detail)
        card.layout.addWidget(orbit_detail)
        card.layout.addWidget(self.orbit_privacy_button, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _show_orbit_privacy(self) -> None:
        """Let the user inspect the chat data scope at any time from settings."""
        try:
            settings = self.store.load()
        except (SettingsError, OSError, ValueError) as error:
            QMessageBox.warning(self, "无法读取当前模型", str(error))
            return
        provider = PROVIDER_BY_ID.get(settings.provider_id)
        provider_name = provider.name if provider else settings.provider_id
        OrbitPrivacyDialog(provider_name, settings.model, False, self).exec()

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

    def _load_provider(self, provider_id: str) -> None:
        settings = self.store.load(provider_id)
        self._provider_id = provider_id
        self.base_url_edit.setText(settings.base_url)
        self.model_edit.setText(settings.model)
        self.api_key_edit.setText(settings.api_key)
        self.timeout_spin.setValue(settings.timeout_seconds)
        self.local_key_checkbox.setChecked(settings.store_key_locally)
        self.provider_note.setText(PROVIDER_BY_ID[provider_id].note)
        self._dirty = False
        self.status_label.setText(f"已加载配置 · API Key 来源：{settings.api_key_source}。")
        self._update_test_enabled()

    def _mark_dirty(self, *_args) -> None:
        self._dirty = True
        self.status_label.setStyleSheet("")
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
                          self.local_key_checkbox.isChecked())

    def save_current(self) -> bool:
        """Persist the visible provider profile and show its actual storage mode."""
        try:
            settings = self._collect_settings()
            self.store.save(settings)
        except (SettingsError, OSError, ValueError) as error:
            self.status_label.setText(str(error))
            QMessageBox.warning(self, "保存失败", str(error))
            return False
        self._dirty = False
        self.status_label.setText("配置已保存到本地。" if settings.store_key_locally
                                  else "配置已保存；API Key 使用系统凭据存储。")
        self._update_test_enabled()
        self.configuration_changed.emit()
        return True

    def _request_test(self) -> None:
        settings = self._collect_settings()
        if not settings.api_key:
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
        self.test_button.setEnabled(True)
        for widget in (self.provider_combo, self.base_url_edit, self.model_edit, self.api_key_edit,
                       self.show_key_button, self.timeout_spin, self.local_key_checkbox, self.save_button):
            widget.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_label.setText(message)
        if success:
            self.status_label.setStyleSheet("color:#16A34A;")
        else:
            self.status_label.setStyleSheet("color:#DC2626;")

    def _update_test_enabled(self) -> None:
        self.test_button.setEnabled(bool(self.base_url_edit.text().strip() and self.model_edit.text().strip()
                                         and self.api_key_edit.text().strip()))
