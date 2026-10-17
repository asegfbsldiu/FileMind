"""Central color, typography, spacing, and Qt stylesheet tokens."""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from filemind.ui.styles.palettes import ACCENTS, DARK, LIGHT

COLORS = dict(LIGHT)
_ACTIVE_THEME = "light"


def appearance_choices() -> tuple[tuple[str, str], ...]:
    """Return the persisted appearance options shared with branch2."""
    return (("light", "浅色"), ("dark", "深色"), ("system", "跟随系统"),
            ("green", "绿色"), ("orange", "橙色"))


def resolve_appearance(appearance: str) -> str:
    """Resolve system mode using Qt's live operating-system color scheme."""
    application = QApplication.instance()
    if appearance == "system":
        dark = application and application.styleHints().colorScheme() == Qt.ColorScheme.Dark
        return "dark" if dark else "light"
    return appearance if appearance in {value for value, _label in appearance_choices()} else "light"


def is_dark_active() -> bool:
    """Whether the current shared palette uses dark surfaces."""
    return _ACTIVE_THEME == "dark"


def resolve_qss(stylesheet: str) -> str:
    """Resolve semantic color tokens for application and local QSS."""
    for name, color in COLORS.items():
        stylesheet = stylesheet.replace(f"__{name}__", color)
    return stylesheet


def apply_theme(application: QApplication, appearance: str = "light") -> None:
    """Apply the shared FileMind palette and polished Fusion widget theme."""
    global _ACTIVE_THEME
    _ACTIVE_THEME = resolve_appearance(appearance)
    application.setProperty("filemindAppearance", appearance)
    if not application.property("filemindSystemThemeConnected"):
        application.styleHints().colorSchemeChanged.connect(lambda _scheme: _follow_system(application))
        application.setProperty("filemindSystemThemeConnected", True)
    if (application.property("filemindAppliedTheme") == _ACTIVE_THEME
            and application.property("filemindAppliedQss") == application.styleSheet()):
        return
    COLORS.clear()
    COLORS.update(DARK if is_dark_active() else LIGHT)
    COLORS.update(ACCENTS.get(_ACTIVE_THEME, {}))
    if application.style().objectName().lower() != "fusion":
        application.setStyle("Fusion")
    _apply_palette(application)
    font_family = _preferred_font_family(application)
    application.setFont(QFont(font_family, 10))
    stylesheet = _stylesheet(font_family)
    application.setStyleSheet(stylesheet)
    application.setProperty("filemindAppliedTheme", _ACTIVE_THEME)
    application.setProperty("filemindAppliedQss", stylesheet)


def _follow_system(application: QApplication) -> None:
    if application.property("filemindAppearance") == "system":
        apply_theme(application, "system")


def _apply_palette(application: QApplication) -> None:
    palette = QPalette()
    roles = {"Window": "page", "WindowText": "text", "Base": "input_bg",
             "AlternateBase": "table_alt", "Text": "text", "Button": "card",
             "ButtonText": "text", "Highlight": "selection", "HighlightedText": "text",
             "ToolTipBase": "tooltip_bg", "ToolTipText": "tooltip_text",
             "Link": "link", "PlaceholderText": "placeholder"}
    for name, token in roles.items():
        palette.setColor(getattr(QPalette.ColorRole, name), QColor(COLORS[token]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS["muted_soft"]))
    application.setPalette(palette)


def _preferred_font_family(application: QApplication) -> str:
    """Choose an installed Chinese-capable font before Latin-only fallbacks."""
    available = set(QFontDatabase.families())
    preferred = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB",
                 "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC", "WenQuanYi Zen Hei",
                 "DengXian", "SimSun")
    for candidate in preferred:
        if candidate in available:
            return candidate
    for font_path in _candidate_font_files():
        if font_path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id >= 0:
                available.update(QFontDatabase.applicationFontFamilies(font_id))
            for candidate in preferred:
                if candidate in available:
                    return candidate
    for candidate in ("Segoe UI", "Helvetica Neue", "Noto Sans", "DejaVu Sans"):
        if candidate in available:
            return candidate
    return application.font().family()


def _candidate_font_files() -> tuple[Path, ...]:
    """Locate optional CJK fonts without re-registering installed families."""
    if os.name == "nt":
        root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        return tuple(root / name for name in ("msyh.ttc", "Noto Sans SC (TrueType).otf", "Deng.ttf", "simsun.ttc"))
    if sys.platform == "darwin":
        return (Path("/System/Library/Fonts/PingFang.ttc"),
                Path("/System/Library/Fonts/STHeiti Light.ttc"),
                Path("/Library/Fonts/Arial Unicode.ttf"))
    return (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            Path("/usr/share/fonts/truetype/arphic/uming.ttc"))


def _stylesheet(font_family: str) -> str:
    """Return the shared QSS using an installed font family."""
    stylesheet = "\n".join(Path(__file__).with_name(name).read_text(encoding="utf-8")
                            for name in ("base.qss", "orbit.qss", "conversion.qss", "models.qss"))
    assets = (Path(__file__).parent.parent / "assets").as_posix()
    stylesheet = stylesheet.replace("__FONT_FAMILY__", font_family).replace("__ASSETS__", assets)
    return resolve_qss(stylesheet)
