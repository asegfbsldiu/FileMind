"""User edits applied to a reviewed plan without touching the filesystem.

The plan itself stays immutable; this module keeps editable rows next to it and
rebuilds a fresh, re-validated ``OperationPlan`` after every accepted change. An
edit that would be unsafe raises ``ValueError`` and changes nothing, so the table
can simply restore the previous value and explain why.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from filemind.core.planner import (PlanEntry, assemble_plan, name_suffixes, validate_category,
                                   validate_file_name, validate_relative_subdirectory)
from filemind.models import OperationPlan, PlannedOperation


@dataclass(frozen=True)
class EditableRow:
    """One preview row and its current, possibly edited, values."""

    source: Path
    original_name: str
    category: str
    requested_name: str
    target_subdirectory: str
    reason: str
    source_kind: str
    size_bytes: int
    modified_ns: int
    excluded: bool = False
    review_note: str = ""


class PlanEditor:
    """Hold editable rows for one plan and rebuild a validated plan on demand."""

    def __init__(self, plan: OperationPlan) -> None:
        self.root = plan.root
        self._rows = [_row_from(operation) for operation in plan.operations]

    @property
    def rows(self) -> tuple[EditableRow, ...]:
        return tuple(self._rows)

    def row(self, source: Path) -> EditableRow | None:
        """Return the editable row of one source path, if it is still present."""
        for item in self._rows:
            if item.source == source:
                return item
        return None

    def set_category(self, source: Path, category: str) -> None:
        """Store a validated category; raise ``ValueError`` for an unsafe label."""
        text = category.strip()
        validate_category(text)
        self._replace(source, category=text, review_note="")

    def set_target_subdirectory(self, source: Path, directory: str) -> None:
        """Store a validated subdirectory below the category."""
        text = directory.strip()
        validate_relative_subdirectory(text)
        self._replace(source, target_subdirectory=text, review_note="")

    def set_new_name(self, source: Path, name: str) -> None:
        """Store a new name that keeps the original extension."""
        row = self._require(source)
        text = name.strip()
        if not text or text == row.original_name:
            self._replace(source, requested_name=row.original_name, review_note="")
            return
        validate_file_name(text)
        original_suffix = name_suffixes(row.original_name)
        if name_suffixes(text) != original_suffix:
            raise ValueError(f"新文件名必须保留原扩展名：{''.join(original_suffix) or '无扩展名'}")
        self._replace(source, requested_name=text, review_note="")

    def set_excluded(self, source: Path, excluded: bool) -> None:
        """Include or exclude one row without changing any other value."""
        self._replace(source, excluded=excluded)

    def counts(self) -> tuple[int, int, int]:
        """Return ``(total, executable, skipped)`` for the current edits."""
        operations = self.build().operations
        total = len(operations)
        skipped = sum(item.excluded or bool(item.warning) for item in operations)
        return total, total - skipped, skipped

    def build(self) -> OperationPlan:
        """Rebuild the plan from the current rows."""
        return self._assemble(self._rows)

    def _assemble(self, rows: list[EditableRow]) -> OperationPlan:
        entries = [
            PlanEntry(
                source=row.source,
                category=row.category,
                reason=row.reason,
                size_bytes=row.size_bytes,
                modified_ns=row.modified_ns,
                source_kind=row.source_kind,
                target_subdirectory=row.target_subdirectory,
                new_name=row.requested_name,
                excluded=row.excluded,
                review_note=row.review_note,
            )
            for row in rows
        ]
        return assemble_plan(self.root, entries)

    def _require(self, source: Path) -> EditableRow:
        row = self.row(source)
        if row is None:
            raise ValueError("这一行已不存在，请重新扫描目录。")
        return row

    def _replace(self, source: Path, **changes: object) -> None:
        self._require(source)
        candidate = [replace(item, **changes) if item.source == source else item
                     for item in self._rows]
        self._assemble(candidate)
        self._rows = candidate


def _row_from(operation: PlannedOperation) -> EditableRow:
    return EditableRow(
        source=operation.source,
        original_name=operation.original_name,
        category=operation.classification.category,
        requested_name=operation.requested_name or operation.new_name,
        target_subdirectory=operation.classification.target_subdirectory,
        reason=operation.classification.reason,
        source_kind=operation.classification.source,
        size_bytes=operation.size_bytes,
        modified_ns=operation.modified_ns,
        excluded=operation.excluded,
        review_note=operation.review_note,
    )
