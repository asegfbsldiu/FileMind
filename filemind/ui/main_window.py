"""Main Qt window, navigation, and application lifecycle."""

from __future__ import annotations

import logging
from threading import Event
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QSize, QThreadPool, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QDialog,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from filemind.ai.base import ProgressCallback
from filemind.ai.chat_service import ChatService
from filemind.ai.adapters import build_provider
from filemind.ai.chat_result import MultiModelResult
from filemind.ai.model_config import ModelConfig
from filemind.ai.multi_model import run_models
from filemind.ai.chat_prompts import ORBIT_SYSTEM_PROMPT
from filemind.ai.openai_compatible import AIServiceError, OpenAICompatibleClient
from filemind.ai.providers import PROVIDER_BY_ID, is_local_connection
from filemind.ai.schemas import file_metadata
from filemind.chat_models import ChatConversation
from filemind.storage.chat_history import MAX_CONVERSATIONS, MAX_MESSAGE_LENGTH, ChatHistoryError, ChatHistoryStore
from filemind.storage.history import OperationHistory
from filemind.storage.settings import AISettings, SettingsError, SettingsStore
from filemind.storage.local_lock import LocalLockStore
from filemind.storage.workspace import WorkspaceError, WorkspaceStore
from filemind.ui.widgets.local_account import LocalAccountButton, avatar_icon
from filemind.ui.branding import application_icon
from filemind.ui.dialogs.user_name import UserNameDialog
from filemind.ui.pages.assistant_page import AssistantPage
from filemind.ui.pages.history_page import HistoryPage
from filemind.ui.pages.organize_page import OrganizePage
from filemind.ui.pages.settings_page import SettingsPage
from filemind.ui.pages.local_settings_page import LocalSettingsPage
from filemind.ui.pages.conversion_page import ConversionPage
from filemind.ui.dialogs.plan_preview import PlanPreviewDialog
from filemind.ui.styles.icons import svg_icon
from filemind.ui.styles.theme import COLORS, apply_theme
from filemind.ui.widgets.conversation_row import ROW_HEIGHT, ConversationList, ConversationRow
from filemind.ui.widgets.privacy_dialog import OrbitPrivacyDialog
from filemind.core.organization_presets import classify_with_preset
from filemind.core.executor import ExecutionResult, execute_plan, undo_record
from filemind.core.planner import build_plan
from filemind.core.scanner import scan_files
from filemind.models import FileSuggestion, OperationPlan, OperationRecord
from filemind.ui.workers import TaskWorker


NAVIGATION_ITEMS: tuple[tuple[str, str, str, str, str], ...] = (
    ("organize", "文件整理", "organize", "文件整理", "选择文件夹，检查本地整理建议并确认执行。"),
    ("assistant", "Orbit AI 助手", "assistant", "Orbit AI 助手", "你的智能工作伙伴。"),
    ("conversion", "格式转换", "convert", "文件格式转换", "选择一个文件，在本机转换并保存到新位置。"),
    ("history", "整理历史", "history", "整理历史", "查看操作结果；需要时可以安全撤销。"),
    ("settings", "模型配置", "settings", "模型配置", "管理服务商、API 连接与多模型并行调用。"),
)
PAGE_INFO = {key: (title, subtitle) for key, _label, _icon, title, subtitle in NAVIGATION_ITEMS}
PAGE_INFO["appsettings"] = ("设置", "外观、本机工作空间与数据隐私。")
LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """The single official FileMind desktop shell."""

    local_auth_requested = Signal(str)
    organization_phase = Signal(int, str)

    def __init__(self, settings_store: SettingsStore | None = None,
                 chat_history: ChatHistoryStore | None = None,
                 lock_store: LocalLockStore | None = None,
                 workspace_store: WorkspaceStore | None = None) -> None:
        super().__init__()
        # Qt uses the application display name when no custom caption is set.
        self.setWindowTitle("")
        self.setWindowIcon(application_icon())
        self.resize(1280, 850)
        self.setMinimumSize(1024, 700)
        self.settings_store = settings_store or SettingsStore()
        self.chat_history = chat_history or ChatHistoryStore()
        self.lock_store = lock_store
        self._initialize_workspace(workspace_store, settings_store)
        self._build_shell()
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: list[TaskWorker] = []
        self._active_worker: TaskWorker | None = None
        self._active_task_kind: str | None = None
        self._folder_generation = 0
        self._preview_dialog: PlanPreviewDialog | None = None
        self._chat_worker: TaskWorker | None = None
        self._chat_conversation_id: str | None = None
        self._chat_retry_attachments: dict[str, tuple[Path, ...]] = {}
        self._history: OperationHistory | None = None
        self._close_pending = False
        self.organize_page.scan_requested.connect(lambda folder: self._scan_folder(folder, open_preview=False))
        self.organize_page.folder_selected.connect(lambda folder: self._select_directory(folder, analyze=False))
        self.organize_page.import_requested.connect(self._scan_imported_files)
        self.organize_page.plan_invalidated.connect(self._close_plan_preview)
        self.organization_phase.connect(self._organization_phase_changed)
        self.organize_page.clear_requested.connect(self._clear_directory)
        self.organize_page.preview_requested.connect(self._open_plan_preview)
        self.organize_page.execute_requested.connect(self._confirm_execution)
        self.organize_page.history_requested.connect(lambda: self._show_page("history"))
        self.organize_page.settings_requested.connect(lambda: self._show_page("settings"))
        self.assistant_page.message_submitted.connect(self._send_chat_message)
        self.assistant_page.retry_requested.connect(self._retry_chat_message)
        self.assistant_page.stop_requested.connect(self._cancel_chat_task)
        self.assistant_page.configure_requested.connect(lambda: self._show_page("settings"))
        self.settings_page.configuration_changed.connect(self._refresh_assistant_model)
        self._connect_workspace_actions()
        self.new_chat_button.clicked.connect(self._new_chat)
        self.conversation_list.itemClicked.connect(self._select_chat_item)
        self.conversation_list.currentRowChanged.connect(self._update_conversation_selection)
        self._refresh_conversation_list()
        self._refresh_assistant_model()
        self._show_page("organize")
        self.conversion_page.job_finished.connect(self._conversion_finished)
        self.organize_page.layout_changed.connect(self._organizer_resized)
        QTimer.singleShot(0, self._restore_organizer_height)

    def _connect_workspace_actions(self) -> None:
        self.organize_page.cancel_button.clicked.connect(self._cancel_task)
        self.history_page.refresh_requested.connect(self._refresh_history)
        self.history_page.undo_requested.connect(self._confirm_undo)
        self.history_page.cancel_requested.connect(self._cancel_task)
        self.settings_page.test_requested.connect(self._test_ai_connection)
        self.settings_page.cancel_requested.connect(self._cancel_task)
        self._connect_model_controls()
        self.local_settings_page.local_auth_requested.connect(self._request_local_auth)
        self.local_settings_page.set_local_lock_available(self.lock_store is not None)
        self.local_settings_page.appearance_changed.connect(self._apply_appearance)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._system_scheme_changed)

    def _initialize_workspace(self, store: WorkspaceStore | None, settings: object) -> None:
        path = getattr(settings, "settings_path", None)
        self.workspace_store = store or (WorkspaceStore(path.with_name("workspace.json")) if path else
                                        WorkspaceStore(memory=settings is not None))
        self._avatar_worker: TaskWorker | None = None
        try:
            preferences = self.workspace_store.load()
        except WorkspaceError:
            from filemind.storage.workspace import WorkspacePreferences
            preferences = WorkspacePreferences()
        self._sidebar_width = preferences.sidebar_width
        self._sidebar_collapsed = preferences.sidebar_collapsed
        self._organizer_height = preferences.organizer_height
        self._reduced_motion = preferences.reduced_motion
        self._user_name = preferences.user_name
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(200)
        self._layout_timer.timeout.connect(self._save_workspace_layout)
        self._initialize_appearance()

    def _initialize_appearance(self) -> None:
        getter = getattr(self.settings_store, "get_appearance", None)
        try:
            self._appearance = getter() if callable(getter) else "light"
        except (SettingsError, OSError, ValueError):
            self._appearance = "light"
            LOGGER.warning("Appearance preference could not be read; using light theme.")
        apply_theme(QApplication.instance(), self._appearance)

    def _apply_appearance(self, appearance: str) -> None:
        self._appearance = appearance
        apply_theme(QApplication.instance(), appearance)
        for widget in self.findChildren(QWidget):
            refresh = getattr(widget, "reapply_theme", None)
            if callable(refresh):
                refresh()
            widget.update()
        self.sidebar_toggle.setIcon(svg_icon("sidebar", COLORS["muted"]))
        self.local_settings_action.setIcon(svg_icon("settings", COLORS["muted"]))
        for key, _label, icon, _title, _subtitle in NAVIGATION_ITEMS:
            self.nav_buttons[key].setIcon(svg_icon(icon, COLORS["muted"]))

    def _system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._appearance == "system":
            self._apply_appearance("system")

    def _connect_model_controls(self) -> None:
        self.settings_page.parallel_test_requested.connect(self._test_multiple_models)
        self.settings_page.refresh_models_requested.connect(self._refresh_local_models)
        self.settings_page.ollama_models_requested.connect(self._detect_ollama_models)
        for composer in (self.assistant_page.home_composer, self.assistant_page.chat_composer):
            composer.model_selected.connect(self._select_orbit_model)

    def _select_orbit_model(self, model: str) -> None:
        """Switch only the model field, preserving the saved endpoint and credentials."""
        try:
            settings = self.settings_store.load()
            self.settings_store.set_active_model(settings.provider_id, model)
        except (SettingsError, OSError, ValueError) as error:
            self.assistant_page.show_error(f"模型切换失败：{error}", self._chat_conversation_id or "")
        self._refresh_assistant_model()

    def _refresh_orbit_choices(self, settings: AISettings) -> None:
        loader = getattr(self.settings_store, "load_models", None)
        if not callable(loader):
            return
        try:
            configs = loader()
            models = [config.model for config in configs if config.provider == settings.provider_id
                      and config.base_url.rstrip("/") == settings.base_url.rstrip("/")]
            models.extend(settings.model_options)
            parallel = self.settings_store.is_parallel_mode_enabled()
            labels = [config.label for config in configs if config.enabled] if parallel else []
            for composer in (self.assistant_page.home_composer, self.assistant_page.chat_composer):
                composer.set_model_options(models, labels)
        except (SettingsError, OSError, ValueError) as error:
            self.settings_page.multi_status.setText(f"模型列表读取失败：{error}")

    def _refresh_assistant_model(self) -> None:
        """Reflect the current shared provider profile without exposing its key."""
        try:
            settings = self.settings_store.load()
        except (SettingsError, OSError, ValueError):
            self.assistant_page.set_model(None, None, None, False)
            self.organize_page.set_ai_configuration_status("配置读取失败：请检查设置文件和系统凭据存储。", False)
            return
        preset = PROVIDER_BY_ID.get(settings.provider_id)
        provider_name = preset.name if preset else settings.provider_id
        self.assistant_page.set_model(settings.provider_id, provider_name, settings.model or None,
                                      bool(settings.api_key.strip()) or settings.local)
        self._refresh_orbit_choices(settings)
        is_ready = _is_usable_ai_settings(settings)
        if is_ready:
            self.organize_page.set_ai_configuration_status(
                f"已配置 {provider_name} · {settings.model}，尚未确认当前连接状态。", True
            )
        elif not settings.api_key.strip() and not settings.local:
            self.organize_page.set_ai_configuration_status("未配置：缺少 API Key。", False)
        elif not settings.base_url.strip():
            self.organize_page.set_ai_configuration_status("未配置：Base URL 为空。", False)
        else:
            self.organize_page.set_ai_configuration_status("未配置：模型名称为空。", False)

    def _refresh_conversation_list(self) -> None:
        """Reload recent Orbit sessions from their independent local store."""
        try:
            conversations = self.chat_history.list_conversations()
        except ChatHistoryError as error:
            self.conversation_list.clear()
            self.conversation_list.setVisible(False)
            self.conversation_count.setText("—")
            self.conversation_empty.setText("本地对话暂时无法读取\n请检查记录文件后重试")
            self.conversation_empty.show()
            self.recent_empty_filler.show()
            self.assistant_page.show_error(str(error), self._chat_conversation_id or "")
            return
        self.conversation_list.clear()
        self.conversation_list.setVisible(bool(conversations))
        self.conversation_empty.setVisible(not conversations)
        for conversation in conversations:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, conversation.conversation_id)
            item.setToolTip(f"{len(conversation.messages)} 条消息")
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self.conversation_list.addItem(item)
            row = ConversationRow(conversation.conversation_id, conversation.title, self.conversation_list,
                                  conversation.updated_at, len(conversation.messages))
            row.activated.connect(self._select_conversation_id)
            row.delete_requested.connect(self._delete_chat_by_id)
            self.conversation_list.setItemWidget(item, row)
            if conversation.conversation_id == self._chat_conversation_id:
                self.conversation_list.setCurrentItem(item)
        self._update_conversation_selection()
        self._filter_conversations()

    def _filter_conversations(self, *_args: object) -> None:
        query = self.conversation_search.text().strip().casefold()
        total = self.conversation_list.count()
        matched = 0
        for index in range(total):
            item = self.conversation_list.item(index)
            row = self.conversation_list.itemWidget(item)
            visible = isinstance(row, ConversationRow) and query in row.full_title.casefold()
            item.setHidden(not visible)
            matched += int(visible)
        self.conversation_count.setText(f"{matched}/{total}" if query else str(total))
        self.conversation_count.setToolTip(f"本机共 {total} 段对话；保留最近 {MAX_CONVERSATIONS} 段，不按天清除。")
        self.conversation_list.setVisible(matched > 0)
        self.conversation_empty.setVisible(matched == 0)
        self.recent_empty_filler.setVisible(matched == 0)
        self.conversation_empty.setText("没有匹配的对话\n试试其他标题关键词" if query else
                                        "还没有最近对话\n新建一段对话开始使用 Orbit")

    def _toggle_conversation_search(self) -> None:
        visible = self.conversation_search.isHidden()
        self.conversation_search.setVisible(visible)
        self.conversation_search_button.setChecked(visible)
        if visible:
            self.conversation_search.setFocus()
        else:
            self.conversation_search.clear()

    def _update_conversation_selection(self, _row: int = -1) -> None:
        for index in range(self.conversation_list.count()):
            item = self.conversation_list.item(index)
            row = self.conversation_list.itemWidget(item)
            if isinstance(row, ConversationRow):
                row.set_selected(item is self.conversation_list.currentItem())

    def _new_chat(self) -> None:
        """Create and show a new empty local Orbit conversation."""
        try:
            conversation = self.chat_history.create_conversation()
        except (ChatHistoryError, OSError) as error:
            QMessageBox.warning(self, "无法新建对话", str(error))
            return
        self._chat_conversation_id = conversation.conversation_id
        self.assistant_page.set_conversation(None)
        self.assistant_page.set_busy(self._chat_worker is not None, self._chat_conversation_id)
        self._show_page("assistant")
        self._refresh_conversation_list()

    def _select_chat_item(self, item: QListWidgetItem) -> None:
        """Load one selected conversation without changing an in-flight request."""
        conversation_id = str(item.data(Qt.ItemDataRole.UserRole))
        self._select_conversation_id(conversation_id)

    def _select_conversation_id(self, conversation_id: str) -> None:
        """Load a conversation selected from its compact sidebar row."""
        for index in range(self.conversation_list.count()):
            item = self.conversation_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == conversation_id:
                self.conversation_list.setCurrentItem(item)
                break
        try:
            conversation = self.chat_history.get_conversation(conversation_id)
        except ChatHistoryError as error:
            QMessageBox.warning(self, "无法读取对话", str(error))
            return
        if conversation is None:
            self._refresh_conversation_list()
            return
        self._chat_conversation_id = conversation_id
        self.assistant_page.set_conversation(conversation)
        self._show_page("assistant")

    def _delete_selected_chat(self) -> None:
        """Delete only the selected Orbit history record after confirmation."""
        item = self.conversation_list.currentItem()
        if item is None:
            return
        conversation_id = str(item.data(Qt.ItemDataRole.UserRole))
        self._delete_chat_by_id(conversation_id)

    def _delete_chat_by_id(self, conversation_id: str) -> None:
        """Delete a requested chat after explicit confirmation."""
        answer = QMessageBox.question(self, "删除对话", "删除这段本地对话记录？此操作不可撤销。",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._chat_worker is not None and conversation_id == self._chat_conversation_id:
            self._chat_worker.cancel()
        try:
            self.chat_history.delete_conversation(conversation_id)
        except (ChatHistoryError, OSError) as error:
            QMessageBox.warning(self, "无法删除对话", str(error))
            return
        if conversation_id == self._chat_conversation_id:
            self._chat_conversation_id = None
            self.assistant_page.set_conversation(None)
        self._chat_retry_attachments.pop(conversation_id, None)
        self._refresh_conversation_list()

    def _send_chat_message(self, text: str, attachments: object = ()) -> None:
        """Persist a user turn only after configuration and disclosure checks."""
        if self._chat_worker is not None or self._active_worker is not None:
            return
        selected_paths = tuple(path for path in attachments if isinstance(path, Path)) \
            if isinstance(attachments, (tuple, list)) else ()
        if self._send_parallel_if_enabled(text, selected_paths):
            return
        try:
            settings = self.settings_store.load()
        except (SettingsError, OSError, ValueError) as error:
            self.assistant_page.show_error(f"模型配置读取失败：{error}", self._chat_conversation_id or "")
            return
        if not _is_usable_ai_settings(settings):
            QMessageBox.information(self, "请先配置模型", "Orbit 默认选择设置页中的 DeepSeek 模型。请先填写自己的 API Key。")
            self._show_page("settings")
            return
        if selected_paths and not self._confirm_attachment_upload(settings, selected_paths):
            return
        if not self._confirm_chat_privacy(settings):
            return
        try:
            conversation = self._ensure_chat_conversation()
            conversation = self.chat_history.add_message(
                conversation.conversation_id, "user", text,
                tuple(path.name for path in selected_paths),
            )
        except (ChatHistoryError, OSError, ValueError) as error:
            QMessageBox.warning(self, "无法保存消息", str(error))
            return
        self.assistant_page.accept_submission()
        self.assistant_page.show_conversation(conversation)
        self._refresh_conversation_list()
        self._chat_retry_attachments[conversation.conversation_id] = selected_paths
        self._start_chat_request(conversation.conversation_id, settings, selected_paths)

    def _ensure_chat_conversation(self) -> ChatConversation:
        """Return the active session or create one when sending from the home page."""
        conversation = (self.chat_history.get_conversation(self._chat_conversation_id)
                        if self._chat_conversation_id else None)
        if conversation is None:
            conversation = self.chat_history.create_conversation()
            self._chat_conversation_id = conversation.conversation_id
        return conversation

    def _send_parallel_if_enabled(self, text: str, paths: tuple[Path, ...]) -> bool:
        """Handle an explicitly enabled batch, never silently fall back to one model."""
        enabled = getattr(self.settings_store, "is_parallel_mode_enabled", None)
        if not callable(enabled):
            return False
        try:
            if not enabled():
                return False
            if paths:
                raise ValueError("并行模式不发送附件；请先关闭并行，再单独确认附件发送。")
            configs = [config for config in self.settings_store.load_models() if config.enabled]
            if not 1 <= len(configs) <= 4:
                raise ValueError("请在设置中启用 1–4 个模型，或关闭并行模式。")
            if not self._confirm_multi_model_privacy(configs):
                return True
            conversation = self._ensure_chat_conversation()
            conversation = self.chat_history.add_message(conversation.conversation_id, "user", text)
            self.assistant_page.accept_submission()
            self.assistant_page.show_conversation(conversation)
            self._refresh_conversation_list()
            self._start_parallel_request(conversation.conversation_id, configs)
        except (SettingsError, ChatHistoryError, OSError, ValueError) as error:
            self.assistant_page.show_error(str(error), self.assistant_page.current_conversation_id() or "")
        return True

    def _confirm_multi_model_privacy(self, configs: list[ModelConfig]) -> bool:
        """Disclose each actual endpoint, failing closed when its profile cannot load."""
        scope = "\n".join(f"• {config.label} · {config.base_url}" for config in configs)
        for config in configs:
            if config.api_key:
                scope = scope.replace(config.api_key, "[已隐藏密钥]")
        dialog = QMessageBox(self)
        dialog.setWindowTitle("确认多模型发送")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(f"消息、近期最多 20 条上下文与 Orbit 系统提示词将分别发送给：\n\n{scope}\n\n"
                       "不发送附件。云端模型可能分别计费；本机服务是否转发云端取决于其自身配置。继续吗？")
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        return dialog.exec() == QMessageBox.StandardButton.Yes

    def _retry_parallel_if_enabled(self, conversation_id: str) -> bool:
        enabled = getattr(self.settings_store, "is_parallel_mode_enabled", None)
        if not callable(enabled):
            return False
        try:
            if not enabled():
                return False
            configs = [config for config in self.settings_store.load_models() if config.enabled]
            if not 1 <= len(configs) <= 4:
                raise ValueError("请在设置中启用 1–4 个模型。")
            if self._confirm_multi_model_privacy(configs):
                self._start_parallel_request(conversation_id, configs)
        except (SettingsError, ChatHistoryError, OSError, ValueError) as error:
            self.assistant_page.show_error(str(error), conversation_id)
        return True

    def _start_parallel_request(self, conversation_id: str, configs: list[ModelConfig]) -> None:
        """Use the same cancellation and conversation guards as a normal Orbit turn."""
        conversation = self.chat_history.get_conversation(conversation_id)
        if conversation is None or not conversation.messages:
            return
        messages = [{"role": message.role, "content": message.content}
                    for message in conversation.messages[-20:]]
        if sum(len(str(message["content"])) for message in messages) > 60_000:
            raise ValueError("本次对话上下文过长，请新建对话后重试。")

        def request(_progress, cancel_event):
            result = run_models(configs, messages, {"system": ORBIT_SYSTEM_PROMPT}, cancel_event)
            if not result.succeeded:
                raise AIServiceError("；".join(item.error or "无回答" for item in result.failed))
            return _format_multi_model_answer(result)

        worker = TaskWorker(request)
        self._chat_worker = worker
        self._chat_conversation_id = conversation_id
        worker.signals.completed.connect(lambda answer, job=worker, cid=conversation_id:
                                         self._chat_request_completed(job, cid, str(answer)))
        worker.signals.failed.connect(lambda error, job=worker, cid=conversation_id:
                                      self._chat_request_failed(job, cid, error))
        worker.signals.cancelled.connect(lambda _message, job=worker, cid=conversation_id:
                                         self._chat_request_cancelled(job, cid))
        self.assistant_page.set_busy(True, conversation_id)
        self.thread_pool.start(worker)

    def _confirm_chat_privacy(self, settings: AISettings) -> bool:
        """Ask once before Orbit sends user turns and recent context to a provider."""
        try:
            if self.settings_store.has_chat_ai_consent(settings.provider_id):
                return True
            preset = PROVIDER_BY_ID.get(settings.provider_id)
            provider_name = preset.name if preset else settings.provider_id
            dialog = OrbitPrivacyDialog(provider_name, settings.model, True, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False
            self.settings_store.set_chat_ai_consent(settings.provider_id, True)
            return True
        except (SettingsError, OSError) as error:
            QMessageBox.warning(self, "隐私设置无法保存", str(error))
            return False

    def _confirm_attachment_upload(self, settings: AISettings, paths: tuple[Path, ...]) -> bool:
        """Ask for per-request consent before reading selected local attachments."""
        names = "\n".join(f"• {path.name}" for path in paths)
        preset = PROVIDER_BY_ID.get(settings.provider_id)
        provider_name = preset.name if preset else settings.provider_id
        return QMessageBox.question(
            self, "确认发送附件",
            f"Orbit 将读取并发送以下已选文件给 {provider_name} 的 {settings.model}：\n\n"
            f"{names}\n\n图片和文本内容会离开本机。历史记录仅保存附件名称，不保存文件内容或本地路径。继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def _start_chat_request(self, conversation_id: str, settings: AISettings | None = None,
                            attachments: tuple[Path, ...] = ()) -> None:
        """Dispatch one request through the shared Qt worker pool."""
        try:
            conversation = self.chat_history.get_conversation(conversation_id)
            active_settings = settings or self.settings_store.load()
            if conversation is None or not conversation.messages:
                return
            messages = [{"role": message.role, "content": message.content}
                        for message in conversation.messages[-20:]]
        except (ChatHistoryError, SettingsError, OSError, ValueError) as error:
            self.assistant_page.show_error(f"无法准备模型请求：{error}", conversation_id)
            return

        def request(_progress, cancel_event):
            try:
                service = ChatService(active_settings)
                if attachments:
                    return service.respond(messages, cancel_event, attachments)
                return service.respond(messages, cancel_event)
            except (AIServiceError, InterruptedError, ValueError):
                raise
            except Exception as error:
                LOGGER.warning("Orbit request failed error_type=%s", type(error).__name__)
                raise AIServiceError("模型请求失败，请检查网络和配置后重试。") from None

        worker = TaskWorker(request)
        self._chat_worker = worker
        self._chat_conversation_id = conversation_id
        worker.signals.completed.connect(lambda answer, job=worker, cid=conversation_id:
                                         self._chat_request_completed(job, cid, str(answer)))
        worker.signals.failed.connect(lambda error, job=worker, cid=conversation_id:
                                      self._chat_request_failed(job, cid, error))
        worker.signals.cancelled.connect(lambda _message, job=worker, cid=conversation_id:
                                         self._chat_request_cancelled(job, cid))
        self.assistant_page.set_busy(True, conversation_id)
        self.thread_pool.start(worker)

    def _test_multiple_models(self, configs: object) -> None:
        """Probe every enabled model in parallel from the settings page."""
        selected = [config for config in configs
                    if isinstance(config, ModelConfig) and config.enabled] \
            if isinstance(configs, (list, tuple)) else []
        if not selected:
            self.settings_page.set_parallel_test_failed("没有可测试的模型。")
            return
        try:
            selected = [self.settings_store.resolve_model(item) for item in selected]
        except (SettingsError, OSError, ValueError) as error:
            self.settings_page.set_parallel_test_failed(str(error))
            return
        if len(selected) > 4:
            self.settings_page.set_parallel_test_failed("一次最多测试 4 个模型。")
            return
        if self._active_worker is not None:
            self.settings_page.set_parallel_test_failed("另一个后台任务正在运行，请稍后重试。")
            return
        messages = [{"role": "user", "content": "请用一句话确认模型可用。"}]

        def probe(_progress, cancel_event):
            return run_models(selected, messages, cancel_event=cancel_event)

        self._run_task(probe, "正在并行测试已选模型…", self._parallel_test_completed,
                       self._parallel_test_failed, kind="models")

    def _parallel_test_completed(self, result: object) -> None:
        if isinstance(result, MultiModelResult):
            self.settings_page.set_parallel_test_result(result)
        else:
            self.settings_page.set_parallel_test_failed("返回结果无效。")

    def _parallel_test_failed(self, message: str) -> None:
        self.settings_page.set_parallel_test_failed(message)

    def _refresh_local_models(self, base_url: str) -> None:
        """Fetch the installed Ollama models off the UI thread."""
        if self._active_worker is not None:
            self.settings_page.set_local_models_failed("另一个后台任务正在运行，请稍后重试。")
            return
        config = ModelConfig("ollama", "qwen2.5:7b", base_url=str(base_url))

        def probe(_progress, _cancel_event):
            return build_provider(config).list_models()

        self._run_task(probe, "正在获取本机 Ollama 模型…", self._local_models_completed,
                       self._local_models_failed, kind="models")

    def _local_models_completed(self, result: object) -> None:
        self.settings_page.set_local_models(result)

    def _local_models_failed(self, message: str) -> None:
        self.settings_page.set_local_models_failed(message)

    def _detect_ollama_models(self) -> None:
        """List installed Ollama models off the UI thread for the model config combo."""
        if self._active_worker is not None:
            self.settings_page.set_ollama_models([], "另一个后台任务正在运行，请稍后重试。")
            return
        base_url = self.settings_page.base_url_edit.text().strip() or PROVIDER_BY_ID["ollama"].base_url
        config = ModelConfig("ollama", PROVIDER_BY_ID["ollama"].model, base_url=base_url)
        self.settings_page.set_ollama_detect_running(True)

        def probe(_progress, _cancel_event):
            return build_provider(config).list_models()

        self._run_task(probe, "正在检测本机 Ollama 模型…", self._ollama_models_completed,
                       self._ollama_models_failed, kind="models")

    def _ollama_models_completed(self, result: object) -> None:
        models = [str(name) for name in result if str(name).strip()] if isinstance(result, (list, tuple)) else []
        self.settings_page.set_ollama_models(models, None)
        try:
            self.settings_store.save_model_options("ollama", models)
        except (SettingsError, OSError, ValueError) as error:
            self.settings_page.status_label.setText(f"已检测模型，但未能保存列表：{error}")

    def _ollama_models_failed(self, message: str) -> None:
        self.settings_page.set_ollama_models([], message)

    def _retry_chat_message(self) -> None:
        """Retry the saved final user turn using the current provider profile."""
        if self._chat_worker is not None or not self._chat_conversation_id:
            return
        conversation_id = self._chat_conversation_id
        conversation = self.chat_history.get_conversation(conversation_id)
        attachments = self._chat_retry_attachments.get(conversation_id)
        if conversation and conversation.messages[-1].role == "user" \
                and conversation.messages[-1].attachments and attachments is None:
            self.assistant_page.chat_composer.set_text(conversation.messages[-1].content)
            self.assistant_page.show_error("历史记录只保留附件名称；请重新添加附件后发送。", conversation_id)
            self.assistant_page.retry_button.setVisible(False)
            return
        try:
            settings = self.settings_store.load()
        except (SettingsError, OSError, ValueError) as error:
            self.assistant_page.show_error(f"模型配置读取失败：{error}", conversation_id)
            return
        selected_paths = attachments or ()
        if not selected_paths and self._retry_parallel_if_enabled(conversation_id):
            return
        if selected_paths and not self._confirm_attachment_upload(settings, selected_paths):
            return
        self._start_chat_request(conversation_id, settings, selected_paths)

    def _chat_request_completed(self, worker: TaskWorker, conversation_id: str, answer: str) -> None:
        """Persist a response only if its originating conversation still exists."""
        if self._chat_worker is not worker:
            return
        if worker.cancel_event.is_set():
            self._chat_request_cancelled(worker, conversation_id)
            return
        self._chat_worker = None
        if self._close_pending:
            self.close()
            return
        try:
            conversation = self.chat_history.add_message(conversation_id, "assistant", answer)
        except (ChatHistoryError, OSError, ValueError) as error:
            self.assistant_page.show_error(f"回答已收到，但本地保存失败：{error}", conversation_id)
            return
        self._chat_retry_attachments.pop(conversation_id, None)
        self._refresh_conversation_list()
        if self.assistant_page.current_conversation_id() == conversation_id:
            self.assistant_page.set_conversation(conversation)
        self.assistant_page.set_busy(False)
        self.assistant_page.show_reply(conversation_id)

    def _chat_request_failed(self, worker: TaskWorker, conversation_id: str, message: str) -> None:
        """Keep the user turn available for retry and show a safe provider error."""
        if self._chat_worker is not worker:
            return
        self._chat_worker = None
        if self._close_pending:
            self.close()
            return
        safe_message = message.split(": ", 1)[-1]
        self.assistant_page.show_error(safe_message, conversation_id)

    def _chat_request_cancelled(self, worker: TaskWorker, conversation_id: str) -> None:
        """Discard cancelled output and restore the composer state."""
        if self._chat_worker is not worker:
            return
        self._chat_worker = None
        if self._close_pending:
            self.close()
            return
        self.assistant_page.show_stopped(conversation_id)

    def _cancel_chat_task(self) -> None:
        """Request cancellation without allowing a late answer to overwrite UI."""
        if self._chat_worker is not None:
            self._chat_worker.cancel()
            self.assistant_page.set_busy(True, self._chat_conversation_id)

    def _build_shell(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = self._build_sidebar()
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(20, 12, 20, 14)
        self.content_layout.setSpacing(10)
        self.content_layout.addWidget(self._build_page_header())
        self._register_pages()
        self.content_layout.addWidget(self.page_subtitle)
        self.content_layout.addWidget(self.page_stack, 1)
        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setObjectName("WorkspaceSplitter")
        self.workspace_splitter.setHandleWidth(5)
        self.workspace_splitter.addWidget(self.sidebar)
        self.workspace_splitter.addWidget(self.content)
        self.workspace_splitter.setCollapsible(1, False)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.splitterMoved.connect(self._sidebar_moved)
        layout.addWidget(self.workspace_splitter)
        self.setCentralWidget(central)
        QTimer.singleShot(0, self._restore_sidebar)

    def _build_page_header(self) -> QWidget:
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        self.sidebar_toggle = QPushButton()
        self.sidebar_toggle.setIcon(svg_icon("sidebar"))
        self.sidebar_toggle.setFixedSize(34, 34)
        self.sidebar_toggle.setAccessibleName("展开或收起导航栏")
        self.sidebar_toggle.setToolTip("展开或收起导航栏 · Ctrl+B")
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        shortcut.activated.connect(self._toggle_sidebar)
        row.addWidget(self.sidebar_toggle)
        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        row.addWidget(self.page_title, 1)
        row.addStretch(1)
        settings_shortcut = QShortcut(QKeySequence("Ctrl+,"), self)
        settings_shortcut.activated.connect(lambda: self._show_page("appsettings"))
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        self.page_subtitle.setWordWrap(True)
        return header

    def _register_pages(self) -> None:
        self.page_stack = QStackedWidget()
        self.organize_page = OrganizePage()
        self.assistant_page = AssistantPage()
        self.assistant_page.set_user_avatar(self.account_button.icon())
        self.assistant_page.set_user_name(self._user_name)
        self.assistant_page.set_reduced_motion(self._reduced_motion)
        self.assistant_page.motion_preference_changed.connect(self._save_motion_preference)
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage(self.settings_store)
        self.local_settings_page = LocalSettingsPage(self.settings_store)
        self.conversion_page = ConversionPage()
        self.pages: dict[str, QWidget] = {
            "organize": self.organize_page,
            "assistant": self.assistant_page,
            "history": self.history_page,
            "settings": self.settings_page,
            "conversion": self.conversion_page,
            "appsettings": self.local_settings_page,
        }
        for page in self.pages.values():
            self.page_stack.addWidget(page)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(230)
        sidebar.setMaximumWidth(380)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 14, 16)
        layout.setSpacing(0)
        layout.addWidget(self._build_brand())
        layout.addSpacing(14)
        layout.addWidget(self._build_navigation())
        layout.addSpacing(8)
        layout.addWidget(self._build_recent_area(), 1)
        self.sidebar_filler = QWidget()
        self.sidebar_filler.hide()
        layout.addWidget(self.sidebar_filler, 1)
        mode_label = QLabel("仅处理你选择的目录")
        mode_label.setObjectName("SidebarFooter")
        layout.addSpacing(10)
        layout.addWidget(mode_label)
        layout.addSpacing(8)
        layout.addWidget(self._build_local_account())
        return sidebar

    def _build_local_account(self) -> QPushButton:
        self.account_button = LocalAccountButton(self._user_name)
        try:
            self.account_button.setIcon(avatar_icon(self.workspace_store.avatar_path()))
        except WorkspaceError:
            self.account_button.setIcon(avatar_icon(None))
        self.account_button.setIconSize(QSize(30, 30))
        menu = QMenu(self.account_button)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.NoDropShadowWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.addAction("更换本机头像…", self._choose_avatar)
        self.rename_user_action = menu.addAction("修改用户名…", self._rename_user)
        menu.addSeparator()
        for title, mode in (("锁定 / 登出  Ctrl+L", "unlock"), ("修改本机密码", "change")):
            action = menu.addAction(title)
            action.setEnabled(self.lock_store is not None)
            action.triggered.connect(lambda checked=False, selected=mode: self._request_local_auth(selected))
        menu.addSeparator()
        self.local_settings_action = menu.addAction("设置", lambda: self._show_page("appsettings"))
        self.local_settings_action.setIcon(svg_icon("settings", COLORS["muted"]))
        self.account_button.setMenu(menu)
        shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        shortcut.activated.connect(lambda: self._request_local_auth("unlock"))
        return self.account_button

    def _rename_user(self) -> None:
        dialog = UserNameDialog(self._user_name, self.workspace_store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._user_name = dialog.user_name
            self.account_button.set_user_name(dialog.user_name)
            self.assistant_page.set_user_name(dialog.user_name)
        dialog.deleteLater()

    def _restore_sidebar(self) -> None:
        self.sidebar.setVisible(not self._sidebar_collapsed)
        self.workspace_splitter.setSizes([self._sidebar_width, max(400, self.width() - self._sidebar_width)])

    def _toggle_sidebar(self) -> None:
        collapsed = self.sidebar.isHidden() or self.workspace_splitter.sizes()[0] == 0
        if not collapsed:
            self._sidebar_width = max(230, self.sidebar.width())
        self._sidebar_collapsed = not collapsed
        self._restore_sidebar()
        self._layout_timer.start()

    def _sidebar_moved(self, _position: int, _index: int) -> None:
        width = self.workspace_splitter.sizes()[0]
        self._sidebar_collapsed = width == 0
        if width:
            self._sidebar_width = min(380, max(230, width))
        self._layout_timer.start()

    def _save_workspace_layout(self) -> None:
        try:
            self.workspace_store.save_layout(self._sidebar_width, self._sidebar_collapsed)
            self.workspace_store.save_organizer_height(self._organizer_height)
        except (WorkspaceError, OSError) as error:
            self.organize_page.set_status(str(error))

    def _organizer_resized(self, height: int) -> None:
        self._organizer_height = height
        self._layout_timer.start()

    def _save_motion_preference(self, reduced: bool) -> None:
        try:
            self.workspace_store.save_reduced_motion(reduced)
        except (WorkspaceError, OSError) as error:
            self.assistant_page.set_reduced_motion(self._reduced_motion)
            QMessageBox.warning(self, "无法保存动态效果设置", str(error))
            return
        self._reduced_motion = reduced

    def _restore_organizer_height(self) -> None:
        splitter = self.organize_page.layout_splitter
        splitter.setSizes([self._organizer_height, max(180, splitter.height() - self._organizer_height - 8)])

    def _choose_avatar(self) -> None:
        if self._avatar_worker is not None:
            return
        filename, _filter = QFileDialog.getOpenFileName(self, "选择本机头像", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if filename:
            self._save_avatar(Path(filename))

    def _save_avatar(self, source: Path) -> None:
        if self._avatar_worker is not None:
            return
        self._avatar_worker = TaskWorker(lambda _progress, _cancel: self.workspace_store.save_avatar(source))
        self._avatar_worker.signals.completed.connect(self._avatar_saved)
        self._avatar_worker.signals.failed.connect(self._avatar_failed)
        self.thread_pool.start(self._avatar_worker)

    def _avatar_saved(self, path: object) -> None:
        self._avatar_worker = None
        icon = avatar_icon(path if isinstance(path, Path) else None)
        self.account_button.setIcon(icon)
        self.assistant_page.set_user_avatar(icon)
        self.organize_page.set_status("头像已保存在本机，未上传到任何模型服务。")
        if self._close_pending:
            self.close()

    def _avatar_failed(self, message: str) -> None:
        self._avatar_worker = None
        if self._close_pending:
            self.close()
        else:
            QMessageBox.warning(self, "头像保存失败", message)

    def _request_local_auth(self, mode: str) -> None:
        if self.lock_store is None:
            return
        if (self._active_worker is not None or self._chat_worker is not None or
                self._avatar_worker is not None or self.conversion_page.is_busy):
            QMessageBox.information(self, "任务仍在运行", "请先停止或等待当前任务，再锁定或修改密码。")
            return
        self.local_auth_requested.emit(mode)

    def _conversion_finished(self) -> None:
        if self._close_pending:
            self.close()

    def _build_brand(self) -> QWidget:
        brand_widget = QWidget()
        brand = QHBoxLayout(brand_widget)
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(application_icon().pixmap(QSize(42, 42), self.devicePixelRatioF()))
        mark.setAccessibleName("FileMind 应用图标")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(42, 42)
        mark.setObjectName("BrandMark")
        brand.addWidget(mark)
        brand_text = QVBoxLayout()
        name = QLabel("FileMind")
        name.setObjectName("BrandName")
        caption = QLabel("AI 文件管理更简单")
        caption.setObjectName("BrandCaption")
        brand_text.addWidget(name)
        brand_text.addWidget(caption)
        brand.addLayout(brand_text)
        brand.addStretch(1)
        return brand_widget

    def _build_navigation(self) -> QScrollArea:
        scroll = QScrollArea()
        self.navigation_scroll = scroll
        scroll.setObjectName("SidebarNavigation")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumHeight(80)
        scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        navigation = QWidget()
        navigation_layout = QVBoxLayout(navigation)
        navigation_layout.setContentsMargins(0, 0, 3, 0)
        navigation_layout.setSpacing(4)
        self.nav_buttons: dict[str, QPushButton] = {}
        for key, title, icon_name, _page_title, _page_subtitle in NAVIGATION_ITEMS:
            button = QPushButton(title)
            button.setObjectName("NavButton")
            button.setIcon(svg_icon(icon_name))
            button.setIconSize(QSize(20, 20))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, page=key: self._show_page(page))
            self.nav_buttons[key] = button
            navigation_layout.addWidget(button)
        navigation_layout.addStretch(1)
        scroll.setWidget(navigation)
        scroll.setMaximumHeight(min(260, navigation.sizeHint().height()))
        return scroll

    def _build_recent_area(self) -> QWidget:
        self.recent_area = QFrame()
        self.recent_area.setMinimumHeight(280)
        self.recent_area.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        recent_layout = QVBoxLayout(self.recent_area)
        recent_layout.setContentsMargins(0, 8, 0, 0)
        recent_layout.setSpacing(7)
        recent_layout.addLayout(self._build_recent_header())
        self.conversation_search = QLineEdit()
        self.conversation_search.setObjectName("OrbitConversationSearch")
        self.conversation_search.setPlaceholderText("搜索对话标题…")
        self.conversation_search.setAccessibleName("搜索最近对话")
        self.conversation_search.setClearButtonEnabled(True)
        self.conversation_search.textChanged.connect(self._filter_conversations)
        self.conversation_search.hide()
        recent_layout.addWidget(self.conversation_search)
        self.conversation_list = ConversationList()
        self.conversation_list.setObjectName("OrbitRecentList")
        self.conversation_list.setFrameShape(QFrame.Shape.NoFrame)
        self.conversation_list.setSpacing(1)
        self.conversation_list.setMinimumHeight(216)
        self.conversation_list.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.conversation_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.conversation_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.conversation_list.itemActivated.connect(self._select_chat_item)
        recent_layout.addWidget(self.conversation_list, 1)
        self.conversation_empty = QLabel("还没有最近对话\n新建一段对话开始使用 Orbit")
        self.conversation_empty.setObjectName("OrbitRecentEmpty")
        self.conversation_empty.setWordWrap(True)
        self.conversation_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.conversation_empty.setMinimumHeight(68)
        self.conversation_empty.setMaximumHeight(76)
        recent_layout.addWidget(self.conversation_empty)
        self.recent_empty_filler = QWidget()
        recent_layout.addWidget(self.recent_empty_filler, 1)
        return self.recent_area

    def _build_recent_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("最近对话")
        title.setObjectName("OrbitRecentHeading")
        header.addWidget(title)
        self.conversation_count = QLabel("0")
        self.conversation_count.setObjectName("OrbitConversationCount")
        header.addWidget(self.conversation_count)
        header.addStretch(1)
        self.conversation_search_button = QPushButton()
        self.conversation_search_button.setObjectName("OrbitRecentSearchButton")
        self.conversation_search_button.setCheckable(True)
        self.conversation_search_button.setIcon(svg_icon("search", size=16))
        self.conversation_search_button.setAccessibleName("搜索最近对话")
        self.conversation_search_button.setToolTip("搜索最近对话标题")
        self.conversation_search_button.clicked.connect(self._toggle_conversation_search)
        self.new_chat_button = QPushButton()
        self.new_chat_button.setObjectName("OrbitRecentNewButton")
        self.new_chat_button.setIcon(svg_icon("plus", "#7751D8", 17))
        self.new_chat_button.setToolTip("新建 Orbit 对话")
        self.new_chat_button.setAccessibleName("新建 Orbit 对话")
        for button in (self.conversation_search_button, self.new_chat_button):
            button.setFixedSize(30, 30)
            header.addWidget(button)
        return header

    def _show_page(self, page_name: str) -> None:
        page = self.pages[page_name]
        self.page_stack.setCurrentWidget(page)
        title, subtitle = PAGE_INFO[page_name]
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        is_assistant = page_name == "assistant"
        self.page_title.setVisible(not is_assistant)
        self.page_subtitle.setVisible(not is_assistant and page_name != "organize")
        self.recent_area.setVisible(is_assistant)
        self.sidebar_filler.setVisible(not is_assistant)
        if is_assistant:
            self.assistant_page.set_busy(self._chat_worker is not None, self._chat_conversation_id)
        for key, button in self.nav_buttons.items():
            button.setProperty("active", key == page_name)
            button.setProperty("orbit", key == "assistant")
            button.style().unpolish(button)
            button.style().polish(button)

    def _scan_folder(self, folder: str, open_preview: bool = True) -> None:
        if self._active_worker is not None:
            return
        root = Path(folder).expanduser()
        ai_mode = self.organize_page.mode_combo.currentData() == "ai"
        content_analysis = ai_mode and self.organize_page.content_checkbox.isChecked()
        ai_settings = self._prepare_ai_settings(confirm_metadata=not content_analysis) if ai_mode else None
        if ai_mode and ai_settings is None:
            self.organize_page.set_status("AI 请求未发送：请完成服务配置或同意发送元数据。")
            return
        if content_analysis and not self._confirm_content_privacy(ai_settings):
            self.organize_page.set_status("已取消内容识别：没有读取或发送文件正文。")
            return
        user_rule = self.organize_page.rule_input.toPlainText().strip()
        rename_enabled = self.organize_page.rename_checkbox.isChecked()
        if self.organize_page.path_edit.text().strip() != str(root):
            self.organize_page.set_directory(str(root))
        self._folder_generation += 1
        generation = self._folder_generation
        signature = self._organization_signature()
        preset = str(self.organize_page.preset_combo.currentData())
        task = lambda progress, cancel: self._scan_and_plan(
            root, ai_mode, ai_settings, user_rule, rename_enabled, progress, cancel, preset,
            lambda message: self.organization_phase.emit(generation, message), content_analysis
        )
        self.organize_page.clear_plan()
        self._run_task(task, "正在扫描所选文件夹…",
                       lambda payload, version=generation: self._scan_completed(payload, version, signature, open_preview),
                       kind="scan")

    def _organization_signature(self) -> tuple[object, ...]:
        page = self.organize_page
        return (page.mode_combo.currentData(), page.preset_combo.currentData(),
                page.rule_input.toPlainText(), page.rename_checkbox.isChecked(), page.content_checkbox.isChecked())

    def _organization_phase_changed(self, generation: int, message: str) -> None:
        if generation == self._folder_generation and self._active_worker is not None:
            self.organize_page.set_status(message)

    def _scan_imported_files(self, folder: str) -> None:
        """Import metadata for browsing without creating or sending an AI request."""
        if self._active_worker is not None:
            return
        self._close_plan_preview()
        self._folder_generation += 1
        generation = self._folder_generation
        self.organize_page.clear_plan()
        root = Path(folder).expanduser().resolve()

        def import_files(progress: ProgressCallback, cancel: Event) -> object:
            files = scan_files(root, progress, cancel)
            history = OperationHistory(root)
            return files, history, history.list_records()

        self._run_task(import_files, "正在读取文件列表…",
                       lambda payload: self._import_completed(payload, generation), kind="scan")

    def _import_completed(self, payload: object, generation: int) -> None:
        if generation != self._folder_generation:
            return
        files, history, records = payload
        self._history = history
        self.organize_page.set_files(files)
        self.history_page.set_records(records, self.organize_page.path_edit.text())

    def _select_directory(self, folder: str, analyze: bool = True) -> None:
        """Confirm discarding a plan before changing the user's selected directory."""
        if self._active_worker is not None:
            QMessageBox.information(self, "任务仍在运行", "请先取消或等待当前任务结束，再切换目录。")
            return
        current = self.organize_page.path_edit.text().strip()
        if current != folder and self.organize_page.plan and self.organize_page.plan.operations:
            answer = QMessageBox.question(
                self, "放弃当前整理计划", "切换目录会清除当前预览计划。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._close_plan_preview()
        self.organize_page.set_directory(folder)
        if analyze:
            self._scan_folder(folder)
        else:
            self._scan_imported_files(folder)

    def _clear_directory(self) -> None:
        """Clear directory-bound UI state without touching user files."""
        if self._active_worker is not None and self._active_task_kind != "scan":
            QMessageBox.information(self, "任务仍在运行", "当前文件操作完成或取消后，才能清除目录。")
            return
        if self.organize_page.plan and self.organize_page.plan.operations:
            answer = QMessageBox.question(
                self, "清除当前目录", "清除会放弃当前整理预览，不会删除或移动磁盘文件。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._close_plan_preview()
        self._folder_generation += 1
        if self._active_worker is not None:
            self._active_worker.cancel()
            self.organize_page.set_busy(True, "正在取消旧扫描…")
        self.organize_page.set_directory("")
        self._history = None
        self.history_page.set_records([], "先在文件整理页选择一个文件夹。")

    def _open_plan_preview(self) -> None:
        """Open the current plan in a dedicated, non-blocking review dialog."""
        plan = self.organize_page.plan
        if plan is None or not plan.operations:
            self.organize_page.set_status("请先扫描目录并生成整理计划。")
            return
        dialog = PlanPreviewDialog(plan, self.organize_page.table_model, self)
        dialog.execute_requested.connect(self._confirm_execution)
        dialog.rescan_requested.connect(self.organize_page._request_scan)
        self._preview_dialog = dialog
        dialog.finished.connect(lambda _result, current=dialog: self._forget_preview_dialog(current))
        dialog.open()

    def _forget_preview_dialog(self, dialog: PlanPreviewDialog) -> None:
        if self._preview_dialog is dialog:
            self._preview_dialog = None

    def _close_plan_preview(self) -> None:
        if self._preview_dialog is not None:
            dialog = self._preview_dialog
            self._preview_dialog = None
            dialog.close()

    def _prepare_ai_settings(self, confirm_metadata: bool = True) -> AISettings | None:
        if self.settings_page.has_unsaved_changes:
            QMessageBox.information(self, "请先保存 AI 配置", "当前 AI 服务配置尚未保存，请先保存再生成整理预览。")
            self._show_page("settings")
            return None
        try:
            ai_settings = self.settings_store.load()
        except (SettingsError, OSError) as error:
            QMessageBox.critical(self, "无法读取 AI 配置", str(error))
            return None
        if not _is_usable_ai_settings(ai_settings):
            QMessageBox.warning(self, "AI 服务未配置", "请先在设置页配置服务商、Base URL、模型名称和 API Key。")
            self._show_page("settings")
            return None
        return ai_settings if not confirm_metadata or self._confirm_ai_privacy() else None

    def _confirm_ai_privacy(self) -> bool:
        try:
            if self.settings_store.has_online_ai_consent():
                return True
            consent = QMessageBox.question(
                self,
                "确认发送文件元数据",
                "AI 整理会将文件名、扩展名、大小、修改时间及你的整理规则发送给所选服务。在线服务由服务商处理这些数据。\n"
                "不会上传文件正文、整个文件夹或本地绝对路径。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if consent != QMessageBox.StandardButton.Yes:
                return False
            self.settings_store.set_online_ai_consent(True)
            return True
        except (SettingsError, OSError) as error:
            QMessageBox.critical(self, "无法读取或保存隐私设置", str(error))
            return False

    def _confirm_content_privacy(self, settings: AISettings) -> bool:
        """Require new authorization for every content-reading organization job."""
        answer = QMessageBox.question(
            self, "确认本次内容识别与命名",
            f"接收服务：{settings.provider_id} · {settings.model}\n\n"
            "仅分析当前所选目录第一层文件：文档开头最多 1800 字（PDF 最多前三页）；图片压缩到最长 1024 像素，"
            "图中可见个人信息仍可能被发送。另发送文件名、大小、修改时间和你的规则。\n"
            "最多分析 128 个文件、单文件 8 MB、图片合计 12 MB；不读取子目录。疑似凭据文件会排除；不支持或失败的文件标记并跳过。\n"
            "请先移除不想发送的文件。是否授权本次发送？建议仍须预览确认后才会执行。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    @staticmethod
    def _scan_and_plan(
        root: Path,
        ai_mode: bool,
        ai_settings: AISettings | None,
        user_rule: str,
        rename_enabled: bool,
        progress: ProgressCallback,
        cancel: Event,
        preset_key: str = "extension",
        on_phase: Callable[[str], None] | None = None,
        content_analysis: bool = False,
    ) -> tuple[OperationPlan, list[OperationRecord], OperationHistory, dict[str, str]]:
        if on_phase:
            on_phase("正在扫描所选目录…")
        files = scan_files(root, progress, cancel)
        suggestions: dict[str, FileSuggestion] = {}
        failed_file_ids: dict[str, str] = {}
        if ai_mode and files and ai_settings:
            metadata = [file_metadata(file_info) for file_info in files]
            if content_analysis:
                from filemind.ai.content import prepare_content_metadata
                if on_phase:
                    on_phase("正在提取已授权的内容片段与图片缩略图…")
                metadata, content_failures = prepare_content_metadata(root, files, ai_settings, cancel)
                for failure in content_failures:
                    failed_file_ids.update({file_id: failure.message for file_id in failure.file_ids})
            if on_phase:
                on_phase("正在向所选服务商请求 AI 建议…" if metadata else "没有可安全分析的内容，未发送 AI 请求。")
            client = OpenAICompatibleClient(ai_settings)
            result = client.organize_files(
                metadata, user_rule, rename_enabled, progress, cancel
            )
            suggestions = result.suggestions
            for failure in result.failures:
                failed_file_ids.update({file_id: failure.message for file_id in failure.file_ids})
        if cancel.is_set():
            raise InterruptedError("生成整理建议已取消")
        if on_phase:
            on_phase("正在执行本地路径与冲突校验…")
        classifier = lambda item: classify_with_preset(item, preset_key)
        plan = build_plan(root, files, classifier, suggestions, rename_enabled if ai_mode else False,
                          failed_file_ids)
        history = OperationHistory(plan.root)
        return plan, history.list_records(), history, failed_file_ids

    def _scan_completed(self, payload: object, generation: int | None = None,
                        signature: tuple[object, ...] | None = None, open_preview: bool = True) -> None:
        if generation is not None and generation != self._folder_generation:
            return
        plan, records, history, failed_file_ids = payload
        self._history = history
        if signature is not None and signature != self._organization_signature():
            self.organize_page.clear_plan()
            self.organize_page.set_status("规则在请求期间发生变更，旧建议未应用。请重新发送。")
            return
        self.organize_page.set_plan(plan)
        ai_count = sum(item.classification.source == "AI" for item in plan.operations)
        result_text = f"已收到 {ai_count} 项 AI 建议并完成本地校验" if ai_count else "已生成本地规则预览，未使用 AI 理解规则"
        self.organize_page.set_status(result_text if plan.operations else "目录为空，未发送 AI 请求。")
        self.history_page.set_records(records, str(plan.root))
        if failed_file_ids:
            QMessageBox.warning(
                self,
                "部分 AI 建议未生成",
                f"{len(failed_file_ids)} 个文件所在批次失败。预览中标为本地规则结果，这些行在执行时会跳过。\n"
                "请检查行内错误、修改规则或使用本地规则重新扫描。",
            )
            if self.organize_page.mode_combo.currentData() == "ai" and len(failed_file_ids) >= len(plan.operations):
                self.organize_page.set_status("AI 未生成可用建议；当前所有行都会跳过，请修改规则后重试。")
                return
        if plan.operations and open_preview:
            self._open_plan_preview()

    def _test_ai_connection(self, settings: object) -> None:
        if not isinstance(settings, AISettings):
            return
        if self._active_worker is not None:
            self.settings_page.set_test_result(False, "另一个后台任务正在运行，请稍后重试。")
            return

        def test_connection(progress_emit, cancel_event):
            if cancel_event.is_set():
                raise InterruptedError("连接测试已取消")
            client = OpenAICompatibleClient(settings)
            return client.test_connection()

        self._run_task(test_connection, "正在测试 AI 服务连接…", self._connection_test_completed,
                       self._connection_test_failed)

    def _connection_test_completed(self, result: object) -> None:
        self.settings_page.set_test_result(True, f"连接成功 · 服务端模型：{result}")

    def _connection_test_failed(self, message: str) -> None:
        self.settings_page.set_test_result(False, message)

    def _confirm_execution(self, plan: object) -> None:
        if not isinstance(plan, OperationPlan) or self._history is None:
            return
        executable = [operation for operation in plan.operations
                      if not operation.excluded and not operation.warning]
        skipped = len(plan.operations) - len(executable)
        if not executable:
            QMessageBox.information(
                self, "没有可执行的文件",
                "预览中的文件都会被跳过。请解决冲突、修改分类或文件名，或重新勾选要执行的安全行。")
            return
        self.organize_page.set_plan(plan)
        detail = f"即将移动 {len(executable)} 个文件到预览中的分类文件夹。"
        if skipped:
            detail += f"\n其中 {skipped} 项会跳过（目标冲突、符号链接或你排除的行），不会移动。"
        answer = QMessageBox.question(
            self,
            "确认整理文件",
            f"{detail}\n\n不会删除或覆盖文件，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        history = self._history

        def execute(progress_emit, cancel_event):
            return execute_plan(plan, history, True, on_progress=progress_emit, cancel_event=cancel_event)

        self._run_task(execute, "正在安全整理文件…", self._execution_completed)

    def _execution_completed(self, result: object) -> None:
        if not isinstance(result, ExecutionResult):
            return
        counts = f"成功 {result.succeeded} 项，跳过 {result.skipped} 项，失败 {result.failed} 项。"
        message = f"整理完成：{counts}"
        if result.cancelled:
            message = f"任务已取消：{counts}"
        if result.failures:
            details = "\n".join(result.failures[:8])
            QMessageBox.warning(self, "部分文件未完成", f"{message}\n\n{details}")
        self.organize_page.set_status(message, "\n".join(result.skip_reasons[:8]))
        self.organize_page.last_operation_label.setText(
            f"上次：{result.succeeded} 成功 / {result.skipped} 跳过 / {result.failed} 失败")
        self.organize_page.last_operation_label.setToolTip(
            message if not result.skip_reasons else message + "\n" + "\n".join(result.skip_reasons[:8]))
        self.organize_page.last_operation_label.show()
        if self.organize_page.path_edit.text().strip():
            self.organize_page.clear_plan()
            self._scan_imported_files(self.organize_page.path_edit.text().strip())

    def _refresh_history(self) -> None:
        folder = self.organize_page.path_edit.text().strip()
        if not folder:
            self.history_page.set_records([], "先在文件整理页选择一个文件夹。")
            return

        def load_history(progress_emit, cancel_event):
            if cancel_event.is_set():
                raise InterruptedError("历史记录读取已取消")
            history = OperationHistory(Path(folder))
            return history.list_records(), history

        self._run_task(load_history, "正在读取操作历史…", self._history_completed)

    def _history_completed(self, payload: object) -> None:
        records, history = payload
        self._history = history
        self.history_page.set_records(records, str(history.root))

    def _confirm_undo(self, operation_id: str) -> None:
        if self._history is None:
            return
        answer = QMessageBox.question(
            self,
            "确认撤销",
            "撤销前会重新检查文件是否被修改及原位置是否空闲。继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        history = self._history

        def undo(progress_emit, cancel_event):
            if cancel_event.is_set():
                raise InterruptedError("撤销已取消")
            return undo_record(history, operation_id, cancel_event=cancel_event)

        self._run_task(undo, "正在检查并撤销操作…", self._undo_completed)

    def _undo_completed(self, result: object) -> None:
        if isinstance(result, ExecutionResult):
            message = f"撤销完成：成功 {result.succeeded} 项，失败 {result.failed} 项。"
            self.organize_page.set_status(message)
            if result.failures:
                QMessageBox.warning(self, "部分文件未撤销", "\n".join(result.failures[:8]))
            if self.organize_page.path_edit.text().strip():
                self.organize_page.clear_plan()
                self._scan_imported_files(self.organize_page.path_edit.text().strip())

    def _run_task(self, task, message: str, completed, failed=None, kind: str = "task") -> None:
        if self._active_worker is not None:
            return
        worker = TaskWorker(task)
        self._active_worker = worker
        self._active_task_kind = kind
        self._workers.append(worker)
        worker.signals.progress.connect(self._task_progress)
        worker.signals.completed.connect(lambda result, callback=completed, job=worker: self._task_done(job, callback, result))
        worker.signals.failed.connect(lambda error, job=worker, error_callback=failed:
                                      self._task_failed(job, error, error_callback))
        worker.signals.cancelled.connect(lambda message, job=worker: self._task_cancelled(job, message))
        self.organize_page.set_busy(True, message)
        self.organize_page.cancel_button.setEnabled(True)
        self.history_page.cancel_button.setEnabled(True)
        self.history_page.refresh_button.setEnabled(False)
        self.history_page.undo_button.setEnabled(False)
        self.thread_pool.start(worker)

    def _task_progress(self, completed: int, total: int) -> None:
        self.organize_page.set_progress(completed, total)
        if total:
            self.organize_page.set_status(f"正在处理：{completed}/{total}")

    def _task_done(self, worker: TaskWorker, callback, result: object) -> None:
        if self._active_worker is not worker:
            return
        self._finish_task(worker)
        if self._close_pending:
            self.close()
            return
        callback(result)

    def _task_failed(self, worker: TaskWorker, error: str, callback=None) -> None:
        if self._active_worker is not worker:
            return
        stale_scan = self._active_task_kind == "scan" and not self.organize_page.path_edit.text().strip()
        self._finish_task(worker)
        if self._close_pending:
            self.close()
            return
        if stale_scan:
            return
        self.organize_page.set_error(error)
        if callback:
            callback(error)
        else:
            QMessageBox.critical(self, "任务失败", error)

    def _task_cancelled(self, worker: TaskWorker, message: str) -> None:
        if self._active_worker is not worker:
            return
        cleared_scan = self._active_task_kind == "scan" and not self.organize_page.path_edit.text().strip()
        model_task = self._active_task_kind == "models"
        self._finish_task(worker)
        if model_task:
            self.settings_page.set_parallel_test_failed("已取消")
            self.settings_page.set_ollama_detect_running(False)
            self.settings_page.set_local_models_failed("检测已取消")
        if self._close_pending:
            self.close()
            return
        if cleared_scan:
            self.organize_page.set_status("目录已清除；旧扫描已取消。")
            return
        self.organize_page.set_status(message or "任务已取消。")

    def _finish_task(self, worker: TaskWorker) -> None:
        self._active_worker = None
        self._active_task_kind = None
        if worker in self._workers:
            self._workers.remove(worker)
        self.organize_page.set_busy(False)
        self.history_page.cancel_button.setEnabled(False)
        self.history_page.refresh_button.setEnabled(True)
        self.history_page._update_undo_state()

    def _cancel_task(self) -> None:
        if self._active_worker is not None:
            self._active_worker.cancel()
            self.organize_page.set_status("已请求取消，正在等待安全停止点…")
            self.settings_page.status_label.setText("已请求取消；网络请求会在超时或安全停止点结束…")

    def closeEvent(self, event: QCloseEvent) -> None:
        if (self._active_worker is not None or self._chat_worker is not None or
                self._avatar_worker is not None or self.conversion_page.has_pending_work):
            self._close_pending = True
            self._cancel_task()
            self._cancel_chat_task()
            self.conversion_page.cancel()
            event.ignore()
            self.organize_page.set_status("任务停止后将关闭窗口…")
            return
        self._layout_timer.stop()
        self._save_workspace_layout()
        event.accept()


def main() -> int:
    """Create the QApplication and show the PySide6 main window."""
    from filemind.ui.startup import run_application

    return run_application()


def _is_usable_ai_settings(settings: AISettings | None) -> bool:
    """Check the minimum UI prerequisites before enabling online AI mode."""
    return bool(settings and settings.base_url.strip() and settings.model.strip()
                and (settings.api_key.strip() or is_local_connection(settings.provider_id, settings.base_url)))


def _format_multi_model_answer(result: MultiModelResult) -> str:
    """Group model answers as Markdown without interpreting labels as markup."""
    import re
    parts: list[str] = []
    budget = max(1, (MAX_MESSAGE_LENGTH - 1200) // max(1, len(result.results)))
    for item in result.results:
        label = re.sub(r"[\r\n#<>]", " ", item.label)[:160]
        body = item.content if item.ok else f"调用失败：{item.error}"
        if len(body) > budget:
            body = body[:budget] + "\n\n[回答超出本地会话长度限制，后文已截断。]"
        parts.append(f"### {label}\n\n耗时 {item.latency_ms} ms\n\n{body}")
    return "\n\n---\n\n".join(parts)
