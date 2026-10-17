"""Shared data models passed between FileMind modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


OperationStatus = Literal["pending", "success", "failed", "undone", "cancelled", "skipped"]


@dataclass(frozen=True)
class FileInfo:
    """Metadata for one regular file discovered in the selected directory."""

    path: Path
    size_bytes: int
    modified_ns: int

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()


@dataclass(frozen=True)
class ClassificationResult:
    """A category suggestion and the human-readable reason behind it."""

    category: str
    reason: str
    confidence: float = 1.0
    source: Literal["规则", "AI"] = "规则"
    target_subdirectory: str = ""


@dataclass(frozen=True)
class FileSuggestion:
    """A constrained model suggestion, never a file operation."""

    file_name: str
    category: str
    new_name: str
    reason: str
    file_id: str = ""
    target_subdirectory: str = ""


@dataclass(frozen=True)
class PlannedOperation:
    """One proposed move, validated before it is shown or executed."""

    source: Path
    target: Path
    original_name: str
    new_name: str
    classification: ClassificationResult
    size_bytes: int
    modified_ns: int
    warning: str | None = None
    excluded: bool = False
    requested_name: str = ""
    review_note: str = ""


@dataclass(frozen=True)
class OperationPlan:
    """A complete preview for files in one user-selected directory."""

    root: Path
    operations: tuple[PlannedOperation, ...]


@dataclass
class OperationRecord:
    """Persisted execution details used by history and undo."""

    operation_id: str
    created_at: str
    root: str
    operations: list[dict[str, object]] = field(default_factory=list)
    undone: bool = False

    @classmethod
    def create(cls, operation_id: str, root: Path) -> "OperationRecord":
        return cls(operation_id, datetime.now().astimezone().isoformat(), str(root))
