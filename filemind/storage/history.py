"""Persist operation records in the selected directory without external services.

Long runs append one compact JSON line per step to a journal and write the
consolidated record once at the end. Rewriting the full record after every file made
the total write volume quadratic, while appending keeps per-step durability.
"""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TextIO

from filemind.models import OperationRecord


class OperationJournal:
    """Append-only journal for one run; the last line of a source path wins."""

    def __init__(self, stream: TextIO, record: OperationRecord) -> None:
        self._stream = stream
        if stream.tell() == 0:
            self._write_line({
                "type": "record",
                "operation_id": record.operation_id,
                "created_at": record.created_at,
                "root": record.root,
            })

    def write(self, entry: dict[str, object]) -> None:
        """Persist one operation step without rewriting earlier steps."""
        self._stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._stream.flush()

    def close(self) -> None:
        """Flush and fsync once so a finished journal survives a crash."""
        try:
            self._stream.flush()
            os.fsync(self._stream.fileno())
        except OSError:
            pass

    def _write_line(self, payload: dict[str, object]) -> None:
        self._stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._stream.flush()


class OperationHistory:
    """Read and write operation records under the selected directory."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve(strict=True)
        self.history_dir = self.root / ".filemind" / "history"
        if (self.root / ".filemind").is_symlink() or self.history_dir.is_symlink():
            raise ValueError("FileMind 历史记录目录不能是符号链接")

    def _ensure_safe_directory(self) -> None:
        metadata_dir = self.root / ".filemind"
        if metadata_dir.is_symlink() or self.history_dir.is_symlink():
            raise ValueError("FileMind 历史记录目录不能是符号链接")
        metadata_dir.mkdir(exist_ok=True)
        self.history_dir.mkdir(exist_ok=True)
        if not self.history_dir.resolve().is_relative_to(self.root):
            raise ValueError("历史记录目录必须位于所选目录内")

    def journal_path(self, operation_id: str) -> Path:
        """Return the append-only journal path for one operation."""
        return self.history_dir / f"{operation_id}.ndjson"

    @contextmanager
    def journal(self, record: OperationRecord) -> Iterator[OperationJournal]:
        """Open a journal for one run; appending keeps writes linear in file count."""
        self._ensure_safe_directory()
        path = self.journal_path(record.operation_id)
        if path.is_symlink():
            raise ValueError("操作日志不能是符号链接")
        with path.open("a", encoding="utf-8") as stream:
            writer = OperationJournal(stream, record)
            try:
                yield writer
            finally:
                writer.close()

    def save(self, record: OperationRecord) -> None:
        """Atomically save the consolidated record and drop its journal."""
        self._ensure_safe_directory()
        destination = self.history_dir / f"{record.operation_id}.json"
        temporary = destination.with_suffix(".tmp")
        payload = {
            "operation_id": record.operation_id,
            "created_at": record.created_at,
            "root": record.root,
            "operations": record.operations,
            "undone": record.undone,
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                             encoding="utf-8")
        os.replace(temporary, destination)
        self.journal_path(record.operation_id).unlink(missing_ok=True)

    def load(self, operation_id: str) -> OperationRecord:
        """Load one record; an unfinished run is recovered from its journal."""
        if not operation_id.isalnum() or len(operation_id) != 32:
            raise ValueError("操作记录编号无效")
        journal = self.journal_path(operation_id)
        if journal.is_file() and not journal.is_symlink():
            return self._load_journal(operation_id, journal)
        path = self.history_dir / f"{operation_id}.json"
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("root") != str(self.root) or not isinstance(payload.get("operations"), list):
            raise ValueError("操作记录与当前目录不匹配或格式无效")
        return OperationRecord(
            operation_id,
            str(payload["created_at"]),
            str(payload["root"]),
            payload["operations"],
            bool(payload.get("undone", False)),
        )

    def list_records(self) -> list[OperationRecord]:
        """Return valid operation records newest first, including unfinished runs."""
        if not self.history_dir.exists():
            return []
        records: list[OperationRecord] = []
        seen: set[str] = set()
        for path in sorted(self.history_dir.iterdir()):
            if path.suffix not in {".json", ".ndjson"} or path.stem in seen:
                continue
            try:
                records.append(self.load(path.stem))
                seen.add(path.stem)
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return sorted(records, key=lambda record: record.created_at, reverse=True)

    def _load_journal(self, operation_id: str, path: Path) -> OperationRecord:
        """Rebuild the newest state of each source path from appended lines."""
        header: dict[str, Any] | None = None
        latest: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                # A crash can truncate the final line; earlier steps stay usable.
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") == "record":
                header = item
                continue
            key = str(item.get("from") or item.get("to") or "")
            if not key:
                continue
            if key not in latest:
                order.append(key)
            latest[key] = item
        if header is None or header.get("root") != str(self.root):
            raise ValueError("操作日志与当前目录不匹配或格式无效")
        entries = [latest[key] for key in order]
        successful = [item for item in entries if item.get("status") == "success"]
        undone = bool(successful) and all(item.get("undo_status") == "success" for item in successful)
        return OperationRecord(operation_id, str(header["created_at"]), str(header["root"]),
                               entries, undone)
