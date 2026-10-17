"""Reusable Orbit composer with explicit model and request state."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QEnterEvent, QFocusEvent, QPaintEvent, QPainter,
                           QInputMethodEvent, QKeyEvent, QPainterPath, QPen, QTextCursor)
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QFileDialog, QSizePolicy, QVBoxLayout, QWidget)

from filemind.ui.widgets.card import Card
from filemind.ui.widgets.combo_box import StyledComboBox
from filemind.ui.styles.icons import provider_icon
from filemind.ui.styles.theme import COLORS


class ChatTextEdit(QPlainTextEdit):
    """Send on Enter while preserving Shift+Enter for multiline messages."""

    submit = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._composing = False
        self.setTabChangesFocus(True)

    def inputMethodEvent(self, event: QInputMethodEvent) -> None:
        self._composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._composing and event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submit.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class OrbitModelCombo(StyledComboBox):
    """Draw a compact chevron so the provider selector matches Orbit styling."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrame(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        self.update()

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        disabled = not self.isEnabled()
        stroke = COLORS["purple_border"]
        if self.underMouse():
            stroke = COLORS["primary_border"]
        if self.hasFocus():
            stroke = COLORS["purple"]
        fill = QColor(COLORS["purple_soft"] if not disabled else COLORS["disabled_bg"])
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(stroke), 1.2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 13, 13)
        icon_rect = self.rect()
        icon_rect.setX(10)
        icon_rect.setY((self.height() - 24) // 2)
        icon_rect.setWidth(24)
        icon_rect.setHeight(24)
        if self.currentIndex() >= 0:
            self.itemIcon(self.currentIndex()).paint(painter, icon_rect)
        text_left = icon_rect.right() + 10
        text_right = self.width() - 35
        text = self.fontMetrics().elidedText(
            self.currentText(), Qt.TextElideMode.ElideRight, max(0, text_right - text_left)
        )
        painter.setPen(QColor(COLORS["muted"] if disabled else COLORS["text"]))
        metrics = self.fontMetrics()
        baseline = (self.height() - metrics.height()) // 2 + metrics.ascent()
        painter.drawText(text_left, baseline, text)
        center_x = self.width() - 17
        center_y = self.height() / 2
        chevron = QPainterPath()
        chevron.moveTo(center_x - 4, center_y - 2)
        chevron.lineTo(center_x, center_y + 2)
        chevron.lineTo(center_x + 4, center_y - 2)
        painter.setPen(QPen(QColor(COLORS["muted"]), 1.6))
        painter.drawPath(chevron)


class ChatInput(QWidget):
    """Message editor, selected configured model, and send/stop controls."""

    send_requested = Signal(str, object)
    stop_requested = Signal()
    configure_requested = Signal()
    model_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._configured = False
        self._attachments: tuple[Path, ...] = ()
        card = Card(padding=15)
        card.setObjectName("OrbitComposerCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)
        self.editor = ChatTextEdit()
        self.editor.setObjectName("OrbitEditor")
        self.editor.setPlaceholderText("今天有什么可以帮你？（Enter 发送，Shift+Enter 换行）")
        self.editor.setMaximumHeight(96)
        self.editor.submit.connect(self._submit)
        self.editor.textChanged.connect(self._update_send_state)
        card.layout.addWidget(self.editor)

        attachment_row = QHBoxLayout()
        attachment_row.setContentsMargins(4, 0, 4, 0)
        self.attachment_label = QLabel()
        self.attachment_label.setObjectName("OrbitAttachmentSummary")
        self.attachment_label.setVisible(False)
        attachment_row.addWidget(self.attachment_label, 1)
        self.clear_attachments_button = QPushButton("清除")
        self.clear_attachments_button.setObjectName("OrbitAttachmentClear")
        self.clear_attachments_button.setVisible(False)
        self.clear_attachments_button.clicked.connect(self.clear_attachments)
        attachment_row.addWidget(self.clear_attachments_button)
        card.layout.addLayout(attachment_row)

        footer = QHBoxLayout()
        self.attach_button = QPushButton("＋ 添加文件")
        self.attach_button.setObjectName("OrbitAttachButton")
        self.attach_button.setToolTip(
            "选择图片或 UTF-8 文本/代码文件。图片目前需 DeepSeek V4.1 Flash；单文件最大 4 MB。"
        )
        self.attach_button.clicked.connect(self._pick_attachments)
        footer.addWidget(self.attach_button)
        self.privacy_label = QLabel("消息与近期上下文发送至当前服务商；附件仅按本次选择发送。")
        self.privacy_label.setObjectName("Muted")
        self.privacy_label.setWordWrap(True)
        self.privacy_label.setStyleSheet("font-size:9pt;")
        footer.addStretch(1)
        self.model_combo = OrbitModelCombo()
        self.model_combo.setObjectName("OrbitModelSelector")
        self.model_combo.setMinimumWidth(156)
        self.model_combo.setMaximumWidth(196)
        self.model_combo.setMinimumHeight(40)
        self.model_combo.setIconSize(QSize(24, 24))
        self.model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.model_combo.setMinimumContentsLength(9)
        self.model_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.model_combo.activated.connect(lambda _index: self.model_selected.emit(str(self.model_combo.currentData())))
        footer.addWidget(self.model_combo)
        self.configure_button = QPushButton("配置模型")
        self.configure_button.setObjectName("OrbitLinkButton")
        self.configure_button.clicked.connect(self.configure_requested.emit)
        footer.addWidget(self.configure_button)
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("OrbitSendButton")
        self.send_button.setFixedHeight(40)
        self.send_button.clicked.connect(self._submit)
        footer.addWidget(self.send_button)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("OrbitStopButton")
        self.stop_button.setFixedHeight(40)
        self.stop_button.setVisible(False)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        footer.addWidget(self.stop_button)
        card.layout.addLayout(footer)
        card.layout.addWidget(self.privacy_label)
        self.set_model(None, None, None)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setMaximumHeight(236)
        self._update_send_state()

    def reapply_theme(self) -> None:
        """Refresh composer artwork while preserving text and pending attachments."""
        for index in range(self.model_combo.count()):
            self.model_combo.setItemIcon(index, provider_icon(self._provider_id))
        self.model_combo.update()

    def set_model(self, provider_id: str | None, provider_name: str | None, model_name: str | None,
                  has_api_key: bool = False) -> None:
        """Show only the actual active provider/model, never fabricated choices."""
        self._provider_id = provider_id or "custom"
        self._active_model = model_name or ""
        self.model_combo.clear()
        self._configured = bool(provider_name and model_name)
        display_model = "V4.1 Flash" if provider_id == "deepseek" and model_name == "deepseek-flash" else model_name
        label = display_model if self._configured else "尚未配置模型"
        self.model_combo.addItem(provider_icon(provider_id or "custom"), label, model_name)
        self.model_combo.setToolTip(
            f"{provider_name} · {display_model}（API ID：{model_name}）" if self._configured else label
        )
        self.model_combo.setEnabled(self._configured)
        self.configure_button.setVisible(not has_api_key)

    def set_model_options(self, models: list[str], parallel_labels: list[str]) -> None:
        """Offer saved models through the existing rounded picker, keeping its UI."""
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for model in dict.fromkeys([self._active_model, *models]):
            if model:
                label = "V4.1 Flash" if self._provider_id == "deepseek" and model == "deepseek-flash" else model
                self.model_combo.addItem(provider_icon(self._provider_id), label, model)
        if not self.model_combo.count():
            self.model_combo.addItem("尚未配置模型", "")
        self.model_combo.blockSignals(False)
        self.privacy_label.setText("并行发送至：" + "，".join(parallel_labels) + "；附件须关闭并行后发送。"
                                   if parallel_labels else "消息与近期上下文发送至当前服务商；附件仅按本次选择发送。")

    def set_text(self, text: str) -> None:
        """Fill a suggested prompt without submitting it."""
        self.editor.setPlainText(text)
        self.editor.setFocus()
        self.editor.moveCursor(QTextCursor.MoveOperation.End)

    def clear_text(self) -> None:
        """Clear the composer after a message has been accepted."""
        self.editor.clear()

    @property
    def selected_attachments(self) -> tuple[Path, ...]:
        """Return explicitly selected files without reading their contents."""
        return self._attachments

    def clear_attachments(self) -> None:
        """Forget selected files and refresh the compact attachment summary."""
        self._attachments = ()
        self._update_attachment_display()

    def _pick_attachments(self) -> None:
        paths, _selected_filter = QFileDialog.getOpenFileNames(
            self, "添加图片或文本文件", "",
            "支持的附件 (*.png *.jpg *.jpeg *.gif *.webp *.txt *.md *.csv *.json *.py *.java *.c *.h *.cpp *.hpp *.js *.ts *.html *.css *.sql *.log *.xml *.yaml *.yml)",
        )
        if not paths:
            return
        try:
            self.set_attachments((*self._attachments, *(Path(path) for path in paths)))
        except ValueError as error:
            self.attachment_label.setText(str(error))
            self.attachment_label.setToolTip(str(error))
            self.attachment_label.setVisible(True)
            self.clear_attachments_button.setVisible(bool(self._attachments))
            return

    def set_attachments(self, paths: tuple[Path, ...]) -> None:
        """Set selected attachments after checking types, count, and current files."""
        self._attachments = _validate_selection(paths)
        self._update_attachment_display()

    def _update_attachment_display(self) -> None:
        names = "、".join(path.name for path in self._attachments)
        self.attachment_label.setText(f"已添加 {len(self._attachments)} 个文件：{names}" if names else "")
        self.attachment_label.setToolTip(names)
        self.attachment_label.setVisible(bool(names))
        self.clear_attachments_button.setVisible(bool(names))
        self._update_send_state()

    def set_busy(self, busy: bool) -> None:
        """Prevent duplicate sends while leaving stop available."""
        self._busy = busy
        self.editor.setEnabled(not busy)
        self.attach_button.setEnabled(not busy)
        self.clear_attachments_button.setEnabled(not busy)
        self.model_combo.setEnabled(self._configured and not busy)
        self.send_button.setVisible(not busy)
        self.send_button.setEnabled(not busy and bool(self.editor.toPlainText().strip()))
        self.stop_button.setVisible(busy)
        self.stop_button.setEnabled(busy)
        self._update_send_state()

    def _update_send_state(self) -> None:
        self.send_button.setEnabled(not self._busy and bool(self.editor.toPlainText().strip()))

    def _submit(self) -> None:
        if not self._busy and self.editor.toPlainText().strip():
            self.send_requested.emit(self.editor.toPlainText().strip(), self._attachments)


def _validate_selection(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt", ".md", ".csv", ".json",
               ".py", ".java", ".c", ".h", ".cpp", ".hpp", ".js", ".ts", ".html", ".css",
               ".sql", ".log", ".xml", ".yaml", ".yml"}
    unique = tuple(dict.fromkeys(paths))
    if len(unique) > 5:
        raise ValueError("一次最多添加 5 个附件。")
    for path in unique:
        if path.suffix.lower() not in allowed:
            raise ValueError(f"暂不支持 {path.suffix or '无扩展名'} 文件类型。")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"无法添加非普通文件：{path.name}")
        try:
            file_size = path.stat().st_size
        except OSError as error:
            raise ValueError(f"无法访问附件：{path.name}") from error
        if file_size > 4 * 1024 * 1024:
            raise ValueError(f"{path.name} 超过单文件 4 MB 限制。")
    return unique
