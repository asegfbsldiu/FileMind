"""Exercise real popup, avatar, composer, and conversion selection behavior."""

import time
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QInputMethodEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from filemind.chat_models import ChatConversation, ChatMessage
from filemind.conversion import capabilities as capability_module
from filemind.ui.pages.conversion_page import ConversionPage
from filemind.ui.styles.theme import apply_theme
from filemind.ui.widgets.chat_input import ChatInput
from filemind.ui.widgets.chat_message import ChatMessageBubble
from filemind.ui.widgets.combo_box import ComboItemDelegate, ComboPopup, StyledComboBox
from tools.review_ui import build_review


@pytest.fixture(autouse=True)
def themed_application() -> None:
    """Use the production QSS so popup tests inspect the rendered implementation."""
    apply_theme(QApplication.instance())


def wait_for_idle(page: ConversionPage) -> None:
    deadline = time.monotonic() + 5
    while page.is_busy and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not page.is_busy
    QApplication.processEvents()


@pytest.mark.parametrize("kind", ["model", "preset", "provider", "conversion"])
def test_popup_has_a_single_rounded_surface(tmp_path: Path, kind: str) -> None:
    window, _ = build_review(tmp_path, "orbit")
    window.assistant_page.set_model("deepseek", "DeepSeek", "deepseek-flash", True)
    combos = {
        "model": ("assistant", window.assistant_page.home_composer.model_combo),
        "preset": ("organize", window.organize_page.preset_combo),
        "provider": ("settings", window.settings_page.provider_combo),
        "conversion": ("conversion", window.conversion_page.target_combo),
    }
    page, combo = combos[kind]
    window._show_page(page)
    window.show()
    if kind == "conversion":
        combo.setEnabled(True)
    combo.showPopup()
    QTest.qWait(20)
    popup = combo.view().window()
    assert isinstance(popup, ComboPopup)
    assert isinstance(combo.view().itemDelegate(), ComboItemDelegate)
    assert popup.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert popup.windowFlags() & Qt.WindowType.NoDropShadowWindowHint
    assert popup.grab().toImage().pixelColor(0, 0).alpha() == 0
    # Expanded provider presets scroll inside the existing bounded popup.
    if combo.count() > combo.maxVisibleItems():
        assert combo.view().verticalScrollBar().maximum() > 0
        combo.view().scrollTo(combo.model().index(combo.count() - 1, 0))
        assert combo.view().visualRect(combo.model().index(combo.count() - 1, 0)).intersects(combo.view().viewport().rect())
    else:
        assert combo.view().verticalScrollBar().maximum() == 0
    combo.hidePopup()
    assert not popup.isVisible()
    window.close()


def test_popup_keyboard_selection_escape_and_mouse_activation() -> None:
    combo = StyledComboBox()
    combo.addItems(["文件类型", "修改日期", "课程主题"])
    combo.show()
    changes, activations = [], []
    combo.currentIndexChanged.connect(changes.append)
    combo.activated.connect(activations.append)
    combo.showPopup()
    QTest.keyClick(combo.view(), Qt.Key.Key_Down)
    QTest.keyClick(combo.view(), Qt.Key.Key_Return)
    assert combo.currentIndex() == 1
    assert changes == [1]
    assert activations == [1]
    combo.showPopup()
    QTest.keyClick(combo.view(), Qt.Key.Key_Down)
    QTest.keyClick(combo.view(), Qt.Key.Key_Escape)
    assert combo.currentIndex() == 1
    combo.showPopup()
    view = combo.view()
    index = view.model().index(2, 0)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.visualRect(index).center())
    assert combo.currentIndex() == 2
    assert not view.window().isVisible()
    combo.close()


def test_popup_can_be_opened_from_the_closed_selector_keyboard() -> None:
    combo = StyledComboBox()
    combo.addItems(["DeepSeek", "OpenAI"])
    combo.show()
    combo.setFocus()
    QTest.keyClick(combo, Qt.Key.Key_Space)
    assert combo.view().window().isVisible()
    QTest.keyClick(combo.view(), Qt.Key.Key_Escape)
    assert not combo.view().window().isVisible()
    combo.close()


def test_user_and_assistant_avatars_and_plain_attachment_names() -> None:
    user = ChatMessageBubble(ChatMessage("user", "你好", attachments=("<img src=x>.txt",)))
    assistant = ChatMessageBubble(ChatMessage("assistant", "**你好**"))
    assert not user.avatar.pixmap().isNull()
    assert not assistant.avatar.pixmap().isNull()
    assert user.caption.text() == "你"
    assert assistant.caption.text() == "Orbit"
    assert user.attachment_label.textFormat() == Qt.TextFormat.PlainText
    assert user.bubble.objectName() == "OrbitUserBubble"
    assert assistant.bubble.objectName() == "OrbitAssistantBubble"
    user.close()
    assistant.close()


def test_account_avatar_updates_existing_and_future_user_messages(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "chat")
    avatar = QPixmap(128, 128)
    avatar.fill(QColor("#1C9678"))
    path = tmp_path / "avatar.png"
    assert avatar.save(str(path))
    window._avatar_saved(path)
    bubbles = window.assistant_page.findChildren(ChatMessageBubble)
    user = next(bubble for bubble in bubbles if bubble.is_user)
    assert user.avatar.pixmap().toImage().pixelColor(24, 24).name() == "#1c9678"
    conversation = ChatConversation(messages=(ChatMessage("user", "新消息"),))
    window.assistant_page.set_conversation(conversation)
    user = next(bubble for bubble in window.assistant_page.messages_container.findChildren(ChatMessageBubble)
                if bubble.is_user and bubble.content.toPlainText() == "新消息")
    assert user.caption.text() == window.workspace_store.load().user_name
    assert user.avatar.pixmap().toImage().pixelColor(24, 24).name() == "#1c9678"
    window.close()


def test_chat_enter_respects_ime_composition_and_shift_newline() -> None:
    composer = ChatInput()
    composer.show()
    submissions = []
    composer.send_requested.connect(lambda text, paths: submissions.append(text))
    composer.editor.setPlainText("中文提问")
    composer.editor.inputMethodEvent(QInputMethodEvent("zhong", []))
    QTest.keyClick(composer.editor, Qt.Key.Key_Return)
    assert submissions == []
    composer.editor.inputMethodEvent(QInputMethodEvent())
    composer.editor.setPlainText("中文提问")
    QTest.keyClick(composer.editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert "\n" in composer.editor.toPlainText()
    assert submissions == []
    QTest.keyClick(composer.editor, Qt.Key.Key_Return)
    assert submissions == ["中文提问"]
    composer.close()


def test_repeated_header_settings_removed_but_shortcut_still_opens_settings(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    window.show()
    for key in window.pages:
        window._show_page(key)
        assert not any(button.text() == "模型设置" for button in window.findChildren(QPushButton))
    window._show_page("conversion")
    window.activateWindow()
    QTest.qWait(30)
    assert QApplication.activeWindow() is window
    QTest.keyClick(window, Qt.Key.Key_Comma, Qt.KeyboardModifier.ControlModifier)
    assert window.page_stack.currentWidget() is window.local_settings_page
    window.close()


def test_disabling_or_hiding_selector_dismisses_its_popup() -> None:
    combo = StyledComboBox()
    combo.addItems(["一个选项", "另一个选项"])
    combo.show()
    combo.showPopup()
    combo.setEnabled(False)
    assert not combo.view().window().isVisible()
    combo.setEnabled(True)
    combo.showPopup()
    combo.hide()
    assert not combo.view().window().isVisible()
    combo.close()


def test_conversion_clear_preserves_source_and_output_and_removes_stale_target(tmp_path: Path) -> None:
    page = ConversionPage()
    source = tmp_path / "测试.txt"
    source.write_text("本机转换测试", encoding="utf-8")
    page.select_file(str(source))
    wait_for_idle(page)
    assert page.progress.isHidden()
    assert not page.clear_file_button.isHidden()
    output = tmp_path / "结果.txt"
    page.start_conversion(output)
    wait_for_idle(page)
    page.clear_file_button.click()
    assert page.input_info is None
    assert page.result is None
    assert page.target_combo.currentData() is None
    assert not page.convert_button.isEnabled()
    assert not page.open_result_button.isEnabled()
    assert page.clear_file_button.isHidden()
    assert page.progress.isHidden()
    assert not page.output_label.text()
    assert source.read_text(encoding="utf-8") == "本机转换测试"
    assert output.read_text(encoding="utf-8") == "本机转换测试"
    page.close()


def test_failed_conversion_selection_can_be_cleared(tmp_path: Path) -> None:
    page = ConversionPage()
    page.select_file(str(tmp_path / "missing.txt"))
    wait_for_idle(page)
    assert not page.clear_file_button.isHidden()
    page.clear_file_button.click()
    assert page._selected_path is None
    assert "拖入" in page.file_label.text()
    assert page.file_label.toolTip() == ""
    page.close()


def test_conversion_clear_is_disabled_until_background_job_stops(tmp_path: Path) -> None:
    source = tmp_path / "测试.txt"
    source.write_text("fixture", encoding="utf-8")
    page = ConversionPage()
    entered, release = Event(), Event()
    from filemind.ui.pages import conversion_page
    original = conversion_page.inspect_input

    def slow_inspection(path: Path):
        entered.set()
        assert release.wait(3)
        return original(path)

    with patch.object(conversion_page, "inspect_input", side_effect=slow_inspection):
        page.select_file(str(source))
        try:
            deadline = time.monotonic() + 2
            while not entered.is_set() and time.monotonic() < deadline:
                QTest.qWait(10)
            assert entered.is_set()
            assert not page.clear_file_button.isEnabled()
            page.clear_selection()
            assert page._selected_path == source
            page.cancel()
        finally:
            release.set()
        wait_for_idle(page)
    page.clear_file_button.click()
    assert page._selected_path is None
    assert page.input_info is None
    assert source.read_text(encoding="utf-8") == "fixture"
    page.close()


def test_capability_cards_exclude_unavailable_backends() -> None:
    with patch.object(capability_module, "find_spec", return_value=None), \
            patch.object(capability_module.shutil, "which", return_value=None), \
            patch.object(capability_module, "office_binary", return_value=None):
        cards = capability_module.capabilities()
    assert not {"PDF", "音频", "视频", "Office 排版转换"} & {item.title for item in cards}
    assert all(item.available and item.state != "不可用" for item in cards)
    assert all("尚未" not in item.detail and "未检测" not in item.detail for item in cards)


def test_available_pdf_and_media_are_still_listed() -> None:
    with patch.object(capability_module, "find_spec", return_value=object()), \
            patch.object(capability_module, "office_binary", return_value=None):
        names = {item.title for item in capability_module.capabilities()}
    assert {"PDF", "音频", "视频", "图片", "任意普通文件"} <= names
    assert "Office 排版转换" not in names


def test_existing_cjk_font_does_not_get_registered_again() -> None:
    from filemind.ui.styles import theme
    with patch.object(theme.QFontDatabase, "families", return_value=["Microsoft YaHei UI"]), \
            patch.object(theme.QFontDatabase, "addApplicationFont") as register:
        assert theme._preferred_font_family(QApplication.instance()) == "Microsoft YaHei UI"
    register.assert_not_called()
