"""Small consistent SVG line icons rendered through QtSvg."""

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from filemind.ui.styles.theme import COLORS, is_dark_active


PROVIDER_LOGO_FILES = {name: f"{name}.png" for name in (
    "dashscope", "deepseek", "doubao", "hunyuan", "kimi", "ollama", "openai",
    "qwen", "siliconflow", "volcengine", "wenxin", "zhipu",
)}

PROVIDER_MARKS = {
    "deepseek": ("#4569E8", '<path d="M5 13c2-6 10-7 13-2 2 4-2 8-6 7-2-.4-3-2-3-4"/><path d="M5 13 3 9m2 4 4-1m7-5 2-3m-2 3 4 1"/><circle cx="12" cy="13" r="1" fill="#4569E8" stroke="none"/>'),
    "openai": ("#243449", '<path d="M12 3.5a4 4 0 0 1 6.9 2.7v2.1a4 4 0 0 1 1.7 6.8l-1.8 1.1a4 4 0 0 1-4.7 5.3l-1.9-1a4 4 0 0 1-6.9-2.7v-2.1a4 4 0 0 1-1.7-6.8l1.8-1.1a4 4 0 0 1 4.7-5.3Z"/><path d="m8 8 8 8m-8 0 8-8m-8-1v10m8-10v10"/>'),
    "siliconflow": ("#6C55D9", '<path d="M5 7h10a3 3 0 0 1 0 6H9a3 3 0 0 0 0 6h10"/><path d="M7 4 4 7l3 3m10 4 3 3-3 3"/>'),
    "dashscope": ("#7251D2", '<path d="M5 19V5h8a5 5 0 0 1 0 10H5m8-3 6 7"/><path d="m17 5 2 2-2 2"/>'),
    "custom": ("#65748B", '<circle cx="12" cy="12" r="8.5"/><path d="M3.8 12h16.4M12 3.5a14 14 0 0 1 0 17M12 3.5a14 14 0 0 0 0 17"/>'),
}


ICON_PATHS = {
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6m4-6v6"/>',
    "orbit": '<circle cx="12" cy="12" r="5"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-32 12 12)"/><circle cx="18.5" cy="5.5" r="1.2" fill="currentColor" stroke="none"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16m-3-8h.01"/>',
    "convert": '<path d="M4 7h14l-3-3m3 3-3 3M20 17H6l3 3m-3-3 3-3"/>',
    "image_file": '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="2"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
    "sheet_file": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 9h16M4 15h16M10 9v12"/>',
    "folder_plan": '<path fill="currentColor" fill-opacity=".13" d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 9h18"/>',
    "folder_open": '<path d="M3 11V7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v2"/><path fill="currentColor" fill-opacity=".16" d="M3 11h18l-2 9H5Z"/>',
    "warning": '<path d="m12 3 10 18H2Z"/><path d="M12 9v5m0 3h.01"/>',
    "lock": '<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/>',
    "chevron": '<path d="m9 5 7 7-7 7"/>',
    "organize": '<path d="M4 7h16M4 12h10M4 17h7"/><path d="m17 14 3 3-3 3"/>',
    "assistant": '<path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8 8 0 0 1-3.3-.7L4 20l1.2-3.5A7.2 7.2 0 0 1 4 12c0-4.2 3.6-7.5 8-7.5s8 2.8 8 7Z"/><path d="M8 12h.01M12 12h.01M16 12h.01"/>',
    "history": '<path d="M3 12a9 9 0 1 0 2.64-6.36L3 8"/><path d="M3 4v4h4M12 7v5l3 2"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.6a8 8 0 0 1-1.7 1l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.7-1l-1.7.6-1.4-2.4L5.3 15a8 8 0 0 1 0-2l-1.4-1.1 1.4-2.4 1.7.6a8 8 0 0 1 1.7-1L9 7.3h2.8l.3 1.8a8 8 0 0 1 1.7 1l1.7-.6 1.4 2.4-1.4 1.1a8 8 0 0 1-.1 2Z"/>',
    "folder": '<path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H10l2 2h7.5A1.5 1.5 0 0 1 21 9.5v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5Z"/>',
    "scan": '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><path d="M8 12h8M8 15h5M8 9h8"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h9a7 7 0 0 1 0 14h-2"/>',
    "spark": '<path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5Z"/><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7Z"/>',
    "learning": '<path d="m2 9 10-5 10 5-10 5L2 9Z"/><path d="M6 11v5c3.5 3 8.5 3 12 0v-5m4-2v7"/>',
    "code": '<path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-12-2 14"/>',
    "project": '<rect x="5" y="4" width="14" height="16" rx="2"/><path d="M9 9h6m-6 4h6m-6 4h4"/>',
    "document": '<path d="M7 3h7l5 5v13H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 3v6h5m-9 4h5m-5 4h5"/>',
}


def svg_icon(name: str, color: str | None = None, size: int = 22) -> QIcon:
    """Create a scalable icon for one of the known FileMind symbols."""
    color = color or COLORS["muted"]
    paths = ICON_PATHS[name]
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def provider_icon(provider_id: str, size: int = 20) -> QIcon:
    """Use bundled provider artwork, with a visible fallback for missing assets."""
    logo_file = PROVIDER_LOGO_FILES.get(provider_id)
    if logo_file:
        if provider_id == "ollama" and is_dark_active():
            logo_file = "ollama_dark.png"
        logo_path = Path(__file__).parent.parent / "assets" / "provider_logos" / logo_file
        if logo_path.is_file():
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                return QIcon(pixmap)
    color, paths = PROVIDER_MARKS.get(provider_id, PROVIDER_MARKS["custom"])
    if provider_id not in PROVIDER_LOGO_FILES:
        color = COLORS["muted"]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" '
           f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" '
           f'stroke-linecap="round" stroke-linejoin="round">{paths}</svg>')
    pixmap = QPixmap(max(size, 64), max(size, 64))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter)
    painter.end()
    return QIcon(pixmap)


def file_type_icon(path: Path) -> QIcon:
    """Choose an offline vector hint from the filename without opening files."""
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".svg"}:
        return svg_icon("image_file", "#7C5CE7")
    if suffix in {".csv", ".xlsx", ".xls", ".ods"}:
        return svg_icon("sheet_file", "#278566")
    if suffix in {".py", ".c", ".h", ".cpp", ".java", ".js", ".ts", ".json", ".sql"}:
        return svg_icon("code", "#4F6BED")
    return svg_icon("document")
