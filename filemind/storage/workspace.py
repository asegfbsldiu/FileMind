"""Local non-secret workspace layout and sanitized avatar storage."""

from __future__ import annotations

import json
import os
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import RLock

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader, QPainter

from filemind.storage.paths import data_dir


class WorkspaceError(RuntimeError):
    """Safe-to-display local layout or avatar error."""


def validate_user_name(value: str) -> str:
    """Normalize a local display name and reject empty or multiline names."""
    if not isinstance(value, str):
        raise WorkspaceError("请输入有效的用户名。")
    name = value.strip()
    if not name:
        raise WorkspaceError("用户名不能为空。")
    if len(name) > 32:
        raise WorkspaceError("用户名最多 32 个字符。")
    if any(unicodedata.category(character) in {"Cc", "Cs", "Zl", "Zp"} for character in name):
        raise WorkspaceError("用户名不能包含换行或控制字符。")
    return name


@dataclass(frozen=True)
class WorkspacePreferences:
    """Non-secret local presentation settings, independent of API credentials."""

    sidebar_width: int = 252
    sidebar_collapsed: bool = False
    avatar_file: str = ""
    organizer_height: int = 246
    reduced_motion: bool = False
    user_name: str = "本机用户"


class WorkspaceStore:
    """Persist only UI choices and an explicitly selected avatar thumbnail."""

    def __init__(self, path: Path | None = None, memory: bool = False) -> None:
        self.path = path or data_dir() / "workspace.json"
        self.memory = memory
        self._value = WorkspacePreferences()
        self._lock = RLock()

    def load(self) -> WorkspacePreferences:
        """Read UI-only JSON; never inspect model settings, env keys or OS keys."""
        with self._lock:
            if self.memory or not self.path.exists():
                return self._value
            try:
                if self.path.is_symlink() or self.path.stat().st_size > 8192:
                    raise ValueError("invalid UI configuration")
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._value = WorkspacePreferences(
                    min(380, max(230, int(data.get("sidebar_width", 252)))),
                    data.get("sidebar_collapsed") is True,
                    "avatar.png" if data.get("avatar_file") == "avatar.png" else "",
                    min(600, max(140, int(data.get("organizer_height", 246)))),
                    data.get("reduced_motion") is True,
                    validate_user_name(data.get("user_name", "本机用户")))
                return self._value
            except (OSError, ValueError, TypeError, AttributeError) as error:
                raise WorkspaceError("界面布局配置无法读取，请检查本机配置目录。") from error

    def save_layout(self, width: int, collapsed: bool) -> None:
        """Persist a bounded sidebar width and its expanded state."""
        with self._lock:
            value = replace(self.load(), sidebar_width=min(380, max(230, width)),
                            sidebar_collapsed=collapsed)
            self._write(value)

    def avatar_path(self) -> Path | None:
        """Return only this store's internal image, never an arbitrary JSON path."""
        if not self.load().avatar_file:
            return None
        path = self.path.with_name("avatar.png")
        return path if path.is_file() and not path.is_symlink() else None

    def save_organizer_height(self, height: int) -> None:
        """Remember the user's rule-panel height separately from sidebar width."""
        with self._lock:
            self._write(replace(self.load(), organizer_height=min(600, max(140, height))))

    def save_reduced_motion(self, reduced: bool) -> None:
        """Remember the avatar motion preference with other local UI choices."""
        with self._lock:
            self._write(replace(self.load(), reduced_motion=reduced))

    def save_user_name(self, user_name: str) -> str:
        """Save the local display name while retaining all other UI preferences."""
        name = validate_user_name(user_name)
        with self._lock:
            self._write(replace(self.load(), user_name=name))
        return name

    def save_avatar(self, source: Path) -> Path:
        """Decode a selected raster and keep a small local PNG without metadata."""
        if self.memory:
            raise WorkspaceError("当前验收配置不保存头像。")
        if source.is_symlink() or not source.is_file() or source.stat().st_size > 8 * 1024 * 1024:
            raise WorkspaceError("请选择不超过 8 MB 的普通图片文件。")
        reader = QImageReader(str(source))
        reader.setDecideFormatFromContent(True)
        reader.setAutoTransform(True)
        if bytes(reader.format()).lower() not in {b"png", b"jpg", b"jpeg", b"webp", b"bmp"}:
            raise WorkspaceError("头像仅支持 PNG、JPEG、WebP 或 BMP。")
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > 16_000_000:
            raise WorkspaceError("头像尺寸过大或图片已损坏。")
        image = reader.read()
        if image.isNull():
            raise WorkspaceError("头像图片无法解码。")
        image = image.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation)
        image = image.copy((image.width() - 128) // 2, (image.height() - 128) // 2, 128, 128)
        thumbnail = QImage(128, 128, QImage.Format.Format_ARGB32)
        thumbnail.fill(Qt.GlobalColor.transparent)
        painter = QPainter(thumbnail)
        painter.drawImage(0, 0, image)
        painter.end()
        return self._save_thumbnail(thumbnail)

    def _save_thumbnail(self, image: QImage) -> Path:
        with self._lock:
            self._prepare_directory()
            preferences = self.load()
            descriptor, name = tempfile.mkstemp(suffix=".png", dir=self.path.parent)
            os.close(descriptor)
            staging = Path(name)
            try:
                if not image.save(str(staging), "PNG"):
                    raise WorkspaceError("无法保存本机头像。")
                destination = self.path.with_name("avatar.png")
                if destination.is_symlink():
                    raise WorkspaceError("头像目标不能是符号链接。")
                staging.replace(destination)
                self._write(replace(preferences, avatar_file="avatar.png"))
                return destination
            finally:
                staging.unlink(missing_ok=True)

    def _write(self, value: WorkspacePreferences) -> None:
        if self.memory:
            self._value = value
            return
        self._prepare_directory()
        descriptor, name = tempfile.mkstemp(prefix="workspace-", dir=self.path.parent)
        staging = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(asdict(value), stream)
                stream.flush()
                os.fsync(stream.fileno())
            staging.replace(self.path)
            self._value = value
        except OSError as error:
            raise WorkspaceError("无法保存界面配置，请检查本机目录权限。") from error
        finally:
            staging.unlink(missing_ok=True)

    def _prepare_directory(self) -> None:
        if self.path.is_symlink() or any(
                parent.is_symlink() or parent.is_junction() for parent in self.path.parents):
            raise WorkspaceError("界面配置目录不能是链接。")
        self.path.parent.mkdir(parents=True, exist_ok=True)
