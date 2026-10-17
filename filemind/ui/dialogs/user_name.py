"""Edit a local display name without involving model configuration or chat data."""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from filemind.storage.workspace import WorkspaceError, WorkspaceStore, validate_user_name


class UserNameDialog(QDialog):
    """Validate and persist the local name before accepting the dialog."""

    def __init__(self, user_name: str, store: WorkspaceStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.user_name = user_name
        self.setWindowTitle("修改用户名")
        self.setObjectName("UserNameDialog")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        title = QLabel("修改用户名")
        title.setObjectName("SettingsSectionTitle")
        detail = QLabel("用于本机账户和聊天中的显示名称，最多 32 个字符。名称仅在本机保存。")
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        self.name_edit = QLineEdit(user_name)
        self.name_edit.setAccessibleName("用户名")
        self.name_edit.setPlaceholderText("输入你的用户名")
        self.name_edit.setMaxLength(128)
        self.error_label = QLabel()
        self.error_label.setObjectName("UserNameError")
        self.error_label.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        for widget in (title, detail, self.name_edit, self.error_label):
            layout.addWidget(widget)
        layout.addLayout(buttons)
        self.name_edit.textChanged.connect(self._validate)
        self.name_edit.selectAll()
        self.name_edit.setFocus()
        self._validate()

    def _validate(self) -> None:
        try:
            validate_user_name(self.name_edit.text())
        except WorkspaceError as error:
            self.error_label.setText(str(error))
            self.save_button.setEnabled(False)
            return
        self.error_label.clear()
        self.save_button.setEnabled(True)

    def _save(self) -> None:
        try:
            name = self.store.save_user_name(self.name_edit.text())
        except (WorkspaceError, OSError) as error:
            message = str(error) if isinstance(error, WorkspaceError) else "保存失败，请检查本机配置目录权限。"
            self.error_label.setText(message)
            return
        self.user_name = name
        self.accept()
