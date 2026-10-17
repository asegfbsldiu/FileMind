"""Non-secret avatar and shell preferences use isolated application folders."""

import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from filemind.storage.workspace import WorkspaceError, WorkspaceStore
from tools.review_ui import build_review


def test_layout_persistence_and_bounds(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    store = WorkspaceStore(path)
    store.save_layout(310, True)
    assert WorkspaceStore(path).load().sidebar_width == 310
    assert WorkspaceStore(path).load().sidebar_collapsed
    store.save_layout(1000, False)
    assert store.load().sidebar_width == 380
    store.save_layout(1, False)
    assert store.load().sidebar_width == 230


def test_avatar_is_local_small_and_metadata_free(tmp_path: Path) -> None:
    source = tmp_path / "profile.png"
    image = QImage(320, 180, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.blue)
    image.setText("private original metadata", "do not persist")
    assert image.save(str(source))
    store = WorkspaceStore(tmp_path / "app" / "workspace.json")
    destination = store.save_avatar(source)
    thumbnail = QImage(str(destination))
    assert (thumbnail.width(), thumbnail.height()) == (128, 128)
    assert not thumbnail.textKeys()
    assert WorkspaceStore(store.path).avatar_path() == destination
    config = json.loads(store.path.read_text())
    assert config["avatar_file"] == "avatar.png"
    assert str(source) not in store.path.read_text()
    assert source.exists()


def test_corrupt_config_and_unsupported_avatar_rejected(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    path.write_text("bad JSON")
    with pytest.raises(WorkspaceError):
        WorkspaceStore(path).save_layout(252, False)
    assert path.read_text() == "bad JSON"
    fake_image = tmp_path / "fake.png"
    fake_image.write_text("not image")
    with pytest.raises(WorkspaceError, match="仅支持"):
        WorkspaceStore(tmp_path / "other.json").save_avatar(fake_image)


def test_avatar_arbitrary_paths_ignored(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    path.write_text('{"avatar_file":"../../secret.png"}')
    assert WorkspaceStore(path).avatar_path() is None


def test_sidebar_hide_restore_resize_and_reload(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    window.resize(1024, 700)
    window.show()
    QTest.qWait(30)
    window.workspace_splitter.setSizes([305, 714])
    window._sidebar_moved(305, 1)
    width = window.sidebar.width()
    assert 230 <= width <= 380
    window.sidebar_toggle.click()
    assert window.sidebar.isHidden()
    assert not window.sidebar_toggle.isHidden()
    window._save_workspace_layout()
    saved = window.workspace_store.load()
    assert saved.sidebar_collapsed
    assert abs(saved.sidebar_width - width) <= 2
    window.close()
    # Same isolated store, no user configuration or history access.
    second, _ = build_review(tmp_path, "orbit")
    second.show()
    QTest.qWait(30)
    assert second.sidebar.isHidden()
    second.sidebar_toggle.click()
    QApplication.processEvents()
    assert not second.sidebar.isHidden()
    assert second.conversation_list.height() >= 120
    assert 230 <= second.sidebar.width() <= 380
    second.close()


def test_local_menu_lock_and_avatar_are_real_actions(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    requested = []
    window.local_auth_requested.connect(requested.append)
    actions = window.account_button.menu().actions()
    assert "头像" in actions[0].text()
    lock_action = next(action for action in actions if "登出" in action.text())
    lock_action.trigger()
    assert requested == ["unlock"]
    window.close()


def test_rule_panel_height_survives_window_restart(tmp_path: Path) -> None:
    first, _ = build_review(tmp_path, "empty")
    first.resize(1024, 700)
    first.show()
    QTest.qWait(50)
    first.organize_page.layout_splitter.moveSplitter(210, 1)
    first._save_workspace_layout()
    saved_height = first.workspace_store.load().organizer_height
    assert 140 <= saved_height <= 600
    assert saved_height == first.organize_page.layout_splitter.sizes()[0]
    first.close()
    second, _ = build_review(tmp_path, "empty")
    second.resize(1024, 700)
    second.show()
    QTest.qWait(50)
    assert abs(second.organize_page.layout_splitter.sizes()[0] - saved_height) <= 2
    second.close()
