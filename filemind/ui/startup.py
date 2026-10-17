"""Authenticate locally before constructing pages that load application data."""

import sys

from PySide6.QtCore import QObject, Qt, QThreadPool
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from filemind.storage.local_lock import LocalLockError, LocalLockStore
from filemind.storage.settings import SettingsError, SettingsStore
from filemind.ui.branding import configure_application_identity
from filemind.ui.dialogs.local_lock import LocalLockDialog
from filemind.ui.main_window import MainWindow
from filemind.ui.styles.theme import apply_theme
from filemind.ui.workers import TaskWorker


def authenticate(store: LocalLockStore) -> bool:
    """Do not construct the main window until setup or unlock has succeeded."""
    try:
        if store.try_remembered_unlock():
            return True
        return LocalLockDialog(store).exec() == QDialog.DialogCode.Accepted
    except (LocalLockError, OSError) as error:
        QMessageBox.critical(None, "无法解锁 FileMind", str(error))
        return False


class LocalLockController(QObject):
    """Coordinate manual locking without recreating the current workspace."""

    def __init__(self, window: MainWindow, store: LocalLockStore) -> None:
        super().__init__(window)
        self.window, self.store = window, store
        self.worker: TaskWorker | None = None
        window.local_auth_requested.connect(self.request)

    def request(self, mode: str) -> None:
        """Changing a password is modal; locking also revokes remembered access."""
        if self.worker is not None:
            return
        if mode == "change":
            LocalLockDialog(self.store, "change", self.window).exec()
            return
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self.window.hide()
        self.worker = TaskWorker(lambda _progress, _cancel: self.store.revoke_remembered_unlock())
        self.worker.signals.completed.connect(self._show_unlock)
        self.worker.signals.failed.connect(self._failed)
        QThreadPool.globalInstance().start(self.worker)

    def _show_unlock(self, _result: object) -> None:
        self.worker = None
        result = LocalLockDialog(self.store, "unlock").exec()
        if result == QDialog.DialogCode.Accepted:
            self.window.show()
            self.window.activateWindow()
        else:
            self.window.close()
            QApplication.instance().quit()
        QApplication.instance().setQuitOnLastWindowClosed(True)

    def _failed(self, _message: str) -> None:
        self.worker = None
        self.window.show()
        QApplication.instance().setQuitOnLastWindowClosed(True)
        QMessageBox.warning(self.window, "锁定失败", "无法安全撤销记住解锁，请检查本机配置目录权限。")


def run_application() -> int:
    """Run the single official Qt Widgets application behind a local lock."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    application = QApplication(sys.argv)
    configure_application_identity(application)
    application.setQuitOnLastWindowClosed(False)
    settings_store = SettingsStore()
    try:
        appearance = settings_store.get_appearance()
    except (SettingsError, OSError, ValueError):
        appearance = "light"
    apply_theme(application, appearance)
    store = LocalLockStore()
    if not authenticate(store):
        return 0
    window = MainWindow(settings_store=settings_store, lock_store=store)
    window.lock_controller = LocalLockController(window, store)
    window.show()
    application.setQuitOnLastWindowClosed(True)
    return application.exec()
