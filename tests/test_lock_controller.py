"""Manual lock keeps the existing workspace and revokes remembered access."""

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from filemind.storage.local_lock import LocalLockError
from filemind.ui.startup import LocalLockController, authenticate
from tools.review_ui import build_review


def test_manual_lock_revokes_token_and_restores_same_window(tmp_path: Path, test_protector) -> None:
    """Exercise the revoke flow on every platform using an injected protector."""
    window, _ = build_review(tmp_path, "orbit")
    window.lock_store.protector = test_protector
    window.lock_store.initialize("temporary test password", remember=True)
    assert window.lock_store.try_remembered_unlock()
    controller = LocalLockController(window, window.lock_store)
    window.show()
    with patch("filemind.ui.startup.LocalLockDialog") as dialog:
        dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
        controller.request("unlock")
        assert not window.isVisible()
        loop = QEventLoop()
        controller.worker.signals.completed.connect(loop.quit)
        controller.worker.signals.failed.connect(loop.quit)
        QTimer.singleShot(8000, loop.quit)
        loop.exec()
        QApplication.processEvents()
        assert controller.worker is None
        assert window.isVisible()
        assert not window.lock_store.try_remembered_unlock()
        assert window.page_stack.currentWidget() is window.assistant_page
    window.close()


def test_remember_unlock_is_refused_without_an_os_protector(tmp_path: Path) -> None:
    """macOS and Linux have no DPAPI, so the option must refuse instead of pretending."""
    window, _ = build_review(tmp_path, "orbit")
    window.lock_store.protector = None

    with pytest.raises(LocalLockError, match="无法安全记住解锁"):
        window.lock_store.initialize("temporary test password", remember=True)

    assert not window.lock_store.path.exists()
    assert not window.lock_store.try_remembered_unlock()
    window.close()


def test_account_actions_refuse_to_lock_during_a_file_task(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "orbit")
    requests: list[str] = []
    window.local_auth_requested.connect(requests.append)
    window._active_worker = object()
    with patch("filemind.ui.main_window.QMessageBox.information") as notice:
        window._request_local_auth("unlock")
        assert notice.called
    assert not requests
    window._active_worker = None
    window._request_local_auth("unlock")
    assert requests == ["unlock"]
    window.close()


def test_damaged_local_lock_fails_closed_without_opening_password_setup(tmp_path: Path) -> None:
    window, _ = build_review(tmp_path, "organize")
    with patch.object(window.lock_store, "try_remembered_unlock", side_effect=LocalLockError("损坏")), \
            patch("filemind.ui.startup.LocalLockDialog") as dialog, \
            patch("filemind.ui.startup.QMessageBox.critical") as notice:
        assert not authenticate(window.lock_store)
        dialog.assert_not_called()
        assert notice.called
    window.close()
