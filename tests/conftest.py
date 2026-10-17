"""Keep Qt alive until all test-created widgets and workers are disposed."""

import gc
import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Windows CI may spell TEMP with 8.3 aliases while application paths are resolved.
tempfile.tempdir = os.path.realpath(tempfile.gettempdir())

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication


class ReversibleTestProtector:
    """Deterministic test double, never a replacement for production encryption."""

    def protect(self, data: bytes) -> bytes:
        return bytes(value ^ 73 for value in data)

    def unprotect(self, data: bytes) -> bytes:
        return self.protect(data)


@pytest.fixture
def test_protector() -> ReversibleTestProtector:
    """Exercise token lifecycle on every platform without real user credentials."""
    return ReversibleTestProtector()


@pytest.fixture(scope="session", autouse=True)
def qt_application_lifecycle():
    """Destroy views before QApplication, including on assertion failures."""
    application = QApplication.instance() or QApplication([])
    yield application
    assert QThreadPool.globalInstance().waitForDone(8000), "Qt 测试后台任务未正常结束"
    # Qt.Popup windows are top-level surfaces but still owned by their parent.
    # Queueing both for deletion can destroy a combo's popup before hideEvent.
    roots = [widget for widget in QApplication.topLevelWidgets() if widget.parent() is None]
    for widget in roots:
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
    gc.collect()
