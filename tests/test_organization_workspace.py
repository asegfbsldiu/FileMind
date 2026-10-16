"""Real organizer submissions with generated files and mocked network clients."""

import time
from pathlib import Path
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from filemind.ai.schemas import AIOrganizationResult
from filemind.models import FileSuggestion
from filemind.storage.settings import AISettings
from tools.review_ui import build_review


def wait_for_task(window) -> None:
    # 共享 CI 运行器只有两个虚拟核心，全局 Qt 线程池可能仍在执行锁屏的 PBKDF2 任务，
    # 因此给后台任务更宽的预算；任务始终不结束仍然会失败。
    deadline = time.monotonic() + 30
    while window._active_worker is not None and time.monotonic() < deadline:
        QTest.qWait(10)
    assert window._active_worker is None, "后台任务未在等待时间内结束"
    QApplication.processEvents()


def test_directory_import_does_not_invoke_ai_and_preserves_before_list(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    selected = tmp_path / "import"
    selected.mkdir()
    (selected / "课程.txt").write_text("virtual", encoding="utf-8")
    window.organize_page.mode_combo.setCurrentIndex(1)
    with patch("filemind.ui.main_window.OpenAICompatibleClient", side_effect=AssertionError("not during import")):
        window.organize_page.folder_selected.emit(str(selected))
        wait_for_task(window)
    assert window.organize_page.import_model.rowCount() == 1
    assert window.organize_page.plan is None
    assert window._preview_dialog is None
    assert not window.organize_page.execute_button.isEnabled()
    window.close()


def test_enter_submits_real_ai_service_path_and_shift_enter_only_adds_line(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    selected = tmp_path / "import"
    selected.mkdir()
    (selected / "课程.txt").write_text("virtual", encoding="utf-8")
    page = window.organize_page
    page.set_directory(str(selected))
    page.mode_combo.setCurrentIndex(1)
    page.rule_input.setPlainText("按课程整理")
    captured: list[str] = []

    class Model:
        def __init__(self, settings):
            pass

        def organize_files(self, files, rule, rename, progress, cancel):
            captured.append(rule)
            item = files[0]
            suggestion = FileSuggestion(item.file_name, "课程资料", item.file_name, "文件名匹配课程", item.file_id)
            return AIOrganizationResult({item.file_id: suggestion}, ())

    with patch.object(window.settings_store, "load", return_value=AISettings(
            "deepseek", "https://api.deepseek.com", "deepseek-flash", 10, "mock-key")), \
            patch.object(window, "_confirm_ai_privacy", return_value=True), \
            patch("filemind.ui.main_window.OpenAICompatibleClient", Model):
        QTest.keyClick(page.rule_input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        assert not captured
        QTest.keyClick(page.rule_input, Qt.Key.Key_Return)
        assert not page.rule_send_button.isEnabled()
        wait_for_task(window)
    assert captured == [page.rule_input.toPlainText().strip()]
    assert page.plan.operations[0].classification.source == "AI"
    assert "已收到 1 项 AI 建议" in page.page_status.text()
    assert page.workspace.target_tree is not None
    assert window._preview_dialog is None
    assert (selected / "课程.txt").exists()
    window.close()


def test_local_month_preset_is_real_and_rule_changes_invalidate_execution(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "organize")
    page = window.organize_page
    page.preset_combo.setCurrentIndex(1)
    page.rule_send_button.click()
    wait_for_task(window)
    assert all(item.classification.source == "规则" for item in page.plan.operations)
    assert all(len(item.classification.category) == 7 for item in page.plan.operations)
    page.rule_input.setPlainText("保留这段自定义文本")
    assert page.plan is None
    assert not page.execute_button.isEnabled()
    assert page.import_model.rowCount() == 5
    assert page.pending_count.value_label.text() == "—"
    window.close()


def test_edited_rule_during_ai_request_discards_old_plan(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    selected = tmp_path / "source"
    selected.mkdir()
    (selected / "课程.txt").write_text("virtual", encoding="utf-8")
    page = window.organize_page
    page.set_directory(str(selected))
    page.mode_combo.setCurrentIndex(1)
    page.rule_input.setPlainText("第一版规则")
    entered, release = Event(), Event()

    class DelayedModel:
        def __init__(self, settings):
            pass

        def organize_files(self, files, rule, rename, progress, cancel):
            entered.set()
            assert release.wait(3)
            return AIOrganizationResult({}, ())

    with patch.object(window, "_prepare_ai_settings", return_value=AISettings(
            "deepseek", "https://api.deepseek.com", "mock-model", 10, "mock-key")), \
            patch("filemind.ui.main_window.OpenAICompatibleClient", DelayedModel):
        page.rule_send_button.click()
        deadline = time.monotonic() + 15
        while not entered.is_set() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert entered.is_set()
        assert page.rule_input.isEnabled()
        page.rule_input.setPlainText("新的整理要求")
        release.set()
        wait_for_task(window)
    assert page.plan is None
    assert page.rule_input.toPlainText() == "新的整理要求"
    assert not page.execute_button.isEnabled()
    assert (selected / "课程.txt").exists()
    window.close()
