"""Integrate teammate features using only generated settings and local test data."""

import json
import time
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from PySide6.QtTest import QTest

from filemind.ai.chat_prompts import ORBIT_SYSTEM_PROMPT
from filemind.ai.chat_result import ChatResult, MultiModelResult
from filemind.ai.model_config import ModelConfig
from filemind.ai.multi_model import run_models
from filemind.ai.openai_compatible import validate_connection_settings
from filemind.ai.response import parse_partial_file_suggestions
from filemind.ai.schemas import file_metadata
from filemind.core.classifier import classify_file
from filemind.core.plan_editor import PlanEditor
from filemind.core.planner import build_plan, name_suffixes
from filemind.core.scanner import scan_files
from filemind.models import FileInfo
from filemind.storage.settings import AISettings
from filemind.ui.main_window import MainWindow, _format_multi_model_answer
from tools.review_ui import ReviewCredentials, ReviewSettings, build_review


def configured_window(root: Path) -> MainWindow:
    window, _ = build_review(root, "orbit")
    store = window.settings_store
    store.save(AISettings("openai", "https://api.openai.com/v1", "test-primary", 10, "fixture-secret"))
    store.save_models([ModelConfig("openai", "test-primary"), ModelConfig("ollama", "test-local")], True)
    window._refresh_assistant_model()
    return window


def wait_for_chat(window: MainWindow) -> None:
    deadline = time.monotonic() + 5
    while window._chat_worker is not None and time.monotonic() < deadline:
        QTest.qWait(10)
    assert window._chat_worker is None


def test_new_model_settings_preserve_profiles_keys_and_empty_selection(tmp_path: Path) -> None:
    credentials = ReviewCredentials()
    store = ReviewSettings(tmp_path / "settings.json", tmp_path, credentials)
    store.save(AISettings("openai", "https://api.openai.com/v1", "existing", 10, "fixture-key"))
    profiles = json.loads(store.settings_path.read_text(encoding="utf-8"))["profiles"]
    secrets = dict(credentials.values)
    store.save_models([ModelConfig("openai", "second", api_key="not-for-json")], True)
    store.set_active_model("openai", "second")
    payload = json.loads(store.settings_path.read_text(encoding="utf-8"))
    assert payload["profiles"]["openai"]["base_url"] == profiles["openai"]["base_url"]
    assert credentials.values == secrets
    assert "not-for-json" not in store.settings_path.read_text(encoding="utf-8")
    assert store.load().model == "second"
    assert store.load().api_key == "fixture-key"
    store.save_models([], False)
    assert store.load_models() == []
    assert store.load().model == "second"


def test_model_key_is_bound_to_the_saved_endpoint(tmp_path: Path) -> None:
    store = ReviewSettings(tmp_path / "settings.json", tmp_path, ReviewCredentials())
    store.save(AISettings("openai", "https://api.openai.com/v1", "m", 10, "fixture-key"))
    assert store.resolve_model(ModelConfig("openai", "m")).api_key == "fixture-key"
    changed = store.resolve_model(ModelConfig("openai", "m", base_url="https://other.example/v1"))
    assert changed.api_key == ""
    assert "fixture-key" not in repr(store.resolve_model(ModelConfig("openai", "m")))


def test_parallel_reply_keeps_system_prompt_and_isolates_errors(tmp_path: Path) -> None:
    window = configured_window(tmp_path)
    captured = {}

    def request(configs, messages, options=None, cancel_event=None):
        captured.update(configs=configs, messages=messages, options=options)
        return MultiModelResult((ChatResult("openai", "test-primary", "Generated answer", 12),
                                 ChatResult("ollama", "test-local", error="本机服务不可用")))

    with patch.object(window, "_confirm_multi_model_privacy", return_value=True), \
            patch("filemind.ui.main_window.run_models", side_effect=request):
        window._send_chat_message("Generated question")
        wait_for_chat(window)
    conversation = window.chat_history.get_conversation(window._chat_conversation_id)
    assert [message.role for message in conversation.messages] == ["user", "assistant"]
    assert captured["options"]["system"] == ORBIT_SYSTEM_PROMPT
    assert captured["messages"] == [{"role": "user", "content": "Generated question"}]
    assert "Generated answer" in conversation.messages[-1].content
    assert "本机服务不可用" in conversation.messages[-1].content
    window.close()


def test_parallel_disclosure_rejection_and_attachments_do_not_send(tmp_path: Path) -> None:
    window = configured_window(tmp_path)
    with patch.object(window, "_confirm_multi_model_privacy", return_value=False), \
            patch("filemind.ui.main_window.run_models") as request:
        window._send_chat_message("Generated question")
        window._send_chat_message("Attachment question", (tmp_path / "not-read.txt",))
    request.assert_not_called()
    assert window.chat_history.list_conversations() == []
    assert "不发送附件" in window.assistant_page.status_label.text()
    window.close()


def test_parallel_total_failure_can_retry_without_duplicating_user_turn(tmp_path: Path) -> None:
    window = configured_window(tmp_path)
    failed = MultiModelResult((ChatResult("openai", "m", error="请求超时"),))
    succeeded = MultiModelResult((ChatResult("openai", "m", content="Generated answer"),))
    with patch.object(window, "_confirm_multi_model_privacy", return_value=True), \
            patch("filemind.ui.main_window.run_models", side_effect=[failed, succeeded]) as request:
        window._send_chat_message("Generated question")
        wait_for_chat(window)
        conversation = window.chat_history.get_conversation(window._chat_conversation_id)
        assert len(conversation.messages) == 1
        assert window.assistant_page.retry_button.isVisibleTo(window.assistant_page)
        window._retry_chat_message()
        wait_for_chat(window)
        assert request.call_count == 2
    conversation = window.chat_history.get_conversation(window._chat_conversation_id)
    assert [message.role for message in conversation.messages] == ["user", "assistant"]
    window.close()


def test_cancelled_parallel_answer_cannot_overwrite_new_session(tmp_path: Path) -> None:
    window = configured_window(tmp_path)
    entered, release = Event(), Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(4)
        return MultiModelResult((ChatResult("openai", "m", "Must be discarded"),))

    with patch.object(window, "_confirm_multi_model_privacy", return_value=True), \
            patch("filemind.ui.main_window.run_models", side_effect=delayed):
        window._send_chat_message("Generated question")
        try:
            deadline = time.monotonic() + 2
            while not entered.is_set() and time.monotonic() < deadline:
                QTest.qWait(10)
            assert entered.is_set()
            original = window._chat_conversation_id
            window._cancel_chat_task()
            window._new_chat()
            current = window._chat_conversation_id
        finally:
            release.set()
        wait_for_chat(window)
    assert current != original
    assert window._chat_conversation_id == current
    assert len(window.chat_history.get_conversation(original).messages) == 1
    assert window.chat_history.get_conversation(current).messages == ()
    window.close()


def test_orbit_picker_switch_preserves_credentials_and_both_composers(tmp_path: Path) -> None:
    window = configured_window(tmp_path)
    window.settings_store.save_models([ModelConfig("openai", "test-primary"), ModelConfig("openai", "second")], False)
    window._refresh_assistant_model()
    combo = window.assistant_page.home_composer.model_combo
    assert combo.count() == 2
    combo.setCurrentIndex(1)
    combo.activated.emit(1)
    assert window.settings_store.load().model == "second"
    assert window.settings_store.load().api_key == "fixture-secret"
    assert window.assistant_page.chat_composer.model_combo.currentData() == "second"
    assert window.assistant_page.home_composer.model_combo.currentData() == "second"
    assert window._chat_worker is None
    window.close()


def test_local_ollama_needs_no_key_but_remote_url_cannot_claim_local() -> None:
    validate_connection_settings(AISettings("ollama", "http://127.0.0.1:11434/v1", "installed", 10))
    with pytest.raises(ValueError, match="本机回环"):
        validate_connection_settings(AISettings("ollama", "https://other.example/v1", "m", 10, local=True))
    with pytest.raises(ValueError, match="API Key"):
        validate_connection_settings(AISettings("openai", "https://api.openai.com/v1", "m", 10, local=True))


def test_partial_suggestions_keep_good_rows_and_hold_unsafe_or_duplicate_rows() -> None:
    files = [FileInfo(Path(name), 10, 1) for name in ("good.txt", "unsafe.txt", "duplicate.txt")]
    expected = {file_metadata(item).file_id: item for item in files}
    identifiers = list(expected)
    rows = [{"file_id": identifiers[0], "category": "资料"},
            {"file_id": identifiers[1], "category": "资料", "target_subdirectory": "../escape"},
            {"file_id": identifiers[2], "category": "资料"},
            {"file_id": identifiers[2], "category": "另一个分类"}]
    suggestions, failures = parse_partial_file_suggestions(json.dumps({"suggestions": rows}), expected, True)
    assert set(suggestions) == {identifiers[0]}
    assert set(failures) == {identifiers[1], identifiers[2]}
    extra = {"file_id": identifiers[0], "category": "资料", "command": "not-accepted"}
    parsed, errors = parse_partial_file_suggestions(json.dumps({"suggestions": [extra]}), expected, True)
    assert parsed == {} and len(errors) == 3


def test_shared_suffix_validation_keeps_multipart_extensions_and_atomic_edits(tmp_path: Path) -> None:
    source = tmp_path / "fixture.TAR.GZ"
    source.write_text("generated", encoding="utf-8")
    editor = PlanEditor(build_plan(tmp_path, scan_files(tmp_path), classify_file))
    before = editor.build()
    assert name_suffixes(source.name) == (".tar", ".gz")
    with pytest.raises(ValueError):
        editor.set_new_name(source, "renamed.gz")
    assert editor.build() == before
    editor.set_new_name(source, "renamed.tar.gz")
    assert editor.build().operations[0].new_name == "renamed.tar.gz"


def test_grouped_answers_fit_local_history_and_key_errors_are_redacted() -> None:
    configs = [ModelConfig("openai", "a", api_key="fixture-secret")]

    def factory(config):
        raise ValueError("invalid fixture-secret")

    result = run_models(configs, [{"role": "user", "content": "generated"}], provider_factory=factory)
    assert "fixture-secret" not in result.results[0].error
    large = MultiModelResult(tuple(ChatResult("openai", f"m-{index}", "x" * 20_000) for index in range(4)))
    answer = _format_multi_model_answer(large)
    assert len(answer) <= 20_000
    assert "已截断" in answer
