"""Append-only journals keep long runs linear and survive a crash."""

import json

from filemind.models import OperationRecord
from filemind.storage.history import OperationHistory


def _entry(name: str, status: str = "success") -> dict[str, object]:
    return {"from": f"D:/work/{name}", "to": f"D:/work/文档/{name}",
            "status": status, "error": "", "skip_reason": ""}


def test_save_writes_a_compact_record_and_removes_the_journal(tmp_path) -> None:
    history = OperationHistory(tmp_path)
    record = OperationRecord.create("a" * 32, tmp_path)
    record.operations.append(_entry("notes.txt"))

    with history.journal(record) as journal:
        journal.write(record.operations[0])
    history.save(record)

    record_path = history.history_dir / f"{record.operation_id}.json"
    saved = record_path.read_text(encoding="utf-8")
    assert "\n  " not in saved
    assert not history.journal_path(record.operation_id).exists()
    assert history.load(record.operation_id).operations == record.operations


def test_unfinished_run_is_recovered_from_the_journal(tmp_path) -> None:
    history = OperationHistory(tmp_path)
    record = OperationRecord.create("b" * 32, tmp_path)
    first = _entry("a.txt")
    second = _entry("b.txt", status="pending")
    record.operations.extend((first, second))

    with history.journal(record) as journal:
        journal.write(first)
        journal.write(second)
        journal.write({**second, "status": "skipped", "skip_reason": "目标已存在"})

    recovered = history.load(record.operation_id)
    assert [item["status"] for item in recovered.operations] == ["success", "skipped"]
    assert recovered.operations[1]["skip_reason"] == "目标已存在"
    assert [item.operation_id for item in history.list_records()] == [record.operation_id]


def test_truncated_last_line_keeps_earlier_steps(tmp_path) -> None:
    history = OperationHistory(tmp_path)
    record = OperationRecord.create("c" * 32, tmp_path)
    entry = _entry("c.txt")

    with history.journal(record) as journal:
        journal.write(entry)
    journal_path = history.journal_path(record.operation_id)
    journal_path.write_text(journal_path.read_text(encoding="utf-8") + '{"from": "D:/work/d',
                            encoding="utf-8")

    recovered = history.load(record.operation_id)
    assert len(recovered.operations) == 1
    assert recovered.operations[0]["from"] == "D:/work/c.txt"


def test_consolidated_record_wins_once_the_journal_is_gone(tmp_path) -> None:
    history = OperationHistory(tmp_path)
    record = OperationRecord.create("d" * 32, tmp_path)
    record.operations.append(_entry("d.txt"))
    history.save(record)

    payload = json.loads((history.history_dir / f"{record.operation_id}.json").read_text(encoding="utf-8"))

    assert payload["operation_id"] == record.operation_id
    assert payload["undone"] is False
    assert history.load(record.operation_id).undone is False
