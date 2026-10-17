"""Teammate changes integrated with the current UI and filesystem safeguards."""

from dataclasses import replace
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QStyle, QStyleOptionViewItem

from filemind.core.classifier import classify_file
from filemind.core.executor import execute_plan, undo_record
from filemind.core.plan_editor import PlanEditor
from filemind.core.planner import build_plan, stable_file_id
from filemind.core.scanner import scan_files
from filemind.models import OperationPlan
from filemind.storage.history import OperationHistory
from filemind.ui.dialogs.plan_preview import PlanPreviewDialog
from filemind.ui.pages.history_page import HistoryPage
from filemind.ui.widgets.file_table import CATEGORY_COLUMN, EXECUTE_COLUMN, NAME_COLUMN
from tools.review_ui import build_review


def make_plan(root: Path) -> OperationPlan:
    """Use only short generated files in pytest's private temporary directory."""
    for name in ("notes.txt", "报告.pdf"):
        (root / name).write_text("integration fixture", encoding="utf-8")
    return build_plan(root, scan_files(root), classify_file)


def test_editor_rejects_absolute_subdirectory_and_keeps_previous_value(tmp_path: Path) -> None:
    editor = PlanEditor(make_plan(tmp_path))
    source = editor.rows[0].source
    editor.set_target_subdirectory(source, "第一章")
    previous = editor.build()
    for directory in ("/outside", "//server/share", "../escape", "C:/escape"):
        with pytest.raises(ValueError):
            editor.set_target_subdirectory(source, directory)
        assert editor.build() == previous


def test_editor_marks_an_existing_parent_file_without_changing_disk(tmp_path: Path) -> None:
    editor = PlanEditor(make_plan(tmp_path))
    source = editor.rows[0].source
    (tmp_path / "被占用").write_text("keep", encoding="utf-8")
    editor.set_category(source, "被占用")
    operation = editor.build().operations[0]
    assert "非目录" in (operation.warning or "")
    assert source.exists()
    assert (tmp_path / "被占用").read_text(encoding="utf-8") == "keep"


def test_conflict_appearing_after_preview_does_not_stop_other_files_or_undo(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    blocked, movable = plan.operations
    blocked.target.parent.mkdir()
    blocked.target.write_text("existing destination", encoding="utf-8")
    history = OperationHistory(tmp_path)
    progress: list[tuple[int, int]] = []
    result = execute_plan(plan, history, True, on_progress=lambda done, total: progress.append((done, total)))
    assert (result.succeeded, result.skipped, result.failed) == (1, 1, 0)
    assert blocked.source.exists()
    assert blocked.target.read_text(encoding="utf-8") == "existing destination"
    assert movable.target.exists()
    assert progress == [(1, 2), (2, 2)]
    record = history.list_records()[0]
    assert {item["status"] for item in record.operations} == {"success", "skipped"}
    undone = undo_record(history, record.operation_id)
    assert (undone.succeeded, undone.failed) == (1, 0)
    assert movable.source.exists()
    assert blocked.target.read_text(encoding="utf-8") == "existing destination"


def test_excluded_and_ai_failure_rows_never_move_and_do_not_block_good_rows(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    failed = {stable_file_id(plan.operations[0].original_name): "mock unavailable"}
    plan = build_plan(tmp_path, scan_files(tmp_path), classify_file, failed_file_ids=failed)
    history = OperationHistory(tmp_path)
    result = execute_plan(plan, history, True)
    assert (result.succeeded, result.skipped, result.failed) == (1, 1, 0)
    blocked = plan.operations[0]
    assert blocked.source.exists() and not blocked.target.exists()
    assert "AI 批次失败" in result.skip_reasons[0]
    excluded = OperationPlan(tmp_path, (replace(blocked, excluded=True),))
    stopped = Event()
    stopped.set()
    cancelled = execute_plan(excluded, history, True, cancel_event=stopped)
    assert cancelled.cancelled and cancelled.succeeded == 0
    assert blocked.source.exists()


def test_checkbox_indicator_toggles_once_and_updates_inline_plan(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "organize")
    page = window.organize_page
    dialog = PlanPreviewDialog(page.plan, page.table_model, window)
    window.show()
    dialog.show()
    QTest.qWait(30)
    model = page.table_model
    for excluded in (True, False):
        index = dialog.proxy_model.index(0, EXECUTE_COLUMN)
        dialog.table.scrollTo(index)
        QApplication.processEvents()
        option = QStyleOptionViewItem()
        option.initFrom(dialog.table)
        option.rect = dialog.table.visualRect(index)
        dialog.table.itemDelegateForColumn(EXECUTE_COLUMN).initStyleOption(option, index)
        rectangle = dialog.table.style().subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator,
                                                        option, dialog.table)
        assert not rectangle.isEmpty()
        QTest.mouseClick(dialog.table.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
        assert model.operations[0].excluded is excluded
        assert page.plan == model.current_plan()
        assert page.pending_count.value_label.text() == str(len(model.operations) - int(excluded))
        assert f"{int(excluded)} 项将跳过" in dialog.summary.text()
    dialog.close()
    window.close()


def test_edit_role_is_initialized_and_rejected_edits_preserve_source_and_prior_plan(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "organize")
    model = window.organize_page.table_model
    name = model.index(0, NAME_COLUMN)
    assert name.data(Qt.ItemDataRole.EditRole) == model.operations[0].new_name
    assert model.setData(model.index(0, CATEGORY_COLUMN), "已确认资料")
    accepted = model.current_plan()
    failures: list[str] = []
    model.edit_rejected.connect(failures.append)
    assert not model.setData(model.index(0, NAME_COLUMN), "outside.exe")
    assert model.current_plan() == accepted
    assert "扩展名" in failures[0]
    assert all(item.source.exists() for item in accepted.operations)
    window.close()


def test_declining_second_confirmation_never_invokes_executor(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "organize")
    plan = window.organize_page.plan
    window._history = OperationHistory(plan.root)
    with patch("filemind.ui.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.No), \
            patch("filemind.ui.main_window.execute_plan") as execute:
        window._confirm_execution(plan)
        execute.assert_not_called()
    assert all(item.source.exists() for item in plan.operations)
    window.close()


def test_history_explains_skips_and_does_not_offer_an_empty_undo(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    excluded = OperationPlan(tmp_path, tuple(replace(item, excluded=True) for item in plan.operations))
    history = OperationHistory(tmp_path)
    execute_plan(excluded, history, True)
    page = HistoryPage()
    page.set_records(history.list_records())
    page.table.selectRow(0)
    assert "跳过 2" in page.table_model.index(0, 2).data()
    assert "已在预览中排除" in page.table_model.index(0, 2).data(Qt.ItemDataRole.ToolTipRole)
    assert not page.undo_button.isEnabled()
    page.close()


def test_preview_allows_safe_rows_in_a_mixed_conflict_plan(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "organize")
    page = window.organize_page
    conflict = page.plan.operations[0]
    conflict.target.parent.mkdir(parents=True)
    conflict.target.write_text("keep destination", encoding="utf-8")
    plan = PlanEditor(page.plan).build()
    page.set_plan(plan)
    dialog = PlanPreviewDialog(plan, page.table_model, window)
    selected: list[OperationPlan] = []
    dialog.execute_requested.connect(selected.append)
    assert dialog.execute_button.isEnabled()
    assert "1 项将跳过" in dialog.summary.text()
    dialog._request_execution()
    assert len(selected) == 1
    assert selected[0] == page.plan
    assert all(item.source.exists() for item in selected[0].operations)
    window.close()


def test_closed_preview_does_not_react_to_later_model_edits(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "organize")
    page = window.organize_page
    dialog = PlanPreviewDialog(page.plan, page.table_model, window)
    dialog.show()
    dialog.close()
    with patch.object(dialog, "_rebuild_tree") as rebuild:
        assert page.table_model.setData(page.table_model.index(0, CATEGORY_COLUMN), "后续编辑")
        rebuild.assert_not_called()
    window.close()
