"""Qt layout checks use generated files and isolated application preferences."""

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from filemind.models import FileInfo
from filemind.ui.pages.organize_page import OrganizePage
from filemind.ui.styles.theme import apply_theme
from filemind.ui.widgets.format_cards import FormatCards
from tools.review_ui import build_review


def test_splitter_drag_keeps_controls_available_and_emits_height(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "empty")
    apply_theme(QApplication.instance())
    window.resize(1024, 700)
    window.show()
    QTest.qWait(50)
    page = window.organize_page
    spy = QSignalSpy(page.layout_changed)
    before = page.layout_splitter.sizes()[0]
    handle = page.layout_splitter.handle(1)
    origin = handle.rect().center()
    QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=origin)
    QTest.mouseMove(handle, origin + QPoint(0, 55), delay=15)
    QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=origin + QPoint(0, 55))
    QTest.qWait(30)
    assert spy.count() > 0
    assert abs(page.layout_splitter.sizes()[0] - before) >= 20
    assert page.layout_splitter.sizes()[1] >= 180
    assert page.execute_button.isVisible()
    assert page.history_button.isVisible()
    window.close()


def test_empty_guidance_distinguishes_selection_scan_and_import(tmp_path: Path) -> None:
    page = OrganizePage()
    page.resize(800, 650)
    page.show()
    QTest.qWait(20)
    empty = page.workspace.import_empty
    assert empty.isVisible()
    assert "选择文件夹" == empty.action_button.text()
    with patch("filemind.ui.pages.organize_page.QFileDialog.getExistingDirectory", return_value="") as choose:
        empty.action_button.click()
        choose.assert_called_once()
    page.set_directory(str(tmp_path))
    assert "读取文件" == empty.action_button.text()
    assert "暂无" not in empty.title.text()
    page.rule_input.setFocus()
    QTest.keyClick(page.rule_input, Qt.Key.Key_Tab)
    assert page.rule_send_button.hasFocus()
    submitted = QSignalSpy(page.import_requested)
    empty.action_button.click()
    assert submitted.count() == 1
    page.set_files([])
    assert "暂无" in empty.title.text()
    assert "选择其他文件夹" == empty.action_button.text()
    source = tmp_path / "中文文档.txt"
    source.write_text("generated fixture", encoding="utf-8")
    info = source.stat()
    page.set_files([FileInfo(source, info.st_size, info.st_mtime_ns)])
    assert empty.isHidden()
    assert page.workspace.imports_view.isVisible()
    assert page.import_model.rowCount() == 1
    assert not page.execute_button.isEnabled()
    page.close()


@pytest.mark.parametrize("width,height", [(1024, 700), (1280, 850)])
def test_organizer_narrow_layout_has_no_lost_primary_actions(
        tmp_path: Path, width: int, height: int) -> None:
    window, _ = build_review(tmp_path, "empty")
    apply_theme(QApplication.instance())
    window.resize(width, height)
    window.show()
    QTest.qWait(40)
    page = window.organize_page
    page.mode_combo.setCurrentIndex(1)
    page.rule_input.setFocus()
    QTest.keyClicks(page.rule_input, "Keep original names")
    page.mode_combo.setCurrentIndex(0)
    page.mode_combo.setCurrentIndex(1)
    assert page.rule_input.toPlainText() == "Keep original names"
    assert not page.rule_input.isReadOnly()
    assert page.content_scroll.widget().width() <= page.content_scroll.viewport().width()
    bounds = QRect(0, 0, window.width(), window.height())
    for button in (page.history_button, page.execute_button, page.cancel_button):
        button_bounds = QRect(button.mapTo(window, QPoint()), button.size())
        assert bounds.contains(button_bounds), button.text()
    assert page.layout_splitter.sizes()[1] >= 180
    window.close()


def test_format_cards_reflow_without_removing_content() -> None:
    widget = FormatCards()
    widget.resize(1100, 1000)
    widget.show()
    QTest.qWait(20)
    total = len(widget.cards)
    assert widget._columns == 3
    widget.resize(700, 1200)
    QTest.qWait(20)
    assert widget._columns == 2
    assert widget.grid.count() == total
    widget.resize(420, 2000)
    QTest.qWait(20)
    assert widget._columns == 1
    assert widget.grid.count() == total
    assert all(card.isVisible() for card in widget.cards)
    widget.close()
