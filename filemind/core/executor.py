"""Safe file moves, operation journaling, and guarded undo."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4

from filemind.core.planner import validate_file_name
from filemind.models import OperationPlan, OperationRecord, PlannedOperation
from filemind.storage.history import OperationHistory


MoveFile = Callable[[Path, Path], None]


class ExecutionResult:
    """Summary of a confirmed organize or undo operation."""

    def __init__(self, succeeded: int = 0, failed: int = 0, cancelled: bool = False,
                 skipped: int = 0):
        self.succeeded = succeeded
        self.failed = failed
        self.cancelled = cancelled
        self.skipped = skipped
        self.failures: list[str] = []
        self.skip_reasons: list[str] = []


def move_without_overwrite(source: Path, target: Path) -> None:
    """Move one file while relying on a no-clobber filesystem operation."""
    if target.exists():
        raise FileExistsError(f"目标已存在：{target}")
    if os.name == "nt":
        os.rename(source, target)
        return
    os.link(source, target, follow_symlinks=False)
    try:
        source.unlink()
    except OSError:
        target.unlink(missing_ok=True)
        raise


def execute_plan(
    plan: OperationPlan,
    history: OperationHistory,
    confirmed: bool,
    move_file: MoveFile = move_without_overwrite,
    on_progress: Callable[[int, int], None] | None = None,
    cancel_event: Event | None = None,
) -> ExecutionResult:
    """Execute only a confirmed, still-safe plan and persist each result.

    A row that cannot run safely (explicitly excluded, flagged during preview, or whose
    destination appeared in the meantime) is skipped instead of aborting the batch, so
    one conflict never blocks the remaining files.
    """
    if not confirmed:
        return ExecutionResult(cancelled=True)

    record = OperationRecord.create(uuid4().hex, plan.root)
    history.save(record)
    result = ExecutionResult()
    total = len(plan.operations)
    for index, operation in enumerate(plan.operations, start=1):
        if cancel_event and cancel_event.is_set():
            result.cancelled = True
            break
        entry = _operation_entry(operation)
        record.operations.append(entry)
        history.save(record)
        _apply_operation(plan.root, operation, entry, record, history, move_file, result)
        if on_progress:
            on_progress(index, total)
    return result


def _apply_operation(root: Path, operation: PlannedOperation, entry: dict[str, object],
                     record: OperationRecord, history: OperationHistory,
                     move_file: MoveFile, result: ExecutionResult) -> None:
    """Persist an explicit skip or delegate one checked move to the journal."""
    skip_reason = _skip_reason(operation)
    if skip_reason is not None:
        entry.update(status="skipped", skip_reason=skip_reason)
        history.save(record)
        result.skipped += 1
        result.skip_reasons.append(f"{operation.source.name}：{skip_reason}")
        return
    failure = _execute_one(root, operation, entry, record, history, move_file)
    if failure:
        result.failures.append(failure)
        result.failed += 1
    else:
        result.succeeded += 1


def _skip_reason(operation: PlannedOperation) -> str | None:
    """Read current target state without modifying any file."""
    if operation.excluded:
        return "已在预览中排除"
    if operation.warning:
        return operation.warning
    if operation.review_note:
        return operation.review_note
    if operation.target.is_symlink():
        return "目标路径是符号链接，不能执行"
    if operation.target.exists():
        return "目标位置已存在同名文件，已跳过"
    return None


def undo_record(
    history: OperationHistory,
    operation_id: str,
    move_file: MoveFile = move_without_overwrite,
    cancel_event: Event | None = None,
) -> ExecutionResult:
    """Restore eligible files without overwriting or reverting edited files."""
    record = history.load(operation_id)
    if record.undone:
        return ExecutionResult()
    result = ExecutionResult()
    for entry in reversed(record.operations):
        if cancel_event and cancel_event.is_set():
            result.cancelled = True
            break
        if entry.get("status") != "success" or entry.get("undo_status") == "success":
            continue
        source = Path(str(entry["to"]))
        target = Path(str(entry["from"]))
        failure = _undo_one(history, source, target, entry, record, move_file)
        if failure:
            result.failures.append(failure)
            result.failed += 1
        else:
            result.succeeded += 1
    successful_moves = [item for item in record.operations if item.get("status") == "success"]
    record.undone = bool(successful_moves) and all(item.get("undo_status") == "success" for item in successful_moves)
    history.save(record)
    return result


def _execute_one(
    root: Path,
    operation: PlannedOperation,
    entry: dict[str, object],
    record: OperationRecord,
    history: OperationHistory,
    move_file: MoveFile,
) -> str | None:
    moved = False
    try:
        _validate_move_paths(root, operation.source, operation.target)
        source_stat = operation.source.stat(follow_symlinks=False)
        if source_stat.st_size != operation.size_bytes or source_stat.st_mtime_ns != operation.modified_ns:
            raise ValueError(f"文件在扫描后发生变化，请重新扫描：{operation.source}")
        if not _safe_directory_chain(root, operation.target.parent):
            raise ValueError(f"目标目录不安全：{operation.target.parent}")
        operation.target.parent.mkdir(parents=True, exist_ok=True)
        if not _safe_directory_chain(root, operation.target.parent):
            raise ValueError(f"目标目录不安全：{operation.target.parent}")
        move_file(operation.source, operation.target)
        moved = True
        target_stat = operation.target.stat(follow_symlinks=False)
        entry.update(status="success", size_bytes=target_stat.st_size, modified_ns=target_stat.st_mtime_ns)
        history.save(record)
        return None
    except (OSError, ValueError) as error:
        rollback_error = _rollback_if_moved(operation.target, operation.source, move_file) if moved else ""
        message = f"{error}{rollback_error}"
        entry.update(status="failed", error=message)
        try:
            history.save(record)
        except OSError as log_error:
            message += f"；错误日志也无法保存：{log_error}"
        return f"{operation.source.name}：{message}"


def _undo_one(
    history: OperationHistory,
    source: Path,
    target: Path,
    entry: dict[str, object],
    record: OperationRecord,
    move_file: MoveFile,
) -> str | None:
    moved = False
    try:
        _validate_move_paths(history.root, source, target, undo=True)
        if target.exists():
            raise FileExistsError(f"原位置已有文件，未覆盖：{target}")
        current_stat = source.stat(follow_symlinks=False)
        if current_stat.st_size != entry.get("size_bytes") or current_stat.st_mtime_ns != entry.get("modified_ns"):
            raise ValueError(f"文件整理后发生变化，未撤销：{source}")
        entry.update(undo_status="pending", undo_error="")
        history.save(record)
        move_file(source, target)
        moved = True
        entry.update(undo_status="success", undo_error="")
        history.save(record)
        return None
    except (OSError, ValueError, KeyError) as error:
        rollback_error = _rollback_if_moved(target, source, move_file) if moved else ""
        message = f"{error}{rollback_error}"
        entry.update(undo_status="failed", undo_error=message)
        try:
            history.save(record)
        except OSError as log_error:
            message += f"；错误日志也无法保存：{log_error}"
        return f"{source.name}：{message}"


def _rollback_if_moved(target: Path, source: Path, move_file: MoveFile) -> str:
    if not target.exists() or source.exists():
        return ""
    try:
        move_file(target, source)
        return "（已恢复原位置）"
    except (OSError, ValueError) as error:
        return f"（自动恢复失败：{error}）"


def _operation_entry(operation: PlannedOperation) -> dict[str, object]:
    return {
        "from": str(operation.source),
        "to": str(operation.target),
        "original_name": operation.original_name,
        "new_name": operation.new_name,
        "category": operation.classification.category,
        "reason": operation.classification.reason,
        "size_bytes": operation.size_bytes,
        "modified_ns": operation.modified_ns,
        "status": "pending",
        "error": "",
        "skip_reason": "",
    }


def _validate_move_paths(root: Path, source: Path, target: Path, undo: bool = False) -> None:
    """Keep file operations inside root and reject symlink sources or targets."""
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"源路径不是普通文件或是符号链接：{source}")
    validate_file_name(target.name)
    if target.is_symlink():
        raise ValueError(f"目标路径是符号链接：{target}")
    resolved_root = root.resolve(strict=True)
    if not source.resolve(strict=True).is_relative_to(resolved_root):
        raise ValueError(f"源文件超出所选目录：{source}")
    if not _safe_directory_chain(resolved_root, source.parent):
        raise ValueError(f"源路径包含符号链接目录：{source}")
    if undo:
        if target.parent.resolve(strict=True) != resolved_root:
            raise ValueError(f"撤销目标必须是所选目录的顶层文件：{target}")
    else:
        if source.parent.resolve(strict=True) != resolved_root:
            raise ValueError(f"待整理文件必须位于所选目录顶层：{source}")
    if not _safe_directory_chain(resolved_root, target.parent):
        raise ValueError(f"目标路径不安全或超出所选目录：{target}")


def _safe_directory_chain(root: Path, directory: Path) -> bool:
    """Reject target parent symlinks and directories outside the selected root."""
    try:
        resolved_root = root.resolve(strict=True)
        if not directory.resolve(strict=False).is_relative_to(resolved_root):
            return False
        relative = directory.relative_to(root)
    except (OSError, ValueError):
        return False
    cursor = root
    for segment in relative.parts:
        cursor = cursor / segment
        if cursor.is_symlink():
            return False
    return True
