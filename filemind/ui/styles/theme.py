"""Central color, typography, spacing, and Qt stylesheet tokens."""

import os
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication


COLORS = {
    "page": "#F5F7FB",
    "card": "#FFFFFF",
    "text": "#172033",
    "muted": "#64748B",
    "primary": "#4F6BED",
    "primary_hover": "#3F5DDD",
    "primary_soft": "#EEF2FF",
    "purple": "#7C5CE7",
    "purple_soft": "#F8F6FF",
    "purple_border": "#E7E1FB",
    "border": "#E5EAF2",
    "success": "#16A34A",
    "warning": "#D97706",
    "danger": "#DC2626",
    "sidebar": "#FBFCFF",
}


def apply_theme(application: QApplication) -> None:
    """Apply the shared FileMind palette and polished Fusion widget theme."""
    application.setStyle("Fusion")
    font_family = _preferred_font_family(application)
    application.setFont(QFont(font_family, 10))
    application.setStyleSheet(_stylesheet(font_family))


def _preferred_font_family(application: QApplication) -> str:
    """Choose an installed Chinese-capable font before Latin-only fallbacks."""
    available = set(QFontDatabase.families())
    for font_path in _candidate_font_files():
        if font_path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id >= 0:
                available.update(QFontDatabase.applicationFontFamilies(font_id))
    for candidate in _FONT_FAMILIES:
        if candidate in available:
            return candidate
    return application.font().family()


_FONT_FAMILIES = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB",
                  "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC", "WenQuanYi Zen Hei",
                  "DengXian", "SimSun", "Segoe UI", "Helvetica Neue", "Noto Sans", "DejaVu Sans")


def _candidate_font_files() -> tuple[Path, ...]:
    """List per-platform font files that carry Simplified Chinese glyphs."""
    if os.name == "nt":
        root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        return tuple(root / name for name in ("msyh.ttc", "Deng.ttf", "simsun.ttc"))
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
    stylesheet = """
    QWidget { color: #172033; font-family: "__FONT_FAMILY__"; font-size: 10pt; }
    QMainWindow, QWidget#PageRoot { background: #F5F7FB; }
    QDialog#LocalLockDialog { background: #F5F7FB; }
    QFrame#LockPoster { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #F0E9FF,stop:1 #EEF4FF); border: 1px solid #E0E7FF; border-radius: 20px; }
    QFrame#LockCard { background: #FFFFFF; border: 1px solid #E5EAF2; border-radius: 20px; }
    QLabel#LockTitle { font-size: 21pt; font-weight: 700; }
    QLabel#LockHeadline { font-size: 26pt; font-weight: 700; color: #263B75; }
    QLabel#LockError { color: #B45309; }
    QPushButton#LockLink { border: 0; color: #4F6BED; background: transparent; padding: 8px; }
    QPushButton#LockLink:hover { background: #EEF2FF; }
    QPushButton#LocalAccountButton { text-align: left; background: transparent;
        border: 1px solid #E5EAF2; border-radius: 10px; padding: 11px 12px; }
    QPushButton#LocalAccountButton:hover { background: #EEF2FF; border-color: #CDD6FA; }
    QPushButton#LocalAccountButton::menu-indicator { subcontrol-origin: padding;
        subcontrol-position: right center; right: 12px; }
    QPushButton:focus { border-color: #4F6BED; }
    QMenu { background: #FFFFFF; border: 1px solid #E5EAF2; border-radius: 9px; padding: 5px; }
    QMenu::item { padding: 8px 20px; border-radius: 5px; }
    QMenu::item:selected { color: #4F6BED; background: #EEF2FF; }
    QFrame#Sidebar { background: #FBFCFF; border-right: 1px solid #E5EAF2; }
    QSplitter#WorkspaceSplitter::handle { background: #F0F2F8; }
    QSplitter#WorkspaceSplitter::handle:hover { background: #D8CEF7; }
    QSplitter#OrganizerSplitter::handle { background: #E8ECF5; border-radius: 4px; margin: 1px 55px; }
    QSplitter#OrganizerSplitter::handle:hover { background: #BEB2ED; }
    QWidget#OrganizerEmpty { background: #FFFFFF; border-radius: 12px; }
    QLabel#EmptyTitle { font-size: 16pt; font-weight: 650; color: #28354C; }
    QFrame#CapabilityTile { border: 1px solid #E1E7F0; border-radius: 12px; }
    QFrame#CapabilityTile[tint="blue"] { background: #EAF2FF; border-color: #D8E6FA; }
    QFrame#CapabilityTile[tint="mint"] { background: #E7F6F0; border-color: #D5ECE1; }
    QFrame#CapabilityTile[tint="lavender"] { background: #F1EBFF; border-color: #E6DCF8; }
    QFrame#CapabilityTile[tint="amber"] { background: #FFF5D8; border-color: #EFE2B9; }
    QLabel#TileTitle { font-weight: 650; color: #34435E; }
    QLabel#CapabilityDetail { color: #53647E; font-size: 9pt; }
    QLabel#CapabilityState { color: #52637E; font-size: 8pt; padding: 2px 4px; }
    QTabWidget#OrganizationWorkspace::pane { background: #FFFFFF; border: 1px solid #E5EAF2; border-radius: 10px; top: -1px; }
    QTabWidget#OrganizationWorkspace QTabBar::tab { background: #F2F4FA; color: #64748B;
        border: 1px solid #E5EAF2; border-bottom: 0; padding: 9px 15px;
        border-top-left-radius: 9px; border-top-right-radius: 9px; margin-right: 5px; }
    QTabWidget#OrganizationWorkspace QTabBar::tab:selected { background: #FFFFFF; color: #4F6BED; font-weight: 600; }
    QLabel#SummaryValue { color: #263B75; font-weight: 650; }
    QLabel#ModelStatusBadge { color: #6548C5; font-size: 9pt; }
    QFrame#ConversionDropZone { background: #F7F4FF; border: 1px dashed #C6B8EC; border-radius: 18px; }
    QLabel#ConversionTitle { font-size: 18pt; font-weight: 700; }
    QLabel#ConversionSteps { color: #7255BD; background: #F2EDFF; border-radius: 10px; padding: 10px 14px; }
    QFrame[card="true"] { background: #FFFFFF; border: 1px solid #E5EAF2; border-radius: 14px; }
    QLabel#PageTitle { font-size: 22pt; font-weight: 700; color: #172033; }
    QLabel#PageSubtitle, QLabel#Muted { color: #64748B; }
    QLabel#BrandName { font-size: 18pt; font-weight: 700; color: #172033; }
    QLabel#BrandCaption { color: #64748B; font-size: 9pt; }
    QPushButton { background: #FFFFFF; border: 1px solid #E5EAF2; border-radius: 9px;
                  padding: 9px 14px; color: #26334B; }
    QPushButton:hover { background: #F8FAFF; border-color: #CBD5E1; }
    QPushButton:pressed { background: #EEF2FF; }
    QPushButton:disabled { color: #9AA6B8; background: #F1F4F8; border-color: #E5EAF2; }
    QPushButton#PrimaryButton { background: #4F6BED; color: white; border: 1px solid #4F6BED;
                                font-weight: 600; padding: 10px 18px; }
    QPushButton#PrimaryButton:hover { background: #3F5DDD; border-color: #3F5DDD; }
    QPushButton#PrimaryButton:disabled { color: #9AA6B8; background: #F1F4F8; border-color: #E5EAF2; }
    QToolButton#ClearDirectoryButton { color: #64748B; background: #F8FAFC; border: 1px solid #E5EAF2;
                                      border-radius: 15px; min-width: 30px; max-width: 30px;
                                      min-height: 30px; max-height: 30px; padding: 0; font-size: 16pt; }
    QToolButton#ClearDirectoryButton:hover { color: #DC2626; background: #FEF2F2; border-color: #FECACA; }
    QToolButton#ClearDirectoryButton:disabled { color: #CBD5E1; background: #F8FAFC; }
    QDialog#PlanPreviewDialog { background: #F5F7FB; }
    QScrollArea#OrganizerContentScroll { background: transparent; border: 0; }
    QScrollArea#OrganizerContentScroll > QWidget > QWidget { background: transparent; }
    QScrollArea#ConversionScroll, QScrollArea#ConversionScroll > QWidget > QWidget { background: transparent; border: 0; }
    QLabel#PreviewTitle { color: #172033; font-size: 16pt; font-weight: 700; }
    QLabel#PreviewNotice { color: #354F82; background: #EEF2FF; border: 1px solid #DFE7FA;
                           border-radius: 10px; padding: 9px 12px; }
    QLabel#PreviewNotice[hasWarnings="true"] { color: #9A5B05; background: #FFF7E6; border-color: #F4D89C; }
    QTreeWidget#PlanTargetTree { background: #FFFFFF; border: 1px solid #E5EAF2; border-radius: 10px;
                                 outline: 0; padding: 6px; }
    QTreeWidget#PlanTargetTree::item { min-height: 28px; padding: 3px 4px; border-radius: 6px; }
    QTreeWidget#PlanTargetTree::item:selected { color: #4F6BED; background: #EEF2FF; }
    QTreeWidget#PlanTargetTree::item:hover { background: #F5F7FB; }
    QTableView#PlanDetailTable { border: 1px solid #E5EAF2; border-radius: 10px; }
    QFrame#PlanChangeDetails { background: #FFFFFF; border: 1px solid #E5EAF2; border-radius: 10px; }
    QPushButton#NavButton { text-align: left; padding: 11px 12px; border: 0; background: transparent;
                            color: #64748B; font-weight: 500; }
    QPushButton#NavButton:hover { background: #F1F4FA; color: #172033; }
    QPushButton#NavButton[active="true"] { background: #EEF2FF; color: #4F6BED; font-weight: 600; }
    QPushButton#NavButton[active="true"][orbit="true"] { background: #EEE8FF; color: #7751D8; }
    QListWidget#OrbitRecentList { background: transparent; border: 0; outline: 0; }
    QListWidget#OrbitRecentList::item { background: transparent; border: 0; padding: 0; }
    QFrame#OrbitConversationRow { background: transparent; border: 1px solid transparent;
                                  border-radius: 10px; }
    QFrame#OrbitConversationRow:hover { background: #F6F5FF; border-color: #EEEBFA; }
    QFrame#OrbitConversationRow[selected="true"] { background: #EFECFF; border-color: #E9E3FF; }
    QLabel#OrbitConversationTitle { color: #515B73; background: transparent; border: 0; }
    QFrame#OrbitConversationRow[selected="true"] QLabel#OrbitConversationTitle { color: #6548C5; font-weight: 600; }
    QToolButton#OrbitConversationMore { color: #7A8296; background: transparent; border: 0;
                                       border-radius: 8px; min-width: 27px; max-width: 27px;
                                       min-height: 27px; max-height: 27px; padding: 0; font-size: 15pt; }
    QToolButton#OrbitConversationMore:hover { color: #5D43B7; background: #E5DEFF; }
    QLabel#OrbitRecentEmpty { color: #9099AD; background: #F8F9FC; border: 1px dashed #E3E8F1;
                              border-radius: 10px; padding: 10px 7px; font-size: 9pt; }
    QScrollArea#SidebarNavigation { background: transparent; border: 0; }
    QScrollArea#SidebarNavigation > QWidget > QWidget { background: transparent; }
    QLineEdit, QPlainTextEdit { background: #FFFFFF; border: 1px solid #DCE3ED; border-radius: 9px;
                               padding: 10px 12px; selection-background-color: #DDE5FF; }
    QLineEdit { min-height: 28px; padding: 4px 12px; }
    QComboBox, QSpinBox { min-height: 28px; padding: 4px 10px; background: #FFFFFF;
                          border: 1px solid #DCE3ED; border-radius: 9px; }
    QComboBox:hover, QSpinBox:hover { border-color: #C5D0E0; }
    QComboBox:focus, QSpinBox:focus { border-color: #4F6BED; }
    QComboBox::drop-down { width: 26px; border: 0; }
    QComboBox::down-arrow { image: url("__ASSETS__/tree-open.svg"); width: 12px; height: 12px; }
    QSpinBox::up-button, QSpinBox::down-button { width: 18px; border: 0;
        border-left: 1px solid #EDF0F5; background: transparent; }
    QComboBox QAbstractItemView { background: #FFFFFF; border: 1px solid #E5EAF2;
                                  selection-background-color: #EEF2FF; selection-color: #172033;
                                  padding: 4px; outline: 0; }
    QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #4F6BED; }
    QLineEdit:disabled, QPlainTextEdit:disabled { color: #94A3B8; background: #F8FAFC; }
    QTableView { background: #FFFFFF; alternate-background-color: #FAFBFD; border: 0;
                 gridline-color: #F0F2F6; selection-background-color: #EEF2FF;
                 selection-color: #172033; outline: 0; }
    QHeaderView::section { color: #64748B; background: #F8FAFC; border: 0;
                           border-bottom: 1px solid #E5EAF2; padding: 10px 12px; font-weight: 600; }
    QTableView::item { padding: 6px 8px; border-bottom: 1px solid #F0F2F6; }
    QTableView::item:selected { background: #EEF2FF; }
    QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
    QScrollBar::handle:vertical { background: #CBD5E1; min-height: 24px; border-radius: 4px; }
    QScrollBar:horizontal { background: transparent; height: 9px; margin: 2px; }
    QScrollBar::handle:horizontal { background: #CBD5E1; min-width: 24px; border-radius: 4px; }
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: transparent; border: 0; }
    QProgressBar { background: #E9EEF7; border: 0; border-radius: 4px; height: 8px; text-align: center; }
    QProgressBar::chunk { background: #4F6BED; border-radius: 4px; }
    QToolTip { color: #FFFFFF; background: #172033; border: 0; padding: 6px 8px; }
    """
    assets = (Path(__file__).parent.parent / "assets").as_posix()
    return stylesheet.replace("__FONT_FAMILY__", font_family).replace("__ASSETS__", assets)
