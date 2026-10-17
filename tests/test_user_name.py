"""Local display-name validation, persistence and account/chat integration."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog

from filemind.chat_models import ChatMessage
from filemind.storage.workspace import WorkspaceError, WorkspaceStore
from filemind.ui.dialogs.user_name import UserNameDialog
from filemind.ui.widgets.chat_message import ChatMessageBubble
from tools.review_ui import build_review


def test_old_workspace_defaults_and_name_preserves_existing_preferences(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    old = {"sidebar_width": 310, "sidebar_collapsed": True, "avatar_file": "avatar.png",
           "organizer_height": 205, "reduced_motion": True}
    path.write_text(json.dumps(old), "utf-8")
    store = WorkspaceStore(path)
    assert store.load().user_name == "本机用户"
    assert store.save_user_name("  Frank 同学  ") == "Frank 同学"
    assert WorkspaceStore(path).load().user_name == "Frank 同学"
    assert json.loads(path.read_text("utf-8")) == {**old, "user_name": "Frank 同学"}
    store.save_layout(275, False)
    store.save_organizer_height(300)
    assert store.load().user_name == "Frank 同学"


@pytest.mark.parametrize("name", ["", "   ", "名" * 33, "用户\n换行", "用户\x00", 123])
def test_invalid_names_do_not_change_saved_name(tmp_path: Path, name: object) -> None:
    store = WorkspaceStore(tmp_path / "workspace.json")
    store.save_user_name("原名")
    before = store.path.read_bytes()
    with pytest.raises(WorkspaceError):
        store.save_user_name(name)
    assert store.path.read_bytes() == before


def test_dialog_validation_enter_save_and_escape_cancel(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.json")
    dialog = UserNameDialog("本机用户", store)
    dialog.show()
    dialog.name_edit.setText(" ")
    assert not dialog.save_button.isEnabled()
    assert "不能为空" in dialog.error_label.text()
    dialog.name_edit.setText("名" * 33)
    assert not dialog.save_button.isEnabled()
    dialog.name_edit.setText("  Frank 🪐  ")
    assert dialog.save_button.isEnabled()
    QTest.keyClick(dialog.name_edit, Qt.Key.Key_Return)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert store.load().user_name == "Frank 🪐"
    second = UserNameDialog("Frank 🪐", store)
    second.show()
    second.name_edit.setText("不应保存")
    QTest.keyClick(second, Qt.Key.Key_Escape)
    assert second.result() == QDialog.DialogCode.Rejected
    assert store.load().user_name == "Frank 🪐"
    dialog.close()
    second.close()


def test_save_failure_keeps_dialog_open_and_old_name(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.json")
    store.save_user_name("原名")
    dialog = UserNameDialog("原名", store)
    dialog.show()
    dialog.name_edit.setText("新名")
    with patch.object(store, "_write", side_effect=WorkspaceError("无法保存界面配置")):
        dialog.save_button.click()
    assert dialog.isVisible()
    assert dialog.user_name == "原名"
    assert store.load().user_name == "原名"
    assert "无法保存" in dialog.error_label.text()
    dialog.save_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert store.load().user_name == "新名"
    dialog.close()


def test_menu_rename_updates_current_future_and_reloaded_chat_without_changing_messages(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "chat")
    conversation = window.chat_history.create_conversation()
    window.chat_history.add_message(conversation.conversation_id, "user", "原始问题")
    window.chat_history.add_message(conversation.conversation_id, "assistant", "生成的界面示例")
    window._select_conversation_id(conversation.conversation_id)
    before = window.chat_history.history_path.read_bytes()
    window.assistant_page.chat_composer.editor.setPlainText("保留草稿")
    user_name = "<Frank> & 用户"

    def save_name(dialog: UserNameDialog) -> int:
        dialog.name_edit.setText(user_name)
        dialog.save_button.click()
        return dialog.result()

    with patch.object(UserNameDialog, "exec", save_name), \
            patch.object(window.settings_store, "load", side_effect=AssertionError("unexpected model load")):
        window.rename_user_action.trigger()
    assert user_name in window.account_button.toolTip()
    assert window.assistant_page.chat_composer.editor.toPlainText() == "保留草稿"
    assert window.chat_history.history_path.read_bytes() == before
    window.assistant_page._append_bubble(ChatMessage("user", "新的界面示例"))
    bubbles = window.assistant_page.messages_container.findChildren(ChatMessageBubble)
    assert all(bubble.caption.text() == (user_name if bubble.is_user else "Orbit") for bubble in bubbles)
    assert all(bubble.caption.textFormat() == Qt.TextFormat.PlainText for bubble in bubbles)
    window.close()
    second, _ = build_review(tmp_path, "orbit")
    assert second.workspace_store.load().user_name == user_name
    assert user_name in second.account_button.accessibleName()
    second._select_conversation_id(conversation.conversation_id)
    assert all(bubble.caption.text() == user_name for bubble in
               second.assistant_page.messages_container.findChildren(ChatMessageBubble) if bubble.is_user)
    second.close()


def test_long_name_is_elided_without_expanding_narrow_sidebar(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "chat")
    name = "这是一个比较长的本机用户名字" * 2
    assert len(name) <= 32
    window.account_button.set_user_name(name)
    window.assistant_page.set_user_name(name)
    window.resize(1024, 700)
    window.show()
    QTest.qWait(35)
    assert 230 <= window.sidebar.width() <= 380
    assert "…" in window.account_button.text()
    assert name in window.account_button.toolTip()
    assert window.assistant_page.messages_container.width() <= window.assistant_page.message_scroll.viewport().width()
    window.close()
