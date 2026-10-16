"""Per-platform application directories for configuration and local data.

Windows keeps the historical split between Roaming (configuration) and Local
(machine-specific data); macOS uses Application Support for both; other systems
follow the XDG base directory specification. The decision logic is a pure function
so every platform branch can be unit tested from any operating system.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping

APP_FOLDER = "FileMind"


def config_dir() -> Path:
    """Return the per-user directory for ordinary, non-secret configuration."""
    return _config_dir(os.name, sys.platform, os.environ, Path.home())


def data_dir() -> Path:
    """Return the per-user directory for machine-specific non-secret data."""
    return _data_dir(os.name, sys.platform, os.environ, Path.home())


def _config_dir(os_name: str, platform: str, environ: Mapping[str, str], home: Path) -> Path:
    if os_name == "nt":
        base = environ.get("APPDATA") or environ.get("LOCALAPPDATA")
        return (Path(base) if base else home / "AppData" / "Roaming") / APP_FOLDER
    if platform == "darwin":
        return _macos_support_dir(home)
    return _xdg_dir(environ, "XDG_CONFIG_HOME", Path(".config"), home)


def _data_dir(os_name: str, platform: str, environ: Mapping[str, str], home: Path) -> Path:
    if os_name == "nt":
        base = environ.get("LOCALAPPDATA") or environ.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / APP_FOLDER
    if platform == "darwin":
        return _macos_support_dir(home)
    return _xdg_dir(environ, "XDG_DATA_HOME", Path(".local") / "share", home)


def _macos_support_dir(home: Path) -> Path:
    return home / "Library" / "Application Support" / APP_FOLDER


def _xdg_dir(environ: Mapping[str, str], variable: str, fallback: Path, home: Path) -> Path:
    """Honour an absolute XDG_* override; ignore relative or empty values."""
    value = environ.get(variable, "")
    if value and Path(value).is_absolute():
        return Path(value) / APP_FOLDER
    return home / fallback / APP_FOLDER
