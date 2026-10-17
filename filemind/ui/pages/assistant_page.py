"""Independent Orbit landing page, conversation view, and local chat controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from filemind.ai.chat_prompts import SUGGESTED_PROMPTS
from filemind.chat_models import ChatConversation, ChatMessage
from filemind.ui.widgets.chat_input import ChatInput
from filemind.ui.widgets.chat_message import ChatMessageBubble
from filemind.ui.widgets.orbit_avatar import OrbitAvatar
from filemind.ui.widgets.suggestion_card import SuggestionCard


SHORTCUT_DETAILS = (
    ("学习规划", "拆解知识点，安排阶段练习", "learning"),
    ("代码解释", "理解代码流程与报错原因", "code"),
    ("项目计划", "拆分模块、任务和里程碑", "project"),
    ("分析文档", "粘贴文本后提炼重点和待办", "document"),
)


class AssistantPage(QWidget):
    """Keep Orbit messages, request feedback, and prompts out of file organization."""

    message_submitted = Signal(str, object)
    retry_requested = Signal()
    stop_requested = Signal()
    configure_requested = Signal()
    shortcut_selected = Signal(str, str)
    motion_preference_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OrbitRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._conversation_id: str | None = None
        self._model_ready = False
        self._user_avatar = QIcon()
        self._user_name = "你"
        self._reduced_motion = False
        self._request_busy = False
        self._busy_conversation_id: str | None = None
        self._motion_checkboxes: list[QCheckBox] = []
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._scroll_to_bottom_now)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 12, 26, 18)
        layout.setSpacing(12)
        self.stack = QStackedWidget()
        self.home_page = self._build_home_page()
        self.chat_page = self._build_chat_page()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.chat_page)
        layout.addWidget(self.stack, 1)

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 6)
        layout.addStretch(1)
        self._build_welcome(layout)
        layout.addSpacing(16)
        self.home_composer = ChatInput()
        self._connect_composer(self.home_composer)
        layout.addWidget(self.home_composer)
        self._build_shortcuts(layout)
        layout.addStretch(1)
        footnote = QLabel("Orbit 不会读取本地文件。发送消息前会提示你哪些内容将发送给所选模型服务。")
        footnote.setObjectName("OrbitFootnote")
        footnote.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footnote.setWordWrap(True)
        layout.addWidget(footnote)
        layout.addWidget(self._motion_control(), 0, Qt.AlignmentFlag.AlignRight)
        scroll = QScrollArea()
        scroll.setObjectName("OrbitHomeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _build_welcome(self, layout: QVBoxLayout) -> None:
        self.hero_avatar = OrbitAvatar(140, animate_idle=True)
        layout.addWidget(self.hero_avatar, 0, Qt.AlignmentFlag.AlignHCenter)
        title = QLabel("Orbit AI 助手")
        title.setObjectName("OrbitHeroTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        subtitle = QLabel("你的智能工作伙伴")
        subtitle.setObjectName("OrbitHeroSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        self.setup_notice = QLabel()
        self.setup_notice.setObjectName("OrbitSetupNotice")
        self.setup_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setup_notice.setWordWrap(True)
        self.setup_notice.setVisible(False)
        layout.addWidget(self.setup_notice)

    def _build_shortcuts(self, layout: QVBoxLayout) -> None:
        shortcuts = QGridLayout()
        self.shortcuts_grid = shortcuts
        self._shortcut_columns = 4
        shortcuts.setSpacing(12)
        self.suggestion_cards: list[SuggestionCard] = []
        for index, (title, description, icon) in enumerate(SHORTCUT_DETAILS):
            card = SuggestionCard(title, description, SUGGESTED_PROMPTS[title], icon)
            card.selected.connect(self._shortcut_clicked)
            self.suggestion_cards.append(card)
            shortcuts.addWidget(card, 0, index)
        layout.addSpacing(8)
        layout.addLayout(shortcuts)

    def _motion_control(self) -> QCheckBox:
        control = QCheckBox("减少动态效果")
        control.setToolTip("保留状态表情，关闭浮动、眨眼和轨道动画。")
        control.toggled.connect(self._motion_toggled)
        self._motion_checkboxes.append(control)
        return control

    def _motion_toggled(self, reduced: bool) -> None:
        self.set_reduced_motion(reduced)
        self.motion_preference_changed.emit(reduced)

    def set_reduced_motion(self, reduced: bool) -> None:
        """Apply a shared motion preference to current and future assistant avatars."""
        self._reduced_motion = reduced
        for control in self._motion_checkboxes:
            previous = control.blockSignals(True)
            control.setChecked(reduced)
            control.blockSignals(previous)
        for avatar in self.findChildren(OrbitAvatar):
            avatar.set_motion_enabled(not reduced)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "shortcuts_grid"):
            return
        columns = 2 if self.width() < 620 else 4
        if columns != self._shortcut_columns:
            while self.shortcuts_grid.count():
                self.shortcuts_grid.takeAt(0)
            for index, card in enumerate(self.suggestion_cards):
                self.shortcuts_grid.addWidget(card, index // columns, index % columns)
            self._shortcut_columns = columns

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.chat_title = QLabel("新对话")
        self.chat_title.setObjectName("OrbitChatTitle")
        header = QHBoxLayout()
        header.addWidget(self.chat_title, 1)
        header.addWidget(self._motion_control())
        layout.addLayout(header)
        self.message_scroll = QScrollArea()
        self.message_scroll.setObjectName("OrbitMessageScroll")
        self.message_scroll.setWidgetResizable(True)
        self.message_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.messages_container = QWidget()
        self.messages_container.setObjectName("OrbitMessagesContainer")
        self.messages_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(4, 8, 4, 8)
        self.messages_layout.setSpacing(6)
        self.messages_layout.addStretch(1)
        self.message_scroll.setWidget(self.messages_container)
        layout.addWidget(self.message_scroll, 1)
        layout.addLayout(self._build_status_row())
        self.chat_composer = ChatInput()
        self._connect_composer(self.chat_composer)
        layout.addWidget(self.chat_composer)
        return page

    def _build_status_row(self) -> QHBoxLayout:
        status_row = QHBoxLayout()
        self.activity_avatar = OrbitAvatar(36)
        self.activity_avatar.setVisible(False)
        status_row.addWidget(self.activity_avatar)
        self.status_label = QLabel()
        self.status_label.setObjectName("OrbitStatus")
        self.status_label.setWordWrap(True)
        status_row.addWidget(self.status_label, 1)
        self.retry_button = QPushButton("重试")
        self.retry_button.setObjectName("OrbitRetryButton")
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(self.retry_requested.emit)
        status_row.addWidget(self.retry_button)
        self.configure_error_button = QPushButton("检查模型设置")
        self.configure_error_button.setObjectName("OrbitRetryButton")
        self.configure_error_button.setVisible(False)
        self.configure_error_button.clicked.connect(self.configure_requested.emit)
        status_row.addWidget(self.configure_error_button)
        return status_row

    def _connect_composer(self, composer: ChatInput) -> None:
        composer.send_requested.connect(self.message_submitted.emit)
        composer.stop_requested.connect(self.stop_requested.emit)
        composer.configure_requested.connect(self.configure_requested.emit)

    def _shortcut_clicked(self, title: str, prompt: str) -> None:
        self.home_composer.set_text(prompt)
        self.shortcut_selected.emit(title, prompt)

    def set_model(self, provider_id: str | None, provider_name: str | None, model_name: str | None,
                  has_api_key: bool = False) -> None:
        """Update both composers with the one actual active model profile."""
        self._model_ready = has_api_key
        self.home_composer.set_model(provider_id, provider_name, model_name, has_api_key)
        self.chat_composer.set_model(provider_id, provider_name, model_name, has_api_key)
        self.setup_notice.setVisible(not has_api_key)
        self.setup_notice.setText("默认使用设置页中的模型。尚未配置 API Key；附件只会在你选择并确认发送后读取。")

    def set_conversation(self, conversation: ChatConversation | None) -> None:
        """Switch views and render a persisted conversation without sharing state."""
        self._conversation_id = conversation.conversation_id if conversation else None
        self.home_composer.clear_attachments()
        self.chat_composer.clear_attachments()
        self.clear_error()
        if conversation is None or not conversation.messages:
            self.stack.setCurrentWidget(self.home_page)
            self._sync_request_feedback()
            return
        self.chat_title.setText(conversation.title)
        self._clear_messages()
        for message in conversation.messages:
            self._append_bubble(message)
        self.stack.setCurrentWidget(self.chat_page)
        self._sync_request_feedback()
        self._scroll_to_bottom()

    def accept_submission(self) -> None:
        """Clear both editors only after storage and provider checks succeed."""
        self.home_composer.clear_text()
        self.chat_composer.clear_text()
        self.home_composer.clear_attachments()
        self.chat_composer.clear_attachments()

    def show_conversation(self, conversation: ChatConversation) -> None:
        """Display a conversation after appending its user turn."""
        self.set_conversation(conversation)
        self.stack.setCurrentWidget(self.chat_page)

    def set_busy(self, busy: bool, conversation_id: str | None = None) -> None:
        """Reflect only the request belonging to the currently displayed chat."""
        for composer in (self.home_composer, self.chat_composer):
            composer.set_busy(busy)
        self._request_busy = busy
        self._busy_conversation_id = conversation_id if busy else None
        self._sync_request_feedback()

    def _sync_request_feedback(self) -> None:
        active = self._request_busy and self._busy_conversation_id == self._conversation_id
        self.activity_avatar.set_state("thinking" if active else "ready")
        self.activity_avatar.setVisible(active)
        if active:
            self.status_label.setText("Orbit 正在思考…")
            self.retry_button.setVisible(False)
            self.configure_error_button.setVisible(False)
        elif self._request_busy:
            self.status_label.setText("另一段对话仍在生成；完成后可以继续提问。")
            self.retry_button.setVisible(False)
        else:
            self.status_label.clear()
            self.retry_button.setVisible(False)
            self.configure_error_button.setVisible(False)

    def show_reply(self, conversation_id: str) -> None:
        """Celebrate only the newly received answer in the currently visible chat."""
        if conversation_id != self._conversation_id or not self.isVisible() or self.window().isMinimized():
            return
        item = self.messages_layout.itemAt(self.messages_layout.count() - 2)
        bubble = item.widget() if item is not None else None
        if isinstance(bubble, ChatMessageBubble) and not bubble.is_user:
            bubble.play_reply()

    def show_error(self, message: str, conversation_id: str) -> None:
        """Show a safe retry state only if this request's conversation is open."""
        self.set_busy(False)
        if (conversation_id or None) == self._conversation_id:
            self.status_label.setText(message)
            self.retry_button.setVisible(True)
            self.configure_error_button.setVisible(True)
            if self.stack.currentWidget() is self.home_page:
                self.setup_notice.setText(message)
                self.setup_notice.show()

    def show_stopped(self, conversation_id: str) -> None:
        """Confirm cancellation without appending a stale model response."""
        self.set_busy(False)
        if conversation_id == self._conversation_id:
            self.status_label.setText("已停止生成。可以编辑消息后重新发送。")
            self.retry_button.setVisible(True)

    def clear_error(self) -> None:
        self.status_label.clear()
        self.retry_button.setVisible(False)
        self.setup_notice.setVisible(not self._model_ready)
        self.setup_notice.setText("默认使用设置页中的模型。尚未配置 API Key；附件只会在你选择并确认发送后读取。")

    def current_conversation_id(self) -> str | None:
        """Return the ID currently rendered in the message view."""
        return self._conversation_id

    def _clear_messages(self) -> None:
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        self.messages_layout.addStretch(1)

    def _append_bubble(self, message: ChatMessage) -> None:
        stretch = self.messages_layout.takeAt(self.messages_layout.count() - 1)
        if stretch.widget():
            stretch.widget().deleteLater()
        bubble = ChatMessageBubble(message, user_avatar=self._user_avatar, user_name=self._user_name)
        if isinstance(bubble.avatar, OrbitAvatar):
            bubble.avatar.set_motion_enabled(not self._reduced_motion)
        self.messages_layout.addWidget(bubble)
        self.messages_layout.addStretch(1)

    def set_user_avatar(self, icon: QIcon) -> None:
        """Reuse the local account avatar for current and future user messages."""
        self._user_avatar = icon
        for bubble in self.messages_container.findChildren(ChatMessageBubble):
            bubble.set_user_avatar(icon)

    def set_user_name(self, user_name: str) -> None:
        """Update current and future user captions without rewriting chat history."""
        self._user_name = user_name
        for bubble in self.messages_container.findChildren(ChatMessageBubble):
            bubble.set_user_name(user_name)

    def _scroll_to_bottom(self) -> None:
        self._scroll_timer.start(0)

    def _scroll_to_bottom_now(self) -> None:
        scrollbar = self.message_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
