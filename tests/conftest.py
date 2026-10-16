"""Keep Qt alive until all test-created widgets and workers are disposed."""

import gc
import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Windows 的 TEMP/TMP 可能是 8.3 短路径（例如 C:\Users\RUNNER~1\...），而应用内部会用
# Path.resolve() 规范化成长路径，于是同一个目录在断言里出现两种写法。把测试临时目录的
# 基准统一为规范化路径，断言仍然比较同一个真实目录，强度不变。
tempfile.tempdir = os.path.realpath(tempfile.gettempdir())

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication


class ReversibleTestProtector:
    """Deterministic stand-in for an OS token protector; never a real cipher."""

    __test__ = False

    def protect(self, data: bytes) -> bytes:
        return bytes(value ^ 73 for value in data)

    def unprotect(self, data: bytes) -> bytes:
        return self.protect(data)


@pytest.fixture
def test_protector() -> ReversibleTestProtector:
    """Let remember-unlock flows run on platforms without DPAPI."""
    return ReversibleTestProtector()


@pytest.fixture(scope="session", autouse=True)
def qt_application_lifecycle():
    """Destroy views before QApplication, including on assertion failures."""
    application = QApplication.instance() or QApplication([])
    yield application
    assert QThreadPool.globalInstance().waitForDone(8000), "Qt 测试后台任务未正常结束"
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
    gc.collect()
