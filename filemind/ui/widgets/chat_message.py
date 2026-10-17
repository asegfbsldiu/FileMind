"""Markdown-aware conversation message bubble for Orbit."""

from __future__ import annotations

import math

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QPixmap, QResizeEvent, QTextDocument
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy, QTextBrowser,
                               QVBoxLayout, QWidget)

from filemind.chat_models import ChatMessage
from filemind.ui.widgets.local_account import avatar_icon
from filemind.ui.widgets.orbit_avatar import OrbitAvatar
from filemind.ui.styles.theme import resolve_qss


class LocalMarkdownView(QTextBrowser):
    """Render text without automatically loading model-supplied local images."""

    def loadResource(self, resource_type: int, name: QUrl) -> object:
        if resource_type == QTextDocument.ResourceType.ImageResource:
            return QPixmap()
        return None


class ChatMessageBubble(QWidget):
    """Render a user or assistant message with safe, local Markdown display."""

    def __init__(self, message: ChatMessage, parent: QWidget | None = None, *,
                 user_avatar: QIcon | None = None, user_name: str = "你") -> None:
        super().__init__(parent)
        self.is_user = message.role == "user"
        self._message_content = message.content
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._resize_to_document)
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 8, 4, 8)
        row.setSpacing(10)
        self.avatar = QLabel() if self.is_user else OrbitAvatar(36)
        self.avatar.setObjectName("OrbitUserAvatar" if self.is_user else "OrbitAssistantAvatar")
        self.avatar.setAccessibleName("用户头像" if self.is_user else "Orbit AI 头像")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFixedSize(36, 36)
        if self.is_user:
            icon = user_avatar if user_avatar is not None and not user_avatar.isNull() else avatar_icon(None)
            self.set_user_avatar(icon)
            row.addStretch(1)
        else:
            row.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)
        self.bubble = QFrame()
        self.bubble.setObjectName("OrbitUserBubble" if self.is_user else "OrbitAssistantBubble")
        self.bubble.setMaximumWidth(540 if self.is_user else 860)
        column = QVBoxLayout(self.bubble)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(7)
        self.caption = QLabel(user_name if self.is_user else "Orbit")
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setObjectName("OrbitMessageCaption")
        self.caption.setWordWrap(True)
        self.caption.setMinimumWidth(0)
        column.addWidget(self.caption)
        self._build_content(message, column)
        row.addWidget(self.bubble, 0 if self.is_user else 1)
        if self.is_user:
            row.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)
        self._resize_to_document()

    def _build_content(self, message: ChatMessage, column: QVBoxLayout) -> None:
        self.attachment_label = QLabel("  ·  ".join(message.attachments))
        self.attachment_label.setTextFormat(Qt.TextFormat.PlainText)
        self.attachment_label.setObjectName("OrbitMessageAttachments")
        self.attachment_label.setWordWrap(True)
        self.attachment_label.setVisible(bool(message.attachments))
        column.addWidget(self.attachment_label)
        self.content = LocalMarkdownView()
        self.content.setFrameShape(QFrame.Shape.NoFrame)
        self.content.setObjectName("OrbitMessageContent")
        self.content.setReadOnly(True)
        self.content.setOpenExternalLinks(False)
        self.content.setOpenLinks(False)
        self.content.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content.setMinimumHeight(34)
        self.content.setMinimumWidth(0)
        self.content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.content.document().setDefaultFont(self.font())
        self.reapply_theme()
        column.addWidget(self.content)

    def reapply_theme(self) -> None:
        """Re-render local Markdown styles without changing stored chat messages."""
        self.content.document().setDefaultStyleSheet(resolve_qss(
            "pre, code { font-family: Consolas, 'Cascadia Code', monospace; "
            "background: __surface__; color: __text__; }"
            "blockquote { color: __muted__; border-left: 3px solid __purple_border__; }"
        ))
        if self.is_user:
            self.content.setPlainText(self._message_content)
        else:
            self.content.setMarkdown(self._message_content)
        self._resize_timer.start(0)

    def set_user_avatar(self, icon: QIcon) -> None:
        """Update the local visual identity without changing stored message data."""
        if self.is_user:
            self.avatar.setPixmap(icon.pixmap(QSize(32, 32), self.devicePixelRatioF()))

    def set_user_name(self, user_name: str) -> None:
        """Change only the local caption, keeping model messages untouched."""
        if self.is_user:
            self.caption.setText(user_name)
            self.caption.setToolTip(user_name)

    def play_reply(self) -> None:
        """Briefly animate a new assistant answer without animating saved history."""
        if isinstance(self.avatar, OrbitAvatar):
            self.avatar.set_state("replying")

    def _resize_to_document(self) -> None:
        document = self.content.document()
        document.setTextWidth(max(120, self.content.viewport().width()))
        height = max(34, math.ceil(document.size().height()) + 8)
        if self.content.height() != height:
            self.content.setFixedHeight(height)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._resize_timer.start(0)
