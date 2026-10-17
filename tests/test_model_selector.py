"""Offscreen tests for the multi-model selector widget and settings persistence."""

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from filemind.ai.chat_result import ChatResult, MultiModelResult
from filemind.ai.model_config import ModelConfig
from filemind.storage.settings import SettingsStore
from filemind.ui.main_window import _format_multi_model_answer
from filemind.ui.pages.settings_page import SettingsPage
from filemind.ui.widgets.model_selector import ModelSelector


class _MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, target: str) -> str | None:
        return self.values.get(target)

    def set(self, target: str, value: str) -> None:
        self.values[target] = value

    def delete(self, target: str) -> None:
        self.values.pop(target, None)


def _selector(configs=()):
    widget = ModelSelector()
    widget.set_configs(list(configs))
    return widget


def test_add_appends_and_emits_changed() -> None:
    selector = _selector()
    changed: list[bool] = []
    selector.changed.connect(lambda: changed.append(True))

    selector.provider_combo.setCurrentIndex(selector.provider_combo.findData("openai"))
    selector.model_combo.setEditText("gpt-4o")
    selector._add_current()

    assert [config.identity for config in selector.configs()] == ["openai/gpt-4o"]
    assert selector.configs()[0].enabled
    assert changed
    selector.deleteLater()


def test_empty_and_duplicate_models_are_rejected() -> None:
    selector = _selector([ModelConfig("openai", "gpt-4o")])

    selector.model_combo.setEditText("   ")
    selector._add_current()
    assert len(selector.configs()) == 1

    selector.provider_combo.setCurrentIndex(selector.provider_combo.findData("openai"))
    selector.model_combo.setEditText("gpt-4o")
    selector._add_current()
    assert len(selector.configs()) == 1
    selector.deleteLater()


def test_toggle_move_and_remove_update_the_selection() -> None:
    selector = _selector([ModelConfig("openai", "a"), ModelConfig("openai", "b"),
                          ModelConfig("openai", "c")])

    selector._set_enabled(0, False)
    assert selector.enabled_labels() == ["openai · b", "openai · c"]

    selector._move(0, 1)
    assert [config.model for config in selector.configs()] == ["b", "a", "c"]

    selector._remove(0)
    assert [config.model for config in selector.configs()] == ["a", "c"]
    selector.deleteLater()


def test_reordering_clamps_at_the_edges() -> None:
    selector = _selector([ModelConfig("openai", "a"), ModelConfig("openai", "b")])
    selector._move(0, -1)
    selector._move(1, 1)
    assert [config.model for config in selector.configs()] == ["a", "b"]
    selector.deleteLater()


def test_local_models_fill_the_editable_combo() -> None:
    selector = _selector()
    selector.set_local_models(["qwen2.5:7b", "llama3.2"])
    assert selector.model_combo.count() == 2
    selector.set_local_models([])
    assert "没有可用模型" in selector.add_status.text()
    selector.deleteLater()


def test_refresh_emits_the_ollama_base_url() -> None:
    selector = _selector()
    selector.provider_combo.setCurrentIndex(selector.provider_combo.findData("ollama"))
    received: list[str] = []
    selector.refresh_local_requested.connect(received.append)

    selector._request_local_models()

    assert received and "11434" in received[0]
    selector.deleteLater()


def test_parallel_summary_lists_each_model() -> None:
    result = MultiModelResult((
        ChatResult("openai", "gpt-4o", "好的", 12, None, "主力"),
        ChatResult("ollama", "qwen2.5:7b", "", 30, "无法连接本机 Ollama", "本机"),
    ))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        page = SettingsPage(SettingsStore(root / "settings.json", root, _MemorySecretStore()))
        page.set_parallel_test_result(result)
        assert "1/2" in page.multi_status.text()
        assert "主力" in page.multi_status.toolTip()
        assert "无法连接本机 Ollama" in page.multi_status.toolTip()
        page.deleteLater()


def test_settings_page_saves_and_reloads_the_selection_without_keys() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = SettingsStore(root / "settings.json", root, _MemorySecretStore())
        page = SettingsPage(store)
        page.model_selector.set_configs([
            ModelConfig("openai", "gpt-4o", api_key="must-not-persist"),
            ModelConfig("ollama", "qwen2.5:7b", enabled=False),
        ])
        page.parallel_checkbox.setChecked(True)

        assert page.save_models() is True

        raw = (root / "settings.json").read_text(encoding="utf-8")
        assert "must-not-persist" not in raw
        reloaded = SettingsStore(root / "settings.json", root, _MemorySecretStore())
        assert [config.identity for config in reloaded.load_models()] == \
            ["openai/gpt-4o", "ollama/qwen2.5:7b"]
        assert reloaded.load_models()[1].enabled is False
        assert reloaded.is_parallel_mode_enabled() is True

        reopened = SettingsPage(reloaded)
        assert [config.identity for config in reopened.model_selector.configs()] == \
            ["openai/gpt-4o", "ollama/qwen2.5:7b"]
        assert reopened.parallel_checkbox.isChecked() is True
        page.deleteLater()
        reopened.deleteLater()


def test_format_multi_model_answer_groups_answers_and_errors() -> None:
    result = MultiModelResult((
        ChatResult("openai", "gpt-4o", "第一段", 1234, None, "主力"),
        ChatResult("ollama", "qwen2.5:7b", "", 50, "无法连接本机 Ollama，请确认已运行 ollama serve。", "本机"),
    ))
    text = _format_multi_model_answer(result)

    assert "### 主力" in text and "### 本机" in text
    assert "第一段" in text and "1234 ms" in text
    assert "调用失败" in text and "ollama serve" in text
