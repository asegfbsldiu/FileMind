"""Focused regressions for branch2 navigation, artwork and persisted QSS themes."""

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from filemind.storage.settings import SettingsError
from filemind.ui.styles.icons import PROVIDER_LOGO_FILES, provider_icon
from filemind.ui.styles.theme import COLORS, apply_theme, resolve_appearance
from filemind.ui.widgets.chat_message import ChatMessageBubble
from filemind.ui.widgets.combo_box import StyledComboBox
from tools.review_ui import ReviewCredentials, ReviewSettings, build_review


@pytest.fixture(autouse=True)
def restore_light_theme():
    """Do not leave the shared Qt application dark for other UI tests."""
    existing = {widget for widget in QApplication.topLevelWidgets() if widget.parent() is None}
    yield
    for widget in QApplication.topLevelWidgets():
        if widget.parent() is None and widget not in existing:
            widget.close()
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    apply_theme(QApplication.instance(), "light")


def test_appearance_persistence_preserves_profiles_without_resolving_secrets(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    payload = {"active_provider": "custom", "profiles": {"custom": {"model": "fixture"}},
               "models": [], "future_setting": {"enabled": True}}
    path.write_text(json.dumps(payload), "utf-8")
    store = ReviewSettings(path, tmp_path, ReviewCredentials())
    with patch.object(store, "_load_secret", side_effect=AssertionError("unexpected secret access")):
        store.set_appearance("orange")
        assert store.get_appearance() == "orange"
    assert json.loads(path.read_text("utf-8")) == {**payload, "appearance": "orange"}
    assert ReviewSettings(path, tmp_path, ReviewCredentials()).get_appearance() == "orange"
    with pytest.raises(SettingsError):
        store.set_appearance("unknown")
    assert store.get_appearance() == "orange"


def test_models_have_sidebar_entry_and_general_settings_live_in_account_menu(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "appsettings")
    assert window.nav_buttons["settings"].text() == "模型配置"
    assert "appsettings" not in window.nav_buttons
    assert window.page_stack.currentWidget() is window.local_settings_page
    window.nav_buttons["settings"].click()
    assert window.page_stack.currentWidget() is window.settings_page
    assert window.page_title.text() == "模型配置"
    assert not window.settings_page.findChildren(QLabel, "SettingsSectionTitle")
    window.local_settings_action.trigger()
    assert window.page_stack.currentWidget() is window.local_settings_page
    assert window.local_settings_action.isEnabled()
    assert window.account_button.menu().windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.account_button.menu().testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    requests: list[str] = []
    window.local_auth_requested.connect(requests.append)
    window.local_settings_page.lock_button.click()
    window.local_settings_page.change_password_button.click()
    assert requests == ["unlock", "change"]
    window.close()


@pytest.mark.parametrize("appearance", ["light", "dark", "system", "green", "orange"])
def test_theme_switch_is_live_and_preserves_pending_form_and_composer(tmp_path: Path, appearance: str) -> None:
    window, _ = build_review(tmp_path, "chat")
    page = window.local_settings_page
    window.settings_page.model_edit.setText("unsaved-fixture-model")
    window.assistant_page.chat_composer.editor.setPlainText("未发送的草稿")
    with patch.object(window.settings_store, "load", side_effect=AssertionError("unexpected reload")):
        page.appearance_combo.setCurrentIndex(page.appearance_combo.findData(appearance))
    assert window.settings_store.get_appearance() == appearance
    assert window.settings_page.model_edit.text() == "unsaved-fixture-model"
    assert window.settings_page.has_unsaved_changes
    assert window.assistant_page.chat_composer.editor.toPlainText() == "未发送的草稿"
    assert QApplication.palette().color(QPalette.ColorRole.Window).name().lower() == COLORS["page"].lower()
    assert not re.search(r"__[A-Za-z_]+__", QApplication.instance().styleSheet())
    for bubble in window.assistant_page.findChildren(ChatMessageBubble):
        assert COLORS["surface"] in bubble.content.document().defaultStyleSheet()
    window.close()


def test_failed_theme_save_rolls_back_selection_and_keeps_active_palette(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "appsettings")
    page = window.local_settings_page
    before = dict(COLORS)
    with patch.object(window.settings_store, "set_appearance", side_effect=SettingsError("fixture failure")):
        page.appearance_combo.setCurrentIndex(page.appearance_combo.findData("dark"))
    assert page.appearance_combo.currentData() == "light"
    assert COLORS == before
    assert "保存失败" in page.appearance_status.text()
    window.close()


def test_system_theme_responds_to_qt_color_scheme_changes(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "appsettings")
    hints = QApplication.instance().styleHints()
    with patch.object(hints, "colorScheme", return_value=Qt.ColorScheme.Light):
        window.local_settings_page.appearance_combo.setCurrentIndex(2)
        assert resolve_appearance("system") == "light"
    with patch.object(hints, "colorScheme", return_value=Qt.ColorScheme.Dark):
        hints.colorSchemeChanged.emit(Qt.ColorScheme.Dark)
        assert resolve_appearance("system") == "dark"
        assert COLORS["page"] == "#1E2230"
    assert window.settings_store.get_appearance() == "system"
    window.close()


def test_all_bundled_provider_logos_and_dark_ollama_are_used(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "settings")
    assets = Path(__file__).parents[1] / "filemind/ui/assets/provider_logos"
    assert len(PROVIDER_LOGO_FILES) == 12
    for provider_id, filename in PROVIDER_LOGO_FILES.items():
        expected = QIcon(str(assets / filename)).pixmap(20, 20).toImage()
        assert not expected.isNull()
        assert provider_icon(provider_id).pixmap(20, 20).toImage() == expected
        index = window.settings_page.provider_combo.findData(provider_id)
        assert not window.settings_page.provider_combo.itemIcon(index).isNull()
    window.local_settings_page.appearance_combo.setCurrentIndex(1)
    expected = QIcon(str(assets / "ollama_dark.png")).pixmap(20, 20).toImage()
    assert provider_icon("ollama").pixmap(20, 20).toImage() == expected
    index = window.settings_page.model_selector.provider_combo.findData("ollama")
    assert window.settings_page.model_selector.provider_combo.itemIcon(index).pixmap(20, 20).toImage() == expected
    assert not provider_icon("custom").isNull()
    window.close()


def test_general_settings_uses_current_frameless_popup_and_reloads_theme(tmp_path: Path) -> None:
    first, _ = build_review(tmp_path, "appsettings")
    combo = first.local_settings_page.appearance_combo
    assert isinstance(combo, StyledComboBox)
    combo.setCurrentIndex(combo.findData("green"))
    first.close()
    second, _ = build_review(tmp_path, "appsettings")
    second.show()
    QTest.qWait(25)
    assert second.local_settings_page.appearance_combo.currentData() == "green"
    assert COLORS["primary"] == "#197C50"
    second.local_settings_page.appearance_combo.showPopup()
    assert second.local_settings_page.appearance_combo.view().window().windowFlags() & Qt.WindowType.FramelessWindowHint
    second.local_settings_page.appearance_combo.hidePopup()
    second.close()
