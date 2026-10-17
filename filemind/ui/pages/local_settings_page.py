"""General appearance, local account and privacy settings, separate from models."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from filemind.ai.providers import PROVIDER_BY_ID
from filemind.storage.settings import SettingsError, SettingsStore
from filemind.ui.styles.theme import appearance_choices
from filemind.ui.widgets.card import Card
from filemind.ui.widgets.combo_box import StyledComboBox
from filemind.ui.widgets.privacy_dialog import OrbitPrivacyDialog


class LocalSettingsPage(QWidget):
    """Local settings reached from the account menu, without model form duplication."""

    local_auth_requested = Signal(str)
    appearance_changed = Signal(str)

    def __init__(self, store: SettingsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._appearance = "light"
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("SettingsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(16)
        column.addWidget(self._appearance_card())
        column.addWidget(self._local_lock_card())
        column.addWidget(self._privacy_card())
        column.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll)

    def _appearance_card(self) -> Card:
        card = Card()
        title = QLabel("外观")
        title.setObjectName("SettingsSectionTitle")
        detail = QLabel("选择整个工作空间的主题。跟随系统会自动响应系统的深浅色切换；绿色和橙色使用浅色背景。")
        detail.setWordWrap(True)
        detail.setObjectName("Muted")
        row = QHBoxLayout()
        row.addWidget(QLabel("主题色调"))
        self.appearance_combo = StyledComboBox()
        self.appearance_combo.setObjectName("AppearanceChoice")
        self.appearance_combo.setAccessibleName("主题色调")
        self.appearance_combo.setMinimumWidth(155)
        for value, label in appearance_choices():
            self.appearance_combo.addItem(label, value)
        self.appearance_status = QLabel()
        self.appearance_status.setObjectName("Muted")
        self.appearance_status.setWordWrap(True)
        try:
            getter = getattr(self.store, "get_appearance", None)
            self._appearance = getter() if callable(getter) else "light"
        except (SettingsError, OSError, ValueError):
            self.appearance_status.setText("主题配置读取失败，暂用浅色；更改后可重新保存。")
        self.appearance_combo.setCurrentIndex(self.appearance_combo.findData(self._appearance))
        self.appearance_combo.currentIndexChanged.connect(self._change_appearance)
        row.addWidget(self.appearance_combo)
        row.addStretch(1)
        for widget in (title, detail):
            card.layout.addWidget(widget)
        card.layout.addLayout(row)
        card.layout.addWidget(self.appearance_status)
        return card

    def _change_appearance(self, index: int) -> None:
        value = str(self.appearance_combo.itemData(index))
        try:
            self.store.set_appearance(value)
        except (SettingsError, OSError, ValueError):
            self.appearance_combo.blockSignals(True)
            self.appearance_combo.setCurrentIndex(self.appearance_combo.findData(self._appearance))
            self.appearance_combo.blockSignals(False)
            self.appearance_status.setText("主题保存失败，请检查配置目录权限后重试。")
            return
        self._appearance = value
        self.appearance_status.setText("已保存，重启后继续使用。")
        self.appearance_changed.emit(value)

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
                button.setToolTip("当前工作空间尚未启用本机锁屏。")

    def _privacy_card(self) -> Card:
        card = Card()
        title = QLabel("数据与隐私")
        title.setStyleSheet("font-size:12pt;font-weight:650;")
        organize_detail = QLabel(
            "AI 整理会向所选服务发送文件名、扩展名、大小、修改时间和你填写的整理规则。在线服务由对应服务商处理这些数据。"
            "默认不发送正文；只有逐次授权内容识别后才发送有限片段或图片缩略图，不发送整个文件夹或绝对路径。"
        )
        organize_detail.setObjectName("Muted")
        organize_detail.setWordWrap(True)
        orbit_detail = QLabel(
            "Orbit 会向当前服务商发送消息和近期最多 20 条上下文。并行模式会分别发送至所选模型并列出接口确认。"
            "会话在本机保存；本机 Ollama 是否转发云端取决于其服务配置。"
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
