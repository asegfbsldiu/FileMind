"""Plan preview checks using only generated temporary files."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from filemind.core.planner import build_plan
from filemind.core.scanner import scan_files
from filemind.models import ClassificationResult, OperationPlan
from filemind.ui.dialogs.plan_preview import PlanPreviewDialog
from filemind.ui.widgets.file_table import FilePlanTableModel


@pytest.fixture(scope="session")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def preview(root: Path) -> PlanPreviewDialog:
    plan = build_plan(root, scan_files(root), lambda item: ClassificationResult(
        "文档2" if item.name.startswith("other") else "文档", "测试理由",
        target_subdirectory="数据结构/第一章" if item.name.startswith("nested") else ""))
    model = FilePlanTableModel()
    model.set_plan(plan)
    return PlanPreviewDialog(plan, model)


def test_icons_hierarchy_exact_folder_and_file_filter(application, tmp_path: Path) -> None:
    for name in ("notes.txt", "notes.txt.bak", "other.txt", "nested.txt"):
        (tmp_path / name).write_text("virtual", encoding="utf-8")
    dialog = preview(tmp_path)
    root = dialog.tree.topLevelItem(0)
    folders = {root.child(index).text(0): root.child(index) for index in range(root.childCount())}
    document = folders["文档"]
    assert not root.icon(0).isNull()
    assert not document.icon(0).isNull()
    dialog.tree.setCurrentItem(document)
    assert dialog.proxy_model.rowCount() == 3
    file_node = next(document.child(index) for index in range(document.childCount())
                     if document.child(index).text(0) == "notes.txt")
    dialog.tree.setCurrentItem(file_node)
    assert dialog.proxy_model.rowCount() == 1
    assert dialog.detail_original.text() == "notes.txt"
    assert file_node.toolTip(0) == str(tmp_path / "文档" / "notes.txt")
    assert document.childCount() == 3
    dialog.close()


def test_search_no_results_and_warning_prevent_execution(application, tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("virtual", encoding="utf-8")
    (tmp_path / "文档").mkdir()
    (tmp_path / "文档" / "notes.txt").write_text("existing", encoding="utf-8")
    dialog = preview(tmp_path)
    assert not dialog.execute_button.isEnabled()
    assert dialog.tree.topLevelItem(0).child(0).child(0).text(1) == "冲突"
    received: list[object] = []
    dialog.execute_requested.connect(received.append)
    dialog._request_execution()
    assert not received
    dialog.search_edit.setText("not present")
    assert dialog.proxy_model.rowCount() == 0
    assert "没有文件" in dialog.detail_original.text()
    dialog.search_edit.clear()
    assert dialog.proxy_model.rowCount() == 1
    dialog.close()


def test_empty_plan_is_visible_but_not_executable(application, tmp_path: Path) -> None:
    model = FilePlanTableModel()
    plan = OperationPlan(tmp_path, ())
    model.set_plan(plan)
    dialog = PlanPreviewDialog(plan, model)
    assert dialog.tree.topLevelItemCount() == 1
    assert dialog.tree.topLevelItem(0).text(1) == "0 个文件"
    assert not dialog.execute_button.isEnabled()
    dialog.close()
