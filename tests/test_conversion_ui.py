"""Qt conversion flow, cancellation, and responsive Orbit checks."""

import time
from pathlib import Path
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from filemind.ui.pages.conversion_page import ConversionPage
from tools.review_ui import build_review


def wait_for_conversion(page: ConversionPage) -> None:
    deadline = time.monotonic() + 5
    while page.is_busy and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not page.is_busy
    QApplication.processEvents()


def test_valid_target_save_cancel_and_real_conversion(tmp_path: Path) -> None:
    page = ConversionPage()
    assert not page.convert_button.isEnabled()
    source = tmp_path / "课程.txt"
    source.write_text("学习数据结构", encoding="utf-8")
    page.select_file(str(source))
    wait_for_conversion(page)
    assert page.convert_button.isEnabled()
    assert page.target_combo.currentData() == "utf8"
    with patch("filemind.ui.pages.conversion_page.QFileDialog.getSaveFileName", return_value=("", "")):
        page.convert_button.click()
    assert "取消" in page.status_label.text()
    output = tmp_path / "输出.txt"
    page.start_conversion(output)
    wait_for_conversion(page)
    assert output.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert page.result.output == output
    assert page.open_result_button.isEnabled()
    page.close()


def test_background_inspection_remains_responsive_and_cancel_discards_result(tmp_path: Path) -> None:
    source = tmp_path / "test.txt"
    source.write_text("fixture")
    page = ConversionPage()
    entered, release = Event(), Event()
    from filemind.ui.pages import conversion_page
    original = conversion_page.inspect_input

    def slow_inspection(path):
        entered.set()
        assert release.wait(3)
        return original(path)

    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(5)
    with patch.object(conversion_page, "inspect_input", side_effect=slow_inspection):
        page.select_file(str(source))
        deadline = time.monotonic() + 2
        while not entered.is_set() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert entered.is_set()
        QTest.qWait(40)
        assert ticks
        assert not page.convert_button.isEnabled()
        page.cancel()
        release.set()
        wait_for_conversion(page)
    timer.stop()
    assert page.input_info is None
    assert "取消" in page.status_label.text()
    assert source.read_text() == "fixture"
    page.close()


def test_invalid_selection_clears_old_conversion_target(tmp_path: Path) -> None:
    page = ConversionPage()
    page.select_file(str(tmp_path / "missing.txt"))
    wait_for_conversion(page)
    assert not page.convert_button.isEnabled()
    assert page.input_info is None
    assert "普通文件" in page.status_label.text()
    page.close()


def test_navigation_and_orbit_reflow_at_common_sizes(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    window.show()
    for width, height in ((1024, 700), (1280, 850)):
        window.resize(width, height)
        QTest.qWait(40)
        assistant = window.assistant_page
        composer = assistant.home_composer
        assert composer.send_button.height() == 40
        assert composer.model_combo.height() == 40
        assert composer.model_combo.width() >= 120
        assert assistant.suggestion_cards[0].width() >= 100
        assert window.conversation_list.height() >= 120
    window._show_page("conversion")
    assert window.page_stack.currentWidget() is window.conversion_page
    window._show_page("organize")
    assert window.organize_page.rule_input.isEnabled()
    window.resize(1024, 700)
    window.workspace_splitter.setSizes([380, 639])
    window._show_page("assistant")
    QTest.qWait(40)
    assert window.width() == 1024
    assert window.assistant_page._shortcut_columns == 2
    window._show_page("conversion")
    QTest.qWait(20)
    assert window.width() == 1024
    window.close()


def test_close_waits_for_conversion_to_stop_safely(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "conversion")
    window.show()
    entered, release = Event(), Event()

    def stoppable(_path):
        entered.set()
        assert release.wait(3)
        raise InterruptedError("识别已取消")

    with patch("filemind.ui.pages.conversion_page.inspect_input", side_effect=stoppable):
        window.conversion_page.select_file(str(tmp_path / "fixture.txt"))
        deadline = time.monotonic() + 2
        while not entered.is_set() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert entered.is_set()
        window.close()
        assert window._close_pending
        assert window.isVisible()
        release.set()
        wait_for_conversion(window.conversion_page)
    assert not window.isVisible()
