"""Tests for scanning, local classification, and plan validation."""

import tempfile
import unittest
from pathlib import Path

from filemind.core.classifier import classify_file
from filemind.core.planner import build_plan, validate_file_name
from filemind.models import ClassificationResult
from filemind.core.scanner import scan_files


class ScannerPlannerTests(unittest.TestCase):
    def test_empty_directory_returns_no_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            self.assertEqual(scan_files(Path(temporary_directory)), [])

    def test_scans_top_level_mixed_files_and_chinese_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "毕业设计.pdf").write_text("", encoding="utf-8")
            (root / "旅行.JPG").write_text("", encoding="utf-8")
            (root / "未知格式.xyz").write_text("", encoding="utf-8")
            (root / "子目录").mkdir()
            (root / "子目录" / "不递归.txt").write_text("", encoding="utf-8")

            files = scan_files(root)

            self.assertEqual({file_info.name for file_info in files}, {
                "毕业设计.pdf", "旅行.JPG", "未知格式.xyz"
            })
            result_by_name = {file_info.name: classify_file(file_info).category for file_info in files}
            self.assertEqual(result_by_name["毕业设计.pdf"], "文档")
            self.assertEqual(result_by_name["旅行.JPG"], "图片")
            self.assertEqual(result_by_name["未知格式.xyz"], "其他")

    def test_plan_rejects_traversal_and_invalid_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "report.txt").write_text("", encoding="utf-8")
            file_info = scan_files(root)[0]

            for category in ("../outside", "bad/name", "..", "trailing.", "CON"):
                with self.subTest(category=category):
                    with self.assertRaises(ValueError):
                        build_plan(root, [file_info], lambda _: _result(category))

    def test_invalid_and_special_file_names_are_rejected(self) -> None:
        for file_name in ("bad:name.txt", "trailing.", "CON.txt", "contains\u0001control.txt"):
            with self.subTest(file_name=file_name):
                with self.assertRaises(ValueError):
                    validate_file_name(file_name)
        self.assertEqual(validate_file_name("课程笔记 (1).txt"), "课程笔记 (1).txt")


def _result(category: str) -> ClassificationResult:
    return ClassificationResult(category, "test")


def test_plan_validates_each_target_directory_once(monkeypatch, tmp_path: Path) -> None:
    for index in range(50):
        (tmp_path / f"文件{index:02d}.txt").write_text("", encoding="utf-8")
    calls: list[Path] = []
    from filemind.core import planner

    original = planner._validate_target_directory

    def counting(root: Path, directory: Path) -> None:
        calls.append(directory)
        original(root, directory)

    monkeypatch.setattr("filemind.core.planner._validate_target_directory", counting)
    plan = build_plan(tmp_path, scan_files(tmp_path), classify_file)

    assert len(plan.operations) == 50
    assert calls == [tmp_path / "文档"]


def test_category_path_that_is_an_existing_file_still_warns(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    (tmp_path / "文档").write_text("not a directory", encoding="utf-8")

    plan = build_plan(tmp_path, scan_files(tmp_path), classify_file)
    first = plan.operations[0]

    assert "非目录文件" in (first.warning or "")


if __name__ == "__main__":
    unittest.main()
