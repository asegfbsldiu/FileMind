"""Tests for confirmed moves, collision handling, partial failure, and undo."""

import tempfile
import unittest
from pathlib import Path

from filemind.core.classifier import classify_file
from filemind.core.executor import execute_plan, undo_record
from filemind.core.planner import build_plan
from filemind.core.scanner import scan_files
from filemind.ai.schemas import file_metadata
from filemind.models import FileSuggestion
from filemind.storage.history import OperationHistory


class ExecutorTests(unittest.TestCase):
    def test_cancel_does_not_change_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "notes.txt"
            source.write_text("hello", encoding="utf-8")
            plan = build_plan(root, scan_files(root), classify_file)

            result = execute_plan(plan, OperationHistory(root), confirmed=False)

            self.assertTrue(result.cancelled)
            self.assertTrue(source.exists())
            self.assertFalse((root / "文档" / source.name).exists())

    def test_existing_destination_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "notes.txt"
            source.write_text("source", encoding="utf-8")
            target = root / "文档" / source.name
            target.parent.mkdir()
            target.write_text("keep", encoding="utf-8")
            history = OperationHistory(root)
            plan = build_plan(root, scan_files(root), classify_file)

            result = execute_plan(plan, history, confirmed=True)

            self.assertEqual((result.succeeded, result.skipped, result.failed), (0, 1, 0))
            record = history.list_records()[0]
            self.assertEqual(record.operations[0]["status"], "skipped")
            self.assertIn("同名", str(record.operations[0]["skip_reason"]))

            self.assertEqual(source.read_text(encoding="utf-8"), "source")
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_successful_move_can_be_undone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "课程笔记.txt"
            source.write_text("内容", encoding="utf-8")
            history = OperationHistory(root)
            plan = build_plan(root, scan_files(root), classify_file)

            result = execute_plan(plan, history, confirmed=True)
            operation_id = history.list_records()[0].operation_id
            undo_result = undo_record(history, operation_id)

            self.assertEqual(result.succeeded, 1)
            self.assertEqual(undo_result.succeeded, 1)
            self.assertEqual(source.read_text(encoding="utf-8"), "内容")
            self.assertFalse((root / "文档" / source.name).exists())
            self.assertTrue(history.load(operation_id).undone)

    def test_ai_rename_and_nested_destination_can_be_undone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "课程资料.txt"
            source.write_text("内容", encoding="utf-8")
            file_info = scan_files(root)[0]
            suggestion = FileSuggestion(
                file_info.name, "学习资料", "数据结构复习.txt", "课程语义",
                file_metadata(file_info).file_id, "数据结构/第1章",
            )
            plan = build_plan(root, [file_info], classify_file, {suggestion.file_id: suggestion}, True)
            history = OperationHistory(root)

            result = execute_plan(plan, history, confirmed=True)
            organized_path = root / "学习资料" / "数据结构" / "第1章" / "数据结构复习.txt"
            operation_id = history.list_records()[0].operation_id
            undo_result = undo_record(history, operation_id)

            self.assertEqual(result.succeeded, 1)
            self.assertEqual(undo_result.succeeded, 1)
            self.assertEqual(source.read_text(encoding="utf-8"), "内容")
            self.assertFalse(organized_path.exists())

    def test_modified_file_is_not_undone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "notes.txt"
            source.write_text("original", encoding="utf-8")
            history = OperationHistory(root)
            plan = build_plan(root, scan_files(root), classify_file)
            execute_plan(plan, history, confirmed=True)
            operation_id = history.list_records()[0].operation_id
            target = root / "文档" / source.name
            target.write_text("changed size", encoding="utf-8")

            result = undo_record(history, operation_id)

            self.assertEqual(result.failed, 1)
            self.assertFalse(source.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "changed size")

    def test_undo_does_not_overwrite_a_new_file_at_original_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "notes.txt"
            source.write_text("organized", encoding="utf-8")
            history = OperationHistory(root)
            plan = build_plan(root, scan_files(root), classify_file)
            execute_plan(plan, history, confirmed=True)
            operation_id = history.list_records()[0].operation_id
            source.write_text("new user file", encoding="utf-8")

            result = undo_record(history, operation_id)

            self.assertEqual(result.failed, 1)
            self.assertEqual(source.read_text(encoding="utf-8"), "new user file")
            self.assertEqual((root / "文档" / source.name).read_text(encoding="utf-8"), "organized")

    def test_permission_failure_is_reported_and_other_files_continue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "a.txt").write_text("a", encoding="utf-8")
            (root / "b.txt").write_text("b", encoding="utf-8")
            history = OperationHistory(root)
            plan = build_plan(root, scan_files(root), classify_file)

            def fail_one(source: Path, target: Path) -> None:
                if source.name == "a.txt":
                    raise PermissionError("文件被占用或没有权限")
                from filemind.core.executor import move_without_overwrite

                move_without_overwrite(source, target)

            result = execute_plan(plan, history, confirmed=True, move_file=fail_one)
            record = history.list_records()[0]

            self.assertEqual((result.succeeded, result.failed), (1, 1))
            self.assertEqual((root / "a.txt").read_text(encoding="utf-8"), "a")
            self.assertTrue((root / "文档" / "b.txt").exists())
            self.assertIn("权限", str(record.operations[0]["error"]))

    def test_changed_source_after_preview_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "notes.txt"
            source.write_text("first", encoding="utf-8")
            plan = build_plan(root, scan_files(root), classify_file)
            source.write_text("different length", encoding="utf-8")

            result = execute_plan(plan, OperationHistory(root), confirmed=True)

            self.assertEqual(result.failed, 1)
            self.assertTrue(source.exists())
            self.assertFalse((root / "文档" / source.name).exists())

    def test_journal_failure_rolls_back_the_file_move(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "notes.txt"
            source.write_text("content", encoding="utf-8")
            history = OperationHistory(root)
            plan = build_plan(root, scan_files(root), classify_file)
            original_save = history.save
            save_calls = 0

            def fail_after_move(record) -> None:
                nonlocal save_calls
                save_calls += 1
                if save_calls == 3:
                    raise OSError("disk full")
                original_save(record)

            history.save = fail_after_move
            result = execute_plan(plan, history, confirmed=True)

            self.assertEqual((result.succeeded, result.failed), (0, 1))
            self.assertTrue(source.exists())
            self.assertFalse((root / "文档" / source.name).exists())
            self.assertIn("已恢复原位置", result.failures[0])


if __name__ == "__main__":
    unittest.main()
