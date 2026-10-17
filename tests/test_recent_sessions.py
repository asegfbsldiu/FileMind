"""Date classification and Orbit history with generated local fixtures only."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QWidget

from filemind.chat_models import ChatConversation, ChatMessage
from filemind.core.organization_presets import PRESETS, classify_with_preset
from filemind.core.planner import build_plan
from filemind.models import FileInfo
from filemind.storage.chat_history import MAX_CONVERSATIONS, ChatHistoryStore
from filemind.ui.styles.theme import apply_theme
from filemind.ui.widgets.combo_box import ComboItemDelegate, ComboPopup, StyledComboBox
from filemind.ui.widgets.conversation_row import ConversationList, ConversationRow, conversation_activity
from tools.review_ui import build_review


def populate(store: ChatHistoryStore, count: int) -> list[ChatConversation]:
    """Write disposable conversations without touching the user's local history."""
    base = datetime.now().astimezone() - timedelta(days=90)
    conversations = [ChatConversation(
        conversation_id=f"generated-{index}", title=f"课程学习 {index}" if index % 2 else f"Python 项目 {index}",
        updated_at=(base + timedelta(minutes=index)).isoformat(),
        messages=(ChatMessage("user", "Generated fixture only"),),
    ) for index in range(count)]
    store._write({item.conversation_id: item for item in conversations})
    return conversations


def test_day_preset_uses_full_local_date_and_still_requires_review(tmp_path: Path) -> None:
    source = tmp_path / "generated.txt"
    source.write_text("generated", encoding="utf-8")
    modified = datetime(2026, 2, 3, 15, 4).timestamp()
    info = FileInfo(source, source.stat().st_size, int(modified * 1_000_000_000))
    assert PRESETS[1].key == "modified_day"
    assert "年月日" in PRESETS[1].title
    assert classify_with_preset(info, "modified_day").category == "2026-02-03"
    # Old plans/integrations may still refer to the earlier month-only key.
    assert classify_with_preset(info, "modified_month").category == "2026-02"
    plan = build_plan(tmp_path, [info], lambda item: classify_with_preset(item, "modified_day"))
    assert plan.operations[0].target == tmp_path / "2026-02-03" / source.name
    assert source.exists() and not plan.operations[0].target.exists()


def test_history_retains_more_than_fifty_and_never_filters_by_two_days(tmp_path: Path) -> None:
    store = ChatHistoryStore(tmp_path / "history.json")
    populate(store, 90)
    new = store.create_conversation()
    loaded = ChatHistoryStore(store.history_path).list_conversations()
    assert MAX_CONVERSATIONS == 200
    assert len(loaded) == 91
    assert loaded[0].conversation_id == new.conversation_id
    assert any(item.conversation_id == "generated-0" for item in loaded)


def test_history_cap_keeps_the_newest_two_hundred(tmp_path: Path) -> None:
    store = ChatHistoryStore(tmp_path / "history.json")
    populate(store, 205)
    newest = store.create_conversation()
    loaded = store.list_conversations()
    assert len(loaded) == 200
    assert loaded[0].conversation_id == newest.conversation_id
    assert store.get_conversation("generated-0") is None
    assert store.get_conversation("generated-204") is not None


def test_activity_text_includes_time_message_count_and_old_dates() -> None:
    now = datetime.now().astimezone().replace(hour=12, minute=30, second=0, microsecond=0)
    assert conversation_activity(now.isoformat(), 4, now) == "今天 12:30 · 4 条消息"
    assert "昨天 12:30" in conversation_activity((now - timedelta(days=1)).isoformat(), 2, now)
    older = now - timedelta(days=40)
    assert older.strftime("%m-%d") in conversation_activity(older.isoformat(), 1, now)
    assert "尚未发送消息" in conversation_activity(now.isoformat(), 0, now)
    assert "时间未知" in conversation_activity("invalid", 1, now)


@pytest.mark.parametrize("width,height,minimum_rows", [(1024, 700, 4), (1280, 850, 6)])
def test_recent_list_has_room_for_multiple_rows_and_scrolls_independently(
    tmp_path: Path, width: int, height: int, minimum_rows: int,
) -> None:
    apply_theme(QApplication.instance())
    window, _ = build_review(tmp_path, "orbit")
    populate(window.chat_history, 80)
    window._refresh_conversation_list()
    window.resize(width, height)
    window.show()
    QTest.qWait(60)
    view = window.conversation_list
    viewport = view.viewport().rect()
    complete = [view.visualItemRect(view.item(index)) for index in range(view.count())
                if viewport.contains(view.visualItemRect(view.item(index)))]
    assert len(complete) >= minimum_rows
    assert view.count() == 80 and window.conversation_count.text() == "80"
    assert view.verticalScrollBar().maximum() > 0
    sidebar_width = window.sidebar.width()
    view.scrollToBottom()
    assert viewport.contains(view.visualItemRect(view.item(79)))
    assert window.sidebar.width() == sidebar_width
    assert window.account_button.isVisible()
    window.close()


def test_search_filters_titles_and_restores_sessions_without_network(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    populate(window.chat_history, 20)
    window._refresh_conversation_list()
    window.show()
    window.conversation_search_button.click()
    assert not window.conversation_search.isHidden()
    window.conversation_search.setText("python")
    visible = [window.conversation_list.item(index) for index in range(20)
               if not window.conversation_list.item(index).isHidden()]
    assert len(visible) == 10 and window.conversation_count.text() == "10/20"
    item = visible[0]
    row = window.conversation_list.itemWidget(item)
    row.activated.emit(str(item.data(Qt.ItemDataRole.UserRole)))
    assert window._chat_conversation_id == item.data(Qt.ItemDataRole.UserRole)
    assert window._chat_worker is None
    window.conversation_list.setFocus()
    QTest.keyClick(window.conversation_list, Qt.Key.Key_Down)
    keyboard_selection = window.conversation_list.currentItem()
    assert keyboard_selection is not item
    QTest.keyClick(window.conversation_list, Qt.Key.Key_Return)
    assert window._chat_conversation_id == keyboard_selection.data(Qt.ItemDataRole.UserRole)
    assert window._chat_worker is None
    window.conversation_search.setText("no such title")
    assert window.conversation_empty.isVisible()
    assert "没有匹配" in window.conversation_empty.text()
    window.conversation_search_button.click()
    assert window.conversation_search.isHidden()
    assert window.conversation_search.text() == ""
    assert window.conversation_count.text() == "20"
    assert window.conversation_list.isVisible()
    window.close()


@pytest.mark.parametrize("key,modifiers", [
    (Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
    (Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier),
])
def test_conversation_confirmation_activates_once(
    key: Qt.Key, modifiers: Qt.KeyboardModifier,
) -> None:
    view = ConversationList()
    view.addItems(["First conversation", "Second conversation"])
    view.setCurrentRow(0)
    activated = QSignalSpy(view.itemActivated)
    QTest.keyClick(view, Qt.Key.Key_Down)
    assert view.currentRow() == 1 and activated.count() == 0
    QTest.keyClick(view, key, modifiers)
    assert activated.count() == 1
    assert activated.at(0)[0] is view.currentItem()
    view.currentItem().setHidden(True)
    QTest.keyClick(view, key, modifiers)
    assert activated.count() == 1
    view.close()


def test_action_popup_reuses_model_surface_and_escape_does_not_delete() -> None:
    apply_theme(QApplication.instance())
    row = ConversationRow("fixture", "示例对话")
    row.resize(230, 52)
    row.show()
    requests = QSignalSpy(row.delete_requested)
    row.more_button.click()
    popup = row.action_popup
    assert isinstance(popup, ComboPopup)
    assert isinstance(popup.list_view.itemDelegate(), ComboItemDelegate)
    assert popup.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert popup.windowFlags() & Qt.WindowType.NoDropShadowWindowHint
    assert popup.grab().toImage().pixelColor(0, 0).alpha() == 0
    QTest.keyClick(popup.list_view, Qt.Key.Key_Escape)
    assert not popup.isVisible() and requests.count() == 0
    row.more_button.click()
    QTest.keyClick(popup.list_view, Qt.Key.Key_Return)
    assert requests.count() == 1 and requests.at(0) == ["fixture"]
    assert not popup.isVisible()
    row.close()


def test_row_hiding_closes_action_popup_and_title_is_plain_text() -> None:
    row = ConversationRow("fixture", "<b>not markup</b>")
    row.resize(230, 52)
    row.show()
    row.more_button.click()
    assert row.action_popup.isVisible()
    assert row.title_label.textFormat() == Qt.TextFormat.PlainText
    assert not row.chat_icon.pixmap().isNull()
    row.hide()
    assert not row.action_popup.isVisible()
    row.close()


def test_owner_destruction_disposes_both_popup_types() -> None:
    owner = QWidget()
    layout = QVBoxLayout(owner)
    combo = StyledComboBox()
    combo.addItems(["DeepSeek", "OpenAI"])
    row = ConversationRow("fixture", "生命周期验收")
    layout.addWidget(combo)
    layout.addWidget(row)
    owner.show()
    combo.showPopup()
    combo.hidePopup()
    row.more_button.click()
    disposed_owner = QSignalSpy(owner.destroyed)
    disposed_combo_popup = QSignalSpy(combo.view().window().destroyed)
    disposed_action_popup = QSignalSpy(row.action_popup.destroyed)
    owner.close()
    owner.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert disposed_owner.count() == 1
    assert disposed_combo_popup.count() == 1
    assert disposed_action_popup.count() == 1


def test_delete_popup_still_requires_confirmation_and_only_deletes_selected(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    conversations = populate(window.chat_history, 2)
    window._refresh_conversation_list()
    window.show()
    item = window.conversation_list.item(0)
    selected = str(item.data(Qt.ItemDataRole.UserRole))
    row = window.conversation_list.itemWidget(item)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        row.more_button.click()
        QTest.keyClick(row.action_popup.list_view, Qt.Key.Key_Return)
    assert window.chat_history.get_conversation(selected) is not None
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        row.more_button.click()
        QTest.keyClick(row.action_popup.list_view, Qt.Key.Key_Return)
    assert window.chat_history.get_conversation(selected) is None
    survivor = next(item for item in conversations if item.conversation_id != selected)
    assert window.chat_history.get_conversation(survivor.conversation_id) is not None
    assert window.conversation_count.text() == "1"
    window.close()
