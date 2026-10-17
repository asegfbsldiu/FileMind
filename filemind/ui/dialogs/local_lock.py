"""A local setup/unlock dialog independent of model configuration."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QThreadPool
from PySide6.QtGui import QColor, QCloseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from filemind.storage.local_lock import LocalLockStore
from filemind.ui.branding import application_icon
from filemind.ui.styles.theme import COLORS
from filemind.ui.workers import TaskWorker


class LockArtwork(QWidget):
    """Paint a quiet directory motif without remote images or animations."""

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / 310, self.height() / 240)
        painter.translate((self.width() - 310 * scale) / 2, (self.height() - 240 * scale) / 2)
        painter.scale(scale, scale)
        painter.setPen(QPen(QColor("#C4D0F5"), 2))
        painter.drawLine(60, 67, 60, 193)
        for position, text in ((92, "学习资料"), (144, "项目文件"), (196, "灵感与笔记")):
            painter.drawLine(60, position, 92, position)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawRoundedRect(QRectF(90, position - 20, 196, 40), 11, 11)
            painter.setBrush(QColor(COLORS["primary"]))
            painter.drawRoundedRect(QRectF(104, position - 7, 19, 14), 3, 3)
            painter.setPen(QColor(COLORS["text"]))
            painter.drawText(QRectF(136, position - 18, 140, 36), Qt.AlignmentFlag.AlignVCenter, text)
            painter.setPen(QPen(QColor("#C4D0F5"), 2))
        painter.setPen(QColor(COLORS["primary"]))
        painter.drawText(QRectF(40, 23, 240, 30), Qt.AlignmentFlag.AlignVCenter, "我的工作空间")


class LocalLockDialog(QDialog):
    """Derive passwords on a worker; expose recovery codes only once."""

    def __init__(self, store: LocalLockStore, mode: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.mode = mode or ("unlock" if store.is_configured() else "setup")
        self._worker: TaskWorker | None = None
        self._close_pending = False
        self.setObjectName("LocalLockDialog")
        self.setWindowTitle("FileMind · 本机工作空间")
        self.setWindowIcon(application_icon())
        self.setMinimumSize(760, 600)
        self.resize(920, 660)
        self._build_ui()
        self._set_mode(self.mode)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)
        root.addWidget(self._poster(), 4)
        panel = QFrame()
        panel.setObjectName("LockCard")
        column = QVBoxLayout(panel)
        column.setContentsMargins(30, 28, 30, 24)
        column.setSpacing(14)
        column.addStretch(1)
        self.title_label = QLabel()
        self.title_label.setObjectName("LockTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("Muted")
        self.subtitle.setWordWrap(True)
        column.addWidget(self.title_label)
        column.addWidget(self.subtitle)
        self.fields = QWidget()
        self._build_fields()
        column.addWidget(self.fields)
        self.status_label = QLabel()
        self.status_label.setObjectName("LockError")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        column.addWidget(self.status_label)
        self._build_recovery(column)
        self.primary_button = QPushButton()
        self.primary_button.setObjectName("PrimaryButton")
        self.primary_button.setMinimumHeight(42)
        self.primary_button.setDefault(True)
        self.primary_button.clicked.connect(self._submit)
        column.addWidget(self.primary_button)
        self.switch_button = QPushButton("忘记密码？使用恢复码")
        self.switch_button.setObjectName("LockLink")
        self.switch_button.clicked.connect(self._switch_mode)
        column.addWidget(self.switch_button)
        column.addStretch(1)
        note = QLabel("这是应用级本地锁屏，不等同于 Windows 账户安全或磁盘加密。")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        column.addWidget(note)
        root.addWidget(panel, 5)

    def _poster(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("LockPoster")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(28, 30, 28, 24)
        brand = QLabel("FileMind")
        brand.setObjectName("BrandName")
        layout.addWidget(brand)
        layout.addStretch(1)
        headline = QLabel("文件有序，\n思路清晰。")
        headline.setObjectName("LockHeadline")
        layout.addWidget(headline)
        caption = QLabel("你的文件整理与 AI 工作空间")
        caption.setObjectName("Muted")
        caption.setWordWrap(True)
        layout.addWidget(caption)
        art = LockArtwork()
        art.setMinimumHeight(200)
        layout.addWidget(art)
        layout.addStretch(1)
        privacy = QLabel("本机密码仅用于解锁应用，\n不会发送给 AI 服务商。")
        privacy.setObjectName("Muted")
        layout.addWidget(privacy)
        return panel

    def _build_fields(self) -> None:
        layout = QVBoxLayout(self.fields)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(10)
        self.current_edit = self._password_field("当前密码")
        self.recovery_edit = QLineEdit()
        self.recovery_edit.setPlaceholderText("首次设置时保存的恢复码")
        self.recovery_edit.setAccessibleName("恢复码")
        self.password_edit = self._password_field("密码")
        self.confirm_edit = self._password_field("再次输入新密码")
        for editor in (self.current_edit, self.recovery_edit, self.password_edit, self.confirm_edit):
            layout.addWidget(editor)
            editor.returnPressed.connect(self._submit)
        self.show_password = QCheckBox("显示密码")
        self.show_password.toggled.connect(self._toggle_password)
        layout.addWidget(self.show_password)
        remembers = self.store.protector is not None
        self.remember_checkbox = QCheckBox("在此用户下记住解锁 7 天" if remembers
                                           else "当前系统不支持安全记住解锁")
        self.remember_checkbox.setToolTip(
            "保存由系统凭据保护（Windows DPAPI）的随机令牌，不保存密码；手动锁定或修改密码会撤销。"
            if remembers else
            "安全记住解锁依赖 Windows DPAPI。当前系统请每次输入密码；API Key 可用环境变量或本机明文配置提供。")
        self.remember_checkbox.setEnabled(remembers)
        layout.addWidget(self.remember_checkbox)

    @staticmethod
    def _password_field(placeholder: str) -> QLineEdit:
        editor = QLineEdit()
        editor.setPlaceholderText(placeholder)
        editor.setAccessibleName(placeholder)
        editor.setEchoMode(QLineEdit.EchoMode.Password)
        editor.setMaxLength(1024)
        editor.setMinimumHeight(38)
        return editor

    def _build_recovery(self, layout: QVBoxLayout) -> None:
        self.recovery_panel = QWidget()
        column = QVBoxLayout(self.recovery_panel)
        column.setContentsMargins(0, 0, 0, 0)
        note = QLabel("请将恢复码保存到安全位置。它只显示这一次，可在忘记密码时重设密码。")
        note.setWordWrap(True)
        self.recovery_display = QLineEdit()
        self.recovery_display.setReadOnly(True)
        self.recovery_display.setAccessibleName("一次性显示的恢复码")
        self.saved_checkbox = QCheckBox("我已安全保存恢复码")
        self.saved_checkbox.toggled.connect(lambda checked: self.primary_button.setEnabled(checked))
        column.addWidget(note)
        column.addWidget(self.recovery_display)
        column.addWidget(self.saved_checkbox)
        self.recovery_panel.hide()
        layout.addWidget(self.recovery_panel)

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        titles = {"setup": "创建本机密码", "unlock": "欢迎回来", "change": "修改本机密码", "reset": "使用恢复码"}
        self.title_label.setText(titles[mode])
        self.subtitle.setText("首次设置后，下次启动即可使用密码解锁。" if mode == "setup" else
                              "仅解锁本机 FileMind，文件和模型配置保持在原位置。")
        self.current_edit.setVisible(mode == "change")
        self.recovery_edit.setVisible(mode == "reset")
        self.confirm_edit.setVisible(mode != "unlock")
        self.password_edit.setPlaceholderText("输入本机密码" if mode == "unlock" else "新密码（至少 8 个字符）")
        self.remember_checkbox.setVisible(mode in {"setup", "unlock"})
        self.switch_button.setVisible(mode in {"unlock", "reset"})
        self.switch_button.setText("返回密码解锁" if mode == "reset" else "忘记密码？使用恢复码")
        self.primary_button.setText("解锁工作空间" if mode == "unlock" else "保存并继续")
        self.status_label.clear()
        for editor in (self.current_edit, self.recovery_edit, self.password_edit, self.confirm_edit):
            editor.clear()
        focus = {"reset": self.recovery_edit, "change": self.current_edit}.get(mode, self.password_edit)
        focus.setFocus()

    def _switch_mode(self) -> None:
        self._set_mode("unlock" if self.mode == "reset" else "reset")

    def _toggle_password(self, visible: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        for editor in (self.current_edit, self.password_edit, self.confirm_edit):
            editor.setEchoMode(mode)

    def _submit(self) -> None:
        if self._worker is not None:
            return
        if not self.recovery_panel.isHidden():
            if self.saved_checkbox.isChecked():
                self.recovery_display.clear()
                self.accept()
            return
        password = self.password_edit.text()
        if self.mode != "unlock" and password != self.confirm_edit.text():
            self.status_label.setText("两次输入的密码不一致。")
            return
        remember = self.remember_checkbox.isChecked()
        current, recovery = self.current_edit.text(), self.recovery_edit.text()
        operations = {
            "setup": lambda: self.store.initialize(password, remember),
            "unlock": lambda: self.store.unlock(password, remember),
            "change": lambda: self.store.change_password(current, password),
            "reset": lambda: self.store.reset_password(recovery, password),
        }
        action = operations[self.mode]
        self._worker = TaskWorker(lambda _progress, _cancel: action())
        self._worker.signals.completed.connect(self._completed)
        self._worker.signals.failed.connect(self._failed)
        self._set_busy(True)
        QThreadPool.globalInstance().start(self._worker)

    def _set_busy(self, busy: bool) -> None:
        self.fields.setEnabled(not busy)
        self.primary_button.setEnabled(not busy)
        self.switch_button.setEnabled(not busy)
        if busy:
            self.status_label.setText("正在安全验证，请稍候…")

    def _completed(self, result: object) -> None:
        self._worker = None
        self._set_busy(False)
        for editor in (self.current_edit, self.recovery_edit, self.password_edit, self.confirm_edit):
            editor.clear()
        if self._close_pending:
            super().reject()
        elif result is False:
            self.status_label.setText("密码不正确，请重试；也可以使用恢复码重设。")
            self.password_edit.setFocus()
        elif self.mode in {"setup", "reset"}:
            self.fields.hide()
            self.switch_button.hide()
            self.recovery_panel.show()
            self.recovery_display.setText(str(result))
            self.status_label.clear()
            self.title_label.setText("保存你的恢复码")
            self.primary_button.setText("进入 FileMind")
            self.primary_button.setEnabled(False)
        else:
            self.accept()

    def _failed(self, message: str) -> None:
        self._worker = None
        self._set_busy(False)
        self.status_label.setText(message.removeprefix("LocalLockError: "))
        if self._close_pending:
            super().reject()

    def reject(self) -> None:
        """Wait for atomic credential writes before disposing of the dialog."""
        if self._worker is not None:
            self._close_pending = True
            self.status_label.setText("正在完成安全写入，随后关闭…")
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None:
            self.reject()
            event.ignore()
        else:
            event.accept()
