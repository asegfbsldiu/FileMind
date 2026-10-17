"""Exercise configuration persistence using only temporary files and fake keys."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QLineEdit, QMessageBox

from filemind.storage.settings import AISettings, SettingsError, SettingsStore
from filemind.ui.pages.settings_page import SettingsPage
from tools import review_ui


class MemorySecretStore:
    """Stand in for durable OS storage without touching Windows credentials."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, target: str) -> str | None:
        return self.values.get(target)

    def set(self, target: str, value: str) -> None:
        self.values[target] = value

    def delete(self, target: str) -> None:
        self.values.pop(target, None)


@pytest.fixture
def configuration_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SettingsStore:
    """Prevent even fallback lookups from reaching a real environment secret."""
    for variable in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SILICONFLOW_API_KEY",
                     "DASHSCOPE_API_KEY", "FILEMIND_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    store = SettingsStore(tmp_path / "settings.json", tmp_path, MemorySecretStore())
    monkeypatch.setattr(store, "_legacy_env_key", lambda _provider: "")
    return store


def test_first_start_uses_defaults_without_claiming_a_connection(configuration_store: SettingsStore) -> None:
    page = SettingsPage(configuration_store)
    assert page.provider_combo.currentData() == "deepseek"
    assert page.base_url_edit.text() == "https://api.deepseek.com"
    assert page.api_key_edit.text() == ""
    assert page.api_key_edit.echoMode() == QLineEdit.EchoMode.Password
    assert "尚未验证" in page.status_label.text()
    assert not page.test_button.isEnabled()
    assert not configuration_store.settings_path.exists()
    page.close()


def test_saved_active_provider_and_fields_survive_restart(configuration_store: SettingsStore) -> None:
    page = SettingsPage(configuration_store)
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("openai"))
    page.base_url_edit.setText("https://example.test/v1")
    page.model_edit.setText("user-selected-model")
    page.api_key_edit.setText("fixture-openai-secret")
    page.timeout_spin.setValue(37)
    changed: list[bool] = []
    page.configuration_changed.connect(lambda: changed.append(True))
    assert page.save_current()
    assert changed == [True]
    assert "尚未验证" in page.status_label.text()
    page.close()

    reloaded_store = SettingsStore(configuration_store.settings_path, configuration_store.project_root,
                                   configuration_store.secret_store)
    reloaded = SettingsPage(reloaded_store)
    assert reloaded.provider_combo.currentData() == "openai"
    assert reloaded.base_url_edit.text() == "https://example.test/v1"
    assert reloaded.model_edit.text() == "user-selected-model"
    assert reloaded.timeout_spin.value() == 37
    assert reloaded.api_key_edit.text() == "fixture-openai-secret"
    assert not reloaded.has_unsaved_changes
    payload = json.loads(configuration_store.settings_path.read_text(encoding="utf-8"))
    assert payload["active_provider"] == "openai"
    assert "fixture-openai-secret" not in json.dumps(payload)
    assert "api_key" not in payload["profiles"]["openai"]
    assert "fixture-openai-secret" not in reloaded.status_label.text()
    assert not configuration_store.local_secrets_path.exists()
    reloaded.close()


def test_provider_switch_reloads_each_saved_profile_and_hides_key(configuration_store: SettingsStore) -> None:
    configuration_store.save(AISettings("deepseek", "https://api.deepseek.com", "saved-deepseek", 21,
                                       "fixture-deepseek-secret"))
    configuration_store.save(AISettings("custom", "https://custom.test/v1", "saved-custom", 31,
                                       "fixture-custom-secret"))
    page = SettingsPage(configuration_store)
    assert page.provider_combo.currentData() == "custom"
    page.show_key_button.click()
    assert page.api_key_edit.echoMode() == QLineEdit.EchoMode.Normal
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("deepseek"))
    assert page.model_edit.text() == "saved-deepseek"
    assert page.api_key_edit.text() == "fixture-deepseek-secret"
    assert page.api_key_edit.echoMode() == QLineEdit.EchoMode.Password
    assert page.show_key_button.text() == "显示"
    assert page.save_current()
    assert configuration_store.load().provider_id == "deepseek"
    assert configuration_store.load("custom").model == "saved-custom"
    page.close()


def test_unsaved_provider_edits_are_not_silently_discarded(
    configuration_store: SettingsStore, monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = SettingsPage(configuration_store)
    page.model_edit.setText("unfinished-model")
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Cancel)
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("openai"))
    assert page.provider_combo.currentData() == "deepseek"
    assert page.model_edit.text() == "unfinished-model"
    assert page.has_unsaved_changes
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Save)
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("openai"))
    assert page.provider_combo.currentData() == "openai"
    assert configuration_store.load("deepseek").model == "unfinished-model"
    assert page.save_current()
    assert configuration_store.load().provider_id == "openai"
    page.close()


def test_empty_key_can_save_but_cannot_claim_connected(configuration_store: SettingsStore) -> None:
    page = SettingsPage(configuration_store)
    assert page.save_current()
    assert "尚未配置 API Key" in page.status_label.text()
    assert "连接成功" not in page.status_label.text()
    assert configuration_store.load().api_key == ""
    assert not page.test_button.isEnabled()
    page._request_test()
    assert page.status_label.text() == "请先填写 API Key。"
    page.close()


def test_save_and_connection_errors_never_echo_the_visible_key(
    configuration_store: SettingsStore, monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = SettingsPage(configuration_store)
    secret = "fixture-secret-must-not-be-displayed"
    page.api_key_edit.setText(secret)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(configuration_store, "save", Mock(side_effect=SettingsError(f"保存失败 {secret}")))
    assert not page.save_current()
    assert secret not in page.status_label.text()
    assert secret not in str(warning.call_args)
    assert page.has_unsaved_changes
    page.set_test_result(False, f"连接失败 {secret}")
    assert secret not in page.status_label.text()
    assert "连接失败" in page.status_label.text()
    page.close()


def test_isolated_review_allows_save_without_secret_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-secret-must-not-be-used")
    monkeypatch.setattr(SettingsStore, "_legacy_env_key", Mock(side_effect=AssertionError("read .env")))
    credentials = review_ui.ReviewCredentials()
    store = review_ui.ReviewSettings(tmp_path / "settings.json", tmp_path, credentials)
    assert store.load().api_key == ""
    page = SettingsPage(store)
    page.api_key_edit.setText("explicit-fixture-secret")
    assert page.save_current()
    assert store.load().api_key == "explicit-fixture-secret"
    assert "验收模式不保存" not in page.status_label.text()
    assert "关闭后清除" in page.status_label.text()
    assert "explicit-fixture-secret" not in store.settings_path.read_text(encoding="utf-8")
    fresh_process = review_ui.ReviewSettings(store.settings_path, tmp_path, review_ui.ReviewCredentials())
    assert fresh_process.load().api_key == ""
    page.close()


def test_review_tool_without_isolation_runs_the_real_application(monkeypatch: pytest.MonkeyPatch) -> None:
    from filemind.ui import startup

    run_application = Mock(return_value=17)
    monkeypatch.setattr(startup, "run_application", run_application)
    monkeypatch.setattr(review_ui, "build_review", Mock(side_effect=AssertionError("temporary UI used")))
    monkeypatch.setattr(review_ui, "QApplication", Mock(side_effect=AssertionError("duplicate Qt app")))
    assert review_ui.main(["--page", "settings"]) == 17
    run_application.assert_called_once_with()


@pytest.mark.parametrize("snapshot", [False, True])
def test_review_isolation_is_explicit_or_implied_by_snapshot(
    snapshot: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from filemind.ui import startup

    application = Mock()
    application.exec.return_value = 0
    widget = Mock()
    widget.grab.return_value.save.return_value = True
    build_review = Mock(return_value=(widget, None))
    monkeypatch.setattr(review_ui, "QApplication", Mock(return_value=application))
    monkeypatch.setattr(review_ui, "apply_theme", Mock())
    monkeypatch.setattr(review_ui, "build_review", build_review)
    monkeypatch.setattr(review_ui.QTimer, "singleShot", lambda _delay, callback: callback())
    monkeypatch.setattr(startup, "run_application", Mock(side_effect=AssertionError("real data used")))
    arguments = ["--page", "settings", "--snapshot", str(tmp_path / "ui.png")] if snapshot else ["--isolated"]
    assert review_ui.main(arguments) == 0
    root, page = build_review.call_args.args
    assert isinstance(root, Path)
    assert page == ("settings" if snapshot else "setup")
    widget.show.assert_called_once_with()
    widget.deleteLater.assert_called_once_with()
    assert not root.exists()
