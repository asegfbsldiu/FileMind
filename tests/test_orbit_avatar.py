"""Exercise real Orbit motion, request lifecycle, and local motion preferences."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox

from filemind.ai.chat_service import ChatService
from filemind.ai.openai_compatible import AIServiceError
from filemind.chat_models import ChatConversation, ChatMessage
from filemind.storage.settings import AISettings
from filemind.storage.workspace import WorkspaceError, WorkspaceStore
from filemind.ui.main_window import MainWindow
from filemind.ui.pages.assistant_page import AssistantPage
from filemind.ui.styles.orbit_artwork import AvatarState, orbit_pixmap
from filemind.ui.widgets.chat_message import ChatMessageBubble
from filemind.ui.widgets.orbit_avatar import OrbitAvatar
from tools.review_ui import build_review


def wait_until(predicate: Callable[[], bool], timeout: float = 4.0) -> None:
    """Deliver GUI events until a real worker or animation reaches its endpoint."""
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def page() -> Iterator[AssistantPage]:
    """Use the real page without accessing user data or a model provider."""
    widget = AssistantPage()
    widget.resize(900, 760)
    widget.show()
    QApplication.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()


@pytest.fixture
def window(tmp_path: Path) -> Iterator[MainWindow]:
    """Keep UI, credentials, conversations, and preferences inside tmp_path."""
    _, widget = build_review(tmp_path, "orbit")
    assert widget is not None
    widget.show()
    QApplication.processEvents()
    yield widget
    if widget._chat_worker is not None:
        widget._cancel_chat_task()
        wait_until(lambda: widget._chat_worker is None)
    widget.close()
    widget.deleteLater()


@pytest.mark.parametrize("size,ratio", [(24, 1.0), (32, 1.5), (40, 2.0), (140, 2.0)])
def test_vector_avatar_keeps_transparency_and_high_dpi(size: int, ratio: float) -> None:
    pixmap = orbit_pixmap(size, ratio)
    assert pixmap.width() == round(size * ratio)
    assert pixmap.devicePixelRatio() == ratio
    assert pixmap.toImage().pixelColor(0, 0).alpha() == 0
    assert pixmap.toImage().pixelColor(pixmap.width() // 2, pixmap.height() // 2).alpha() == 255


def test_visible_avatar_moves_and_hidden_avatar_stops() -> None:
    avatar = OrbitAvatar(140, animate_idle=True)
    avatar.show()
    first = avatar.pixmap().toImage()
    assert avatar.is_animating
    # Native timers can start after the first macOS offscreen exposure events.
    wait_until(lambda: avatar.pixmap().toImage() != first, timeout=1.5)
    avatar.hide()
    assert not avatar.is_animating
    avatar.show()
    assert avatar.is_animating
    avatar.showMinimized()
    QApplication.processEvents()
    assert not avatar.is_animating
    avatar.showNormal()
    QApplication.processEvents()
    assert avatar.is_animating
    avatar.close()
    assert not avatar.is_animating


def test_reply_animation_finishes_and_historical_avatar_is_static() -> None:
    avatar = OrbitAvatar(64)
    avatar.show()
    assert not avatar.is_animating
    avatar.set_state("replying")
    assert avatar.is_animating
    assert "回复完成" in avatar.accessibleName()
    wait_until(lambda: avatar.state == "ready", timeout=1.5)
    assert not avatar.is_animating
    avatar.close()


def test_reduced_motion_keeps_the_expression_without_scheduling_frames() -> None:
    avatar = OrbitAvatar(64, animate_idle=True)
    avatar.set_motion_enabled(False)
    avatar.set_state("thinking")
    avatar.show()
    first = avatar.pixmap().toImage()
    QTest.qWait(80)
    assert avatar.pixmap().toImage() == first
    assert avatar.state == "thinking"
    assert "正在思考" in avatar.accessibleName()
    assert not avatar.is_animating
    avatar.set_motion_enabled(True)
    assert avatar.is_animating
    avatar.close()


def test_blink_and_state_expressions_are_visible_in_rendered_frames() -> None:
    open_eyes = orbit_pixmap(128, animated=True, seconds=3.8).toImage()
    blink = orbit_pixmap(128, animated=True, seconds=3.89).toImage()
    assert open_eyes.pixelColor(50, 55).name() == "#ffffff"
    assert blink.pixelColor(50, 55).name() != "#ffffff"
    states: tuple[AvatarState, ...] = ("ready", "thinking", "replying")
    images = [orbit_pixmap(128, state=state).toImage() for state in states]
    assert images[0] != images[1] and images[1] != images[2]


def test_idle_satellite_keeps_moving_after_a_complete_revolution() -> None:
    """Distinguish satellite motion from the existing idle float animation."""
    # Equal float positions and open eyes isolate movement along the orbit.
    frames = [orbit_pixmap(128, state="ready", seconds=seconds, animated=True).toImage()
              for seconds in (0.35, 1.05, 8.75)]
    assert frames[0] != frames[1]
    assert frames[0] != frames[2]
    assert frames[1] != frames[2]


@pytest.mark.parametrize("state", ["ready", "thinking"])
def test_disabled_motion_keeps_the_satellite_stationary(state: AvatarState) -> None:
    """Honor the shared motion preference in both looping avatar states."""
    first = orbit_pixmap(128, state=state, seconds=0.35, animated=False).toImage()
    later = orbit_pixmap(128, state=state, seconds=8.75, animated=False).toImage()
    assert first == later


def test_thinking_follows_its_conversation_and_stops_on_error_or_cancel(page: AssistantPage) -> None:
    first = ChatConversation(messages=(ChatMessage("user", "你好"),))
    other = ChatConversation(messages=(ChatMessage("user", "另一个问题"),))
    page.set_conversation(first)
    page.set_busy(True, first.conversation_id)
    assert page.activity_avatar.state == "thinking"
    assert page.activity_avatar.is_animating
    assert not page.hero_avatar.is_animating
    page.set_conversation(other)
    assert page.activity_avatar.isHidden()
    assert not page.activity_avatar.is_animating
    assert "另一段对话" in page.status_label.text()
    page.set_conversation(first)
    assert page.activity_avatar.is_animating
    page.show_error("测试网络错误", first.conversation_id)
    assert not page.activity_avatar.is_animating
    assert not page.retry_button.isHidden()
    page.set_busy(True, first.conversation_id)
    page.show_stopped(first.conversation_id)
    assert not page.activity_avatar.is_animating
    assert "已停止" in page.status_label.text()


def test_only_the_latest_new_answer_plays_the_reply_animation(page: AssistantPage) -> None:
    conversation = ChatConversation(messages=(ChatMessage("assistant", "之前的回答"),
        ChatMessage("user", "新问题"), ChatMessage("assistant", "新回答")))
    page.set_conversation(conversation)
    QApplication.processEvents()
    bubbles = [page.messages_layout.itemAt(index).widget()
               for index in range(page.messages_layout.count() - 1)]
    assistants = [bubble for bubble in bubbles if isinstance(bubble, ChatMessageBubble) and not bubble.is_user]
    assert all(not bubble.avatar.is_animating for bubble in assistants)
    page.show_reply(conversation.conversation_id)
    assert assistants[-1].avatar.state == "replying"
    assert assistants[-1].avatar.is_animating
    assert not assistants[0].avatar.is_animating
    page.set_conversation(conversation)
    assert all(not avatar.is_animating for avatar in page.messages_container.findChildren(OrbitAvatar)
               if avatar.isVisible())


@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
def test_worker_signals_drive_the_real_avatar_lifecycle(
        window: MainWindow, monkeypatch: pytest.MonkeyPatch, outcome: str) -> None:
    release, entered = Event(), Event()

    def respond(_service: ChatService, _messages: list[dict[str, object]], cancel_event: Event) -> str:
        entered.set()
        if not release.wait(3):
            raise TimeoutError("Test response was not released")
        if cancel_event.is_set():
            raise InterruptedError("测试停止")
        if outcome == "failure":
            raise AIServiceError("测试请求失败")
        return "本地模拟回答"

    monkeypatch.setattr(ChatService, "__init__", lambda _service, _settings: None)
    monkeypatch.setattr(ChatService, "respond", respond)
    conversation = window.chat_history.create_conversation()
    conversation = window.chat_history.add_message(conversation.conversation_id, "user", "测试")
    page = window.assistant_page
    page.set_conversation(conversation)
    settings = AISettings("custom", "https://example.invalid/v1", "fixture", 5, api_key="fixture")
    window._start_chat_request(conversation.conversation_id, settings)
    try:
        wait_until(entered.is_set)
        assert page.activity_avatar.is_animating
        if outcome == "cancel":
            window._cancel_chat_task()
    finally:
        release.set()
    wait_until(lambda: window._chat_worker is None)
    assert not page.activity_avatar.is_animating
    if outcome == "success":
        bubbles = page.messages_container.findChildren(ChatMessageBubble)
        assert any(not bubble.is_user and bubble.avatar.state == "replying" for bubble in bubbles)
    else:
        assert not page.retry_button.isHidden()
        saved = window.chat_history.get_conversation(conversation.conversation_id)
        assert saved is not None and len(saved.messages) == 1


def test_motion_preference_is_shared_persisted_and_used_by_future_messages(
        window: MainWindow) -> None:
    page = window.assistant_page
    controls = page.findChildren(QCheckBox)
    controls[0].setChecked(True)
    assert all(control.isChecked() for control in controls)
    assert not page.hero_avatar.is_animating
    assert WorkspaceStore(window.workspace_store.path).load().reduced_motion
    page.set_conversation(ChatConversation(messages=(ChatMessage("assistant", "历史消息"),)))
    assert all(not avatar.motion_enabled for avatar in page.findChildren(OrbitAvatar))
    payload = json.loads(window.workspace_store.path.read_text(encoding="utf-8"))
    assert payload["reduced_motion"] is True
    controls[1].setChecked(False)
    assert not WorkspaceStore(window.workspace_store.path).load().reduced_motion


def test_preference_save_failure_restores_the_previous_motion_choice(
        window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_save(_reduced: bool) -> None:
        raise WorkspaceError("测试写入失败")

    messages: list[str] = []
    monkeypatch.setattr(window.workspace_store, "save_reduced_motion", fail_save)
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, message: messages.append(message))
    window.assistant_page.findChildren(QCheckBox)[0].setChecked(True)
    assert messages == ["测试写入失败"]
    assert all(avatar.motion_enabled for avatar in window.assistant_page.findChildren(OrbitAvatar))
    assert not any(control.isChecked() for control in window.assistant_page.findChildren(QCheckBox))


def test_legacy_workspace_preferences_default_to_motion_and_preserve_layout(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    path.write_text('{"sidebar_width":305,"organizer_height":220}', encoding="utf-8")
    store = WorkspaceStore(path)
    assert not store.load().reduced_motion
    store.save_reduced_motion(True)
    preferences = WorkspaceStore(path).load()
    assert preferences.reduced_motion
    assert preferences.sidebar_width == 305 and preferences.organizer_height == 220
