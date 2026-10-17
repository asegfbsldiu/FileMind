"""Offscreen integration checks for the PySide6 organizer workflow."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication, QFrame, QMessageBox

from filemind.ui.main_window import MainWindow
from filemind.ai.schemas import AIOrganizationResult, file_metadata
from filemind.models import FileSuggestion
from filemind.storage.settings import AISettings
from filemind.storage.settings import SettingsStore
from filemind.storage.chat_history import ChatHistoryStore
from filemind.ui.main_window import NAVIGATION_ITEMS
from filemind.ui.styles.icons import provider_icon
from filemind.ui.widgets.conversation_row import ConversationRow
from filemind.ui.widgets.chat_input import ChatInput


class MainWindowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.settings_store = SettingsStore(root / "settings.json", root, _MemorySecretStore())
        self.chat_history = ChatHistoryStore(root / "orbit.json")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _new_window(self) -> MainWindow:
        return MainWindow(self.settings_store, self.chat_history)

    def test_selected_directory_scans_off_thread_and_populates_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "课程笔记.txt").write_text("虚拟内容", encoding="utf-8")
            (root / "旅行照片.png").write_bytes(b"test image")
            window = self._new_window()
            window.organize_page.path_edit.setText(str(root))
            window._scan_folder(str(root))

            self._wait_for_task(window)

            self.assertEqual(window.organize_page.table_model.rowCount(), 2)
            self.assertEqual(window.organize_page.file_count.value_label.text(), "2")
            self.assertEqual(window.organize_page.table_model.operations[0].source.parent, root)
            self.assertEqual(window.history_page.table_model.rowCount(), 0)
            window.close()

    def test_local_rules_work_without_ai_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "课程笔记.txt").write_text("virtual content", encoding="utf-8")
            window = self._new_window()
            window.organize_page.path_edit.setText(str(root))
            with patch("filemind.ui.main_window.OpenAICompatibleClient", side_effect=AssertionError):
                window._scan_folder(str(root))
                self._wait_for_task(window)

            operation = window.organize_page.table_model.operations[0]
            self.assertEqual(operation.classification.source, "规则")
            self.assertTrue(window.organize_page.execute_button.isEnabled())
            window.close()

    def test_ai_suggestion_is_shown_in_the_real_preview_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "课程资料.txt").write_text("private body", encoding="utf-8")
            window = MainWindow(_FakeSettingsStore(), self.chat_history)
            window.organize_page.path_edit.setText(str(root))
            window.organize_page.mode_combo.setCurrentIndex(1)
            window.organize_page.rule_input.setPlainText("按数据结构课程和章节整理")
            received_rules: list[str] = []

            class FakeAIClient:
                def __init__(self, settings):
                    self.settings = settings

                def organize_files(self, files, rule, rename, progress, cancel):
                    received_rules.append(rule)
                    suggestion = FileSuggestion(files[0].file_name, "学习资料", "链表笔记.txt", "课程规则匹配",
                                                files[0].file_id, "数据结构/第1章")
                    return AIOrganizationResult({suggestion.file_id: suggestion}, ())

            with patch("filemind.ui.main_window.OpenAICompatibleClient", FakeAIClient):
                window._scan_folder(str(root))
                self._wait_for_task(window)

            operation = window.organize_page.table_model.operations[0]
            self.assertEqual(operation.classification.source, "AI")
            self.assertEqual(operation.target, root / "学习资料" / "数据结构" / "第1章" / "链表笔记.txt")
            self.assertTrue(window.organize_page.execute_button.isEnabled())
            self.assertEqual(received_rules, ["按数据结构课程和章节整理"])
            window.close()

    def test_connection_request_runs_without_blocking_qt_event_loop(self) -> None:
        window = self._new_window()
        settings = AISettings("custom", "https://example.com/v1", "test-model", 10, "mock-key")
        timer_events: list[bool] = []

        class SlowFakeClient:
            def __init__(self, connection_settings):
                self.settings = connection_settings

            def test_connection(self):
                time.sleep(0.15)
                return "mock-model"

        from PySide6.QtCore import QTimer
        QTimer.singleShot(20, lambda: timer_events.append(True))
        with patch("filemind.ui.main_window.OpenAICompatibleClient", SlowFakeClient):
            window._test_ai_connection(settings)
            self._wait_for_task(window)

        self.assertTrue(timer_events)
        self.assertIn("连接成功", window.settings_page.status_label.text())
        window.close()

    def test_organize_rule_editor_stays_editable_and_preserves_text(self) -> None:
        window = self._new_window()
        editor = window.organize_page.rule_input
        editor.setPlainText("课程 PDF 按章节整理")
        self.assertTrue(editor.isEnabled())
        self.assertFalse(editor.isReadOnly())

        window.organize_page.mode_combo.setCurrentIndex(1)
        self.assertTrue(editor.isEnabled())
        self.assertEqual(editor.toPlainText(), "课程 PDF 按章节整理")
        window.organize_page.mode_combo.setCurrentIndex(0)
        self.assertTrue(editor.isEnabled())
        self.assertEqual(editor.toPlainText(), "课程 PDF 按章节整理")
        self.assertIn("不会被本地分类器理解", window.organize_page.rule_mode_note.text())
        window.close()

    def test_orbit_composer_selects_and_clears_explicit_text_attachments(self) -> None:
        composer = ChatInput()
        with tempfile.TemporaryDirectory() as directory:
            text_file = Path(directory) / "链表练习.py"
            text_file.write_text("print('node')", encoding="utf-8")
            composer.set_attachments((text_file,))
            self.assertEqual(composer.selected_attachments, (text_file,))
            self.assertIn("链表练习.py", composer.attachment_label.text())

            sent: list[tuple[str, object]] = []
            composer.send_requested.connect(lambda text, paths: sent.append((text, paths)))
            composer.editor.setPlainText("解释代码")
            composer._submit()
            self.assertEqual(sent, [("解释代码", (text_file,))])

            composer.clear_attachments()
            self.assertEqual(composer.selected_attachments, ())
            self.assertTrue(composer.attachment_label.isHidden())
        composer.close()

    def test_orbit_attachment_send_requires_disclosure_and_keeps_only_filename_in_history(self) -> None:
        self.settings_store.save(AISettings("deepseek", "https://api.deepseek.com", "deepseek-flash",
                                            10, "user-key"))
        window = self._new_window()
        captured: list[tuple[dict[str, object], ...]] = []
        sent_attachments: list[tuple[Path, ...]] = []

        class AttachmentService:
            def __init__(self, settings):
                self.settings = settings

            def respond(self, messages, cancel_event, attachments=()):
                captured.append(tuple(messages[-1:]))
                sent_attachments.append(attachments)
                return "文件内容已分析。"

        with tempfile.TemporaryDirectory() as directory:
            selected_file = Path(directory) / "作业.py"
            selected_file.write_text("print('ok')", encoding="utf-8")
            with patch.object(window, "_confirm_attachment_upload", return_value=True) as disclosure, \
                    patch.object(window, "_confirm_chat_privacy", return_value=True), \
                    patch("filemind.ui.main_window.ChatService", AttachmentService):
                window._send_chat_message("解释这个文件", (selected_file,))
                self._wait_for_chat_task(window)

            conversation = self.chat_history.get_conversation(window._chat_conversation_id)
            serialized = self.chat_history.history_path.read_text(encoding="utf-8")
            self.assertEqual(disclosure.call_count, 1)
            self.assertEqual(conversation.messages[0].attachments, ("作业.py",))
            self.assertEqual(conversation.messages[1].content, "文件内容已分析。")
            self.assertIn("作业.py", serialized)
            self.assertNotIn(directory, serialized)
            self.assertEqual(captured[0][0]["content"], "解释这个文件")
            self.assertEqual(sent_attachments, [(selected_file,)])
        window.close()

    def test_orbit_attachment_picker_rejects_unsupported_document_formats(self) -> None:
        composer = ChatInput()
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "资料.pdf"
            pdf_path.write_bytes(b"virtual pdf")
            with self.assertRaisesRegex(ValueError, "暂不支持"):
                composer.set_attachments((pdf_path,))
        composer.close()

    def test_cancelled_attachment_disclosure_does_not_persist_or_send_message(self) -> None:
        self.settings_store.save(AISettings("deepseek", "https://api.deepseek.com", "deepseek-flash",
                                            10, "user-key"))
        window = self._new_window()
        with tempfile.TemporaryDirectory() as directory:
            selected_file = Path(directory) / "private.txt"
            selected_file.write_text("private contents", encoding="utf-8")
            with patch.object(window, "_confirm_attachment_upload", return_value=False), \
                    patch("filemind.ui.main_window.ChatService") as service:
                window._send_chat_message("分析附件", (selected_file,))

            self.assertEqual(self.chat_history.list_conversations(), [])
            service.assert_not_called()
        window.close()

    def test_first_run_opens_orbit_with_deepseek_and_empty_key(self) -> None:
        window = self._new_window()

        self.assertEqual(window.assistant_page.home_composer.model_combo.currentText(),
                         "V4.1 Flash")
        self.assertFalse(window.assistant_page.home_composer.model_combo.itemIcon(0).isNull())
        self.assertEqual(window.assistant_page.home_composer.model_combo.iconSize().width(), 24)
        self.assertFalse(window.assistant_page.setup_notice.isHidden())
        self.assertIn("尚未配置 API Key", window.assistant_page.setup_notice.text())
        settings_page = window.settings_page
        self.assertEqual(settings_page.api_key_edit.text(), "")
        self.assertEqual(settings_page.provider_combo.currentData(), "deepseek")
        window.close()

    def test_orbit_uses_model_changes_after_configuration_save(self) -> None:
        window = self._new_window()
        page = window.settings_page
        page.provider_combo.setCurrentIndex(page.provider_combo.findData("openai"))
        page.base_url_edit.setText("https://example.test/v1")
        page.model_edit.setText("new-model")
        page.api_key_edit.setText("user-key")
        page.timeout_spin.setValue(20)
        self.assertTrue(page.save_current())

        self.assertEqual(window.assistant_page.home_composer.model_combo.currentText(), "new-model")
        self.assertIn("OpenAI · new-model", window.assistant_page.home_composer.model_combo.toolTip())
        self.assertFalse(window.assistant_page.home_composer.model_combo.itemIcon(0).isNull())
        self.assertTrue(window.assistant_page.setup_notice.isHidden())
        window.close()

    def test_chat_request_runs_off_thread_and_persists_real_service_answer(self) -> None:
        configured = AISettings("deepseek", "https://api.deepseek.com", "deepseek-flash", 10, "user-key")
        self.settings_store.save(configured)
        self.settings_store.set_chat_ai_consent("deepseek", True)
        window = self._new_window()
        timer_events: list[bool] = []
        class SlowService:
            def __init__(self, settings):
                self.settings = settings

            def respond(self, messages, cancel_event):
                time.sleep(0.12)
                return "来自测试模型的真实服务层回答"

        QTimer.singleShot(20, lambda: timer_events.append(True))
        with patch("filemind.ui.main_window.ChatService", SlowService):
            window.assistant_page.home_composer.editor.setPlainText("解释链表")
            window.assistant_page._shortcut_clicked("代码解释", "解释链表")
            window._send_chat_message("解释链表")
            self._wait_for_chat_task(window)

        conversation = self.chat_history.get_conversation(window._chat_conversation_id)
        self.assertTrue(timer_events)
        self.assertEqual([message.role for message in conversation.messages], ["user", "assistant"])
        self.assertIn("测试模型", conversation.messages[-1].content)
        window.close()

    def test_missing_key_keeps_orbit_available_without_sending(self) -> None:
        window = self._new_window()
        window.assistant_page.home_composer.editor.setPlainText("你好")
        with patch("filemind.ui.main_window.QMessageBox.information") as notice:
            window._send_chat_message("你好")

        notice.assert_called_once()
        self.assertEqual(window.assistant_page.home_composer.editor.toPlainText(), "你好")
        self.assertEqual(window.page_stack.currentWidget(), window.settings_page)
        self.assertIsNone(window._chat_worker)
        window.close()

    def test_cancelled_chat_result_is_not_saved_over_conversation(self) -> None:
        configured = AISettings("deepseek", "https://api.deepseek.com", "deepseek-flash", 10, "user-key")
        self.settings_store.save(configured)
        self.settings_store.set_chat_ai_consent("deepseek", True)
        window = self._new_window()

        class SlowService:
            def __init__(self, settings):
                self.settings = settings

            def respond(self, messages, cancel_event):
                time.sleep(0.12)
                return "这条取消后的回答不能写入"

        with patch("filemind.ui.main_window.ChatService", SlowService):
            window._send_chat_message("停止这次回答")
            QTimer.singleShot(20, window._cancel_chat_task)
            self._wait_for_chat_task(window)

        conversation = self.chat_history.get_conversation(window._chat_conversation_id)
        self.assertEqual([message.role for message in conversation.messages], ["user"])
        self.assertNotIn("取消后的回答", conversation.messages[-1].content)
        self.assertIn("已停止生成", window.assistant_page.status_label.text())
        window.close()

    def test_recent_chat_can_be_selected_and_deleted_from_sidebar(self) -> None:
        first = self.chat_history.create_conversation()
        first = self.chat_history.add_message(first.conversation_id, "user", "第一段对话")
        second = self.chat_history.create_conversation()
        second = self.chat_history.add_message(second.conversation_id, "user", "第二段对话")
        window = self._new_window()
        self.assertEqual(window.conversation_list.count(), 2)

        older_item = next(window.conversation_list.item(index) for index in range(2)
                          if window.conversation_list.item(index).data(Qt.ItemDataRole.UserRole)
                          == first.conversation_id)
        window._select_chat_item(older_item)
        self.assertEqual(window.assistant_page.current_conversation_id(), first.conversation_id)
        self.assertEqual(window.page_stack.currentWidget(), window.assistant_page)
        window.conversation_list.setCurrentItem(older_item)
        with patch("filemind.ui.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            window._delete_selected_chat()

        self.assertIsNone(self.chat_history.get_conversation(first.conversation_id))
        self.assertIsNotNone(self.chat_history.get_conversation(second.conversation_id))
        window.close()

    def test_directory_can_be_cleared_and_selected_again_without_touching_files(self) -> None:
        with tempfile.TemporaryDirectory() as first_directory, tempfile.TemporaryDirectory() as second_directory:
            first_file = Path(first_directory) / "课程资料.txt"
            second_file = Path(second_directory) / "第二目录.pdf"
            first_file.write_text("virtual data", encoding="utf-8")
            second_file.write_text("virtual data", encoding="utf-8")
            window = self._new_window()
            window.organize_page.set_directory(first_directory)
            window._scan_folder(first_directory)
            self._wait_for_task(window)
            self.assertEqual(window.organize_page.file_count.value_label.text(), "1")
            self.assertIsNotNone(window._preview_dialog)
            window._preview_dialog.close()

            with patch("filemind.ui.main_window.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.Yes):
                window.organize_page.clear_directory_button.click()

            self.assertEqual(window.organize_page.path_edit.text(), "")
            self.assertIsNone(window.organize_page.plan)
            self.assertEqual(window.organize_page.file_count.value_label.text(), "—")
            self.assertEqual(first_file.read_text(encoding="utf-8"), "virtual data")

            window._select_directory(second_directory)
            self._wait_for_task(window)
            self.assertEqual(window.organize_page.path_edit.text(), second_directory)
            self.assertEqual(window.organize_page.table_model.operations[0].source, second_file)
            self.assertEqual(first_file.read_text(encoding="utf-8"), "virtual data")
            if window._preview_dialog:
                window._preview_dialog.close()
            window.close()

    def test_stale_scan_result_is_ignored_after_directory_clear(self) -> None:
        window = self._new_window()
        window.organize_page.set_directory("")
        window._folder_generation += 1
        stale_generation = window._folder_generation - 1
        window._scan_completed((None, [], None, {}), stale_generation)

        self.assertIsNone(window.organize_page.plan)
        self.assertIsNone(window._preview_dialog)
        window.close()

    def test_plan_preview_uses_target_tree_and_filters_the_existing_plan_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "课程笔记.txt").write_text("virtual data", encoding="utf-8")
            (root / "讲义.pdf").write_text("virtual data", encoding="utf-8")
            window = self._new_window()
            window.resize(1024, 700)
            window.organize_page.set_directory(str(root))
            window._scan_folder(str(root))
            self._wait_for_task(window)

            dialog = window._preview_dialog
            self.assertIsNotNone(dialog)
            self.assertFalse(hasattr(window.organize_page, "table"))
            self.assertEqual(dialog.proxy_model.rowCount(), 2)
            folder = dialog.tree.topLevelItem(0).child(0)
            file_node = folder.child(0)
            dialog.tree.setCurrentItem(file_node)
            QApplication.processEvents()
            self.assertEqual(dialog.proxy_model.rowCount(), 1)
            self.assertTrue(dialog.execute_button.isEnabled())
            operation = window.organize_page.table_model.operations[0]
            self.assertEqual(dialog.detail_source.text(), str(operation.source))
            self.assertEqual(dialog.detail_target.text(), str(operation.target))
            self.assertIn("移动", dialog.detail_operation.text())
            self.assertLessEqual(dialog.width(), 968)
            dialog.close()
            window.close()

    def test_ai_configuration_button_distinguishes_saved_settings_from_missing_key(self) -> None:
        window = self._new_window()
        window.organize_page.mode_combo.setCurrentIndex(1)
        self.assertEqual(window.organize_page.settings_link.text(), "配置 AI 服务")
        self.assertIn("缺少 API Key", window.organize_page.rule_mode_note.text())
        window.close()

        self.settings_store.save(AISettings("deepseek", "https://api.deepseek.com", "model-name", 45,
                                            "user-key"))
        window = self._new_window()
        window.organize_page.mode_combo.setCurrentIndex(1)
        self.assertEqual(window.organize_page.settings_link.text(), "管理 AI 服务")
        self.assertIn("尚未确认当前连接状态", window.organize_page.settings_link.toolTip())
        window.close()

    def test_organize_page_keeps_rule_editor_and_actions_usable_at_1024x700(self) -> None:
        window = self._new_window()
        window.resize(1024, 700)
        window.show()
        QApplication.processEvents()

        self.assertGreaterEqual(window.organize_page.rule_input.height(), 58)
        self.assertTrue(window.organize_page.execute_button.isVisible())
        self.assertTrue(window.organize_page.scan_button.isVisible())
        self.assertLessEqual(window.organize_page.content_scroll.widget().width(),
                             window.organize_page.content_scroll.viewport().width() + 1)
        window.close()

    def test_failed_ai_generation_keeps_rule_and_does_not_open_a_success_preview(self) -> None:
        from filemind.ai.openai_compatible import AIServiceError

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "课堂笔记.txt").write_text("virtual data", encoding="utf-8")
            settings = AISettings("deepseek", "https://api.deepseek.com", "model-name", 45, "user-key")
            self.settings_store.save(settings)
            self.settings_store.set_online_ai_consent(True)
            window = self._new_window()
            window.organize_page.set_directory(str(root))
            window.organize_page.mode_combo.setCurrentIndex(1)
            window.organize_page.rule_input.setPlainText("按课程主题分类")

            with patch("filemind.ui.main_window.OpenAICompatibleClient", side_effect=AIServiceError("请求超时")), \
                    patch("filemind.ui.main_window.QMessageBox.critical"):
                window._scan_folder(str(root))
                self._wait_for_task(window)

            self.assertIsNone(window._preview_dialog)
            self.assertIsNone(window.organize_page.plan)
            self.assertEqual(window.organize_page.rule_input.toPlainText(), "按课程主题分类")
            self.assertIn("请求超时", window.organize_page.page_status.text())
            window.close()

    def test_recent_chat_rows_have_compact_actions_and_empty_state(self) -> None:
        window = self._new_window()
        self.assertFalse(window.conversation_empty.isHidden())
        self.assertTrue(window.conversation_list.isHidden())
        self.assertEqual(window.conversation_list.frameShape(), QFrame.Shape.NoFrame)

        conversation = self.chat_history.create_conversation()
        conversation = self.chat_history.add_message(
            conversation.conversation_id, "user", "这是一条标题特别长的对话用于检查省略效果"
        )
        window._refresh_conversation_list()
        item = window.conversation_list.item(0)
        row = window.conversation_list.itemWidget(item)
        row.resize(140, 44)
        QApplication.processEvents()
        self.assertEqual(row.full_title, conversation.title)
        self.assertEqual(row.title_label.toolTip(), conversation.title)
        long_row = ConversationRow("long", "这是一条很长很长很长很长很长的 Orbit 对话标题")
        long_row.resize(140, 44)
        long_row.show()
        QApplication.processEvents()
        self.assertLess(len(long_row.title_label.text()), len(long_row.full_title))
        self.assertFalse(hasattr(window, "delete_chat_button"))
        self.assertTrue(window.conversation_empty.isHidden())
        self.assertFalse(window.conversation_list.isHidden())
        window.close()

    def test_provider_icon_is_transparent_and_fits_model_selector(self) -> None:
        icon = provider_icon("deepseek")
        pixmap = icon.pixmap(22, 22)

        self.assertFalse(pixmap.isNull())
        self.assertEqual((pixmap.width(), pixmap.height()), (22, 22))
        self.assertEqual(pixmap.toImage().pixelColor(0, 0).alpha(), 0)

    def test_model_selector_focus_and_popup_render_without_native_double_frame(self) -> None:
        window = self._new_window()
        window._show_page("assistant")
        window.show()
        combo = window.assistant_page.home_composer.model_combo
        combo.setFocus()
        QApplication.processEvents()

        self.assertFalse(combo.hasFrame())
        self.assertEqual(combo.height(), 40)
        self.assertFalse(combo.grab().isNull())
        combo.showPopup()
        QApplication.processEvents()
        self.assertTrue(combo.view().isVisible())
        combo.hidePopup()
        window.close()

    def test_sidebar_navigation_and_recent_history_scroll_independently(self) -> None:
        future_items = tuple((f"future-{index}", f"未来功能 {index}", "settings",
                              f"未来功能 {index}", "用于检查导航区可滚动。")
                             for index in range(10))
        with patch("filemind.ui.main_window.NAVIGATION_ITEMS", NAVIGATION_ITEMS + future_items):
            window = self._new_window()
            window._show_page("assistant")
            window.show()
            QApplication.processEvents()
            sidebar_width = window.sidebar.width()
            self.assertGreater(window.navigation_scroll.verticalScrollBar().maximum(), 0)

            for index in range(24):
                conversation = self.chat_history.create_conversation()
                self.chat_history.add_message(conversation.conversation_id, "user", f"对话 {index}")
            window._refresh_conversation_list()
            QApplication.processEvents()

            self.assertEqual(window.sidebar.width(), sidebar_width)
            self.assertGreaterEqual(window.recent_area.height(), 150)
            self.assertGreater(window.conversation_list.verticalScrollBar().maximum(), 0)
            window.close()

    def test_orbit_privacy_disclosure_is_branded_and_remembered_per_provider(self) -> None:
        settings = AISettings("deepseek", "https://api.deepseek.com", "deepseek-flash", 10, "key")
        window = self._new_window()
        observed: list[str] = []

        def accept_dialog() -> None:
            dialog = QApplication.activeModalWidget()
            observed.append(dialog.objectName())
            dialog.accept()

        QTimer.singleShot(0, accept_dialog)
        self.assertTrue(window._confirm_chat_privacy(settings))
        self.assertEqual(observed, ["OrbitPrivacyDialog"])
        self.assertTrue(self.settings_store.has_chat_ai_consent("deepseek"))
        self.assertFalse(self.settings_store.has_chat_ai_consent("openai"))
        self.assertTrue(window._confirm_chat_privacy(settings))
        window.close()

    def test_chat_error_has_retry_and_settings_navigation(self) -> None:
        from filemind.ai.openai_compatible import AIServiceError

        self.settings_store.save(AISettings("deepseek", "https://api.deepseek.com", "deepseek-flash",
                                            10, "user-key"))
        self.settings_store.set_chat_ai_consent("deepseek", True)
        window = self._new_window()

        class FailedService:
            def __init__(self, settings):
                self.settings = settings

            def respond(self, messages, cancel_event):
                raise AIServiceError("DNS 解析失败，请检查网络连接和域名解析。")

        with patch("filemind.ui.main_window.ChatService", FailedService):
            window._send_chat_message("请帮我分析问题")
            self._wait_for_chat_task(window)

        self.assertIn("DNS 解析失败", window.assistant_page.status_label.text())
        self.assertFalse(window.assistant_page.retry_button.isHidden())
        self.assertFalse(window.assistant_page.configure_error_button.isHidden())
        window.assistant_page.configure_error_button.click()
        self.assertEqual(window.page_stack.currentWidget(), window.settings_page)
        window.close()

    @staticmethod
    def _wait_for_task(window: MainWindow) -> None:
        event_loop = QEventLoop()
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(event_loop.quit)
        poll = QTimer()
        poll.setInterval(10)
        poll.timeout.connect(lambda: event_loop.quit() if window._active_worker is None else None)
        poll.start()
        timeout.start(5000)
        event_loop.exec()
        poll.stop()
        if window._active_worker is not None:
            raise TimeoutError("后台扫描任务未在 5 秒内完成")

    @staticmethod
    def _wait_for_chat_task(window: MainWindow) -> None:
        event_loop = QEventLoop()
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(event_loop.quit)
        poll = QTimer()
        poll.setInterval(10)
        poll.timeout.connect(lambda: event_loop.quit() if window._chat_worker is None else None)
        poll.start()
        timeout.start(5000)
        event_loop.exec()
        poll.stop()
        if window._chat_worker is not None:
            raise TimeoutError("Orbit 请求未在 5 秒内完成")


class _FakeSettingsStore:
    def load(self, provider_id=None):
        return AISettings("deepseek", "https://api.deepseek.com", "deepseek-flash", 10, "mock-key")

    def has_online_ai_consent(self):
        return True

    def set_online_ai_consent(self, accepted):
        return None


class _MemorySecretStore:
    def __init__(self):
        self.values = {}

    def get(self, target):
        return self.values.get(target)

    def set(self, target, value):
        self.values[target] = value

    def delete(self, target):
        self.values.pop(target, None)


if __name__ == "__main__":
    unittest.main()
