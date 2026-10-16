"""A plan-only directory tree; never enumerates the user's filesystem."""

from pathlib import Path

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem, QWidget

from filemind.models import OperationPlan
from filemind.ui.styles.icons import svg_icon
from filemind.ui.styles.file_icons import associated_file_icon
from filemind.ui.styles.theme import COLORS


PATH_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1


class PlanTargetTree(QTreeWidget):
    """Display the checked destination hierarchy with folder and file icons."""

    def __init__(self, plan: OperationPlan, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PlanTargetTree")
        self.setHeaderLabels(["整理后的目录", "状态"])
        self.setIconSize(QSize(20, 20))
        self.setIndentation(20)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setMinimumWidth(250)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 90)
        assets = Path(__file__).parent.parent / "assets"
        self._branch_open = QIcon(str(assets / "tree-open.svg"))
        self._branch_closed = QIcon(str(assets / "tree-closed.svg"))
        self._populate(plan)

    def drawBranches(self, painter: QPainter, rect: QRect, index: QModelIndex) -> None:
        """Paint the indentation too; Fusion otherwise leaves a blue selection block."""
        painter.save()
        selected = self.selectionModel().isSelected(index)
        painter.fillRect(rect, QColor(COLORS["primary_soft"] if selected else COLORS["card"]))
        if self.model().hasChildren(index):
            icon = self._branch_open if self.isExpanded(index) else self._branch_closed
            left = rect.right() - self.indentation() + (self.indentation() - 12) // 2
            icon.paint(painter, QRect(left, rect.center().y() - 6, 12, 12))
        painter.restore()

    def _populate(self, plan: OperationPlan) -> None:
        root = self._folder(plan.root.name or str(plan.root), "", plan.root)
        self.addTopLevelItem(root)
        folders: dict[str, QTreeWidgetItem] = {"": root}
        counts: dict[str, list[int]] = {"": [0, 0]}
        excluded: dict[str, int] = {"": 0}
        for operation in plan.operations:
            relative = operation.target.relative_to(plan.root)
            if ".." in relative.parts:
                raise ValueError("预览目标不在所选目录中。")
            current = root
            ancestors = [""]
            for depth, part in enumerate(relative.parts[:-1], 1):
                key = Path(*relative.parts[:depth]).as_posix()
                if key not in folders:
                    folders[key] = self._folder(part, key, plan.root / key)
                    current.addChild(folders[key])
                    counts[key] = [0, 0]
                    excluded[key] = 0
                current = folders[key]
                ancestors.append(key)
            node = QTreeWidgetItem([operation.new_name, self._file_status(operation)])
            node.setData(0, PATH_ROLE, relative.as_posix())
            node.setData(0, KIND_ROLE, "file")
            node.setIcon(0, associated_file_icon(operation.target.suffix.lower()))
            node.setToolTip(0, str(operation.target))
            node.setToolTip(1, self._file_tooltip(operation))
            if operation.warning:
                node.setIcon(0, svg_icon("warning", COLORS["warning"]))
                node.setForeground(1, QColor(COLORS["warning"]))
                if "同名" in operation.warning or "冲突" in operation.warning:
                    node.setText(1, "冲突")
            elif operation.excluded:
                node.setForeground(0, QColor(COLORS["muted"]))
                node.setForeground(1, QColor(COLORS["muted"]))
            current.addChild(node)
            for key in ancestors:
                if operation.excluded:
                    excluded[key] += 1
                else:
                    counts[key][0] += 1
                    counts[key][1] += bool(operation.warning)
        self._set_folder_counts(folders, counts, excluded)
        self.expandToDepth(1)
        self.setCurrentItem(root)

    @staticmethod
    def _file_status(operation) -> str:
        if operation.excluded:
            return "已排除"
        return "异常" if operation.warning else "待执行"

    @staticmethod
    def _file_tooltip(operation) -> str:
        if operation.excluded:
            return "这一行已排除，本次不会移动该文件"
        return operation.warning or "本地安全校验通过；确认后执行"

    @staticmethod
    def _folder(name: str, relative: str, absolute: Path) -> QTreeWidgetItem:
        node = QTreeWidgetItem([name, ""])
        node.setData(0, PATH_ROLE, relative)
        node.setData(0, KIND_ROLE, "folder")
        node.setToolTip(0, str(absolute))
        icon = svg_icon("folder_plan", COLORS["primary"])
        icon.addPixmap(svg_icon("folder_open", COLORS["primary"]).pixmap(22, 22),
                       QIcon.Mode.Normal, QIcon.State.On)
        node.setIcon(0, icon)
        return node

    @staticmethod
    def _set_folder_counts(folders: dict[str, QTreeWidgetItem], counts: dict[str, list[int]],
                           excluded: dict[str, int]) -> None:
        for key, node in folders.items():
            total, warnings = counts[key]
            skipped = excluded.get(key, 0)
            if warnings:
                node.setText(1, f"{warnings} 项异常")
            elif skipped:
                node.setText(1, f"{total} 个文件 · {skipped} 已排除")
            else:
                node.setText(1, f"{total} 个文件")
            node.setToolTip(1, f"{total} 个文件；{warnings} 项异常；{skipped} 项已排除；尚未执行")
            if warnings:
                node.setForeground(1, QColor(COLORS["warning"]))
