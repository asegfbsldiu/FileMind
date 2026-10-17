"""Application identity and offline artwork shared by source and frozen builds."""

import ctypes
import logging
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from filemind import __version__


APP_USER_MODEL_ID = "FileMind.Desktop"
ASSETS_DIRECTORY = Path(__file__).parent / "assets"
LOGGER = logging.getLogger(__name__)


def application_icon() -> QIcon:
    """Load the bundled multi-resolution icon, falling back to the PNG artwork."""
    for name in ("FileMind_AppIcon.ico", "FileMind_AppIcon.png"):
        icon = QIcon(str(ASSETS_DIRECTORY / name))
        if not icon.isNull():
            return icon
    LOGGER.warning("FileMind application icon could not be loaded.")
    return QIcon()


def configure_application_identity(application: QApplication) -> None:
    """Set the app-wide icon before the lock screen or main window is shown."""
    application.setApplicationName("FileMind")
    application.setApplicationDisplayName("FileMind")
    application.setApplicationVersion(__version__)
    application.setWindowIcon(application_icon())
    _set_windows_app_id()


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        if set_app_id(APP_USER_MODEL_ID) < 0:
            LOGGER.warning("Windows could not set the FileMind taskbar identity.")
    except (AttributeError, OSError):
        LOGGER.warning("Windows taskbar identity is unavailable.")
