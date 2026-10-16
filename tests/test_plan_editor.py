"""Reviewed plan edits: validated in Python, never touched on disk."""

from pathlib import Path

import pytest

from filemind.core.classifier import classify_file
from filemind.core.plan_editor import PlanEditor
from filemind.core.planner import build_plan, stable_file_id
from filemind.core.scanner import scan_files


def _editor(tmp_path: Path) -> PlanEditor:
    for name in ("notes.txt", "报告.pdf"):
        (tmp_path / name).write_text("virtual", encoding="utf-8")
    return PlanEditor(build_plan(tmp_path, scan_files(tmp_path), classify_file))


def test_category_and_name_edits_change_the_rebuilt_target(tmp_path: Path) -> None:
    editor = _editor(tmp_path)
    source = next(row.source for row in editor.rows if row.original_name == "notes.txt")

    editor.set_category(source, "学习资料")
    editor.set_target_subdirectory(source, "数据结构/第1章")
    editor.set_new_name(source, "笔记整理.txt")

    operation = next(item for item in editor.build().operations if item.source == source)
    assert operation.target == tmp_path / "学习资料" / "数据结构" / "第1章" / "笔记整理.txt"
    assert operation.classification.source == "规则"


def test_unsafe_category_and_name_edits_are_rejected_without_changing_the_row(tmp_path: Path) -> None:
    editor = _editor(tmp_path)
    source = next(row.source for row in editor.rows if row.original_name == "notes.txt")

    with pytest.raises(ValueError):
        editor.set_category(source, "../escape")
    with pytest.raises(ValueError):
        editor.set_target_subdirectory(source, "../外部")
    with pytest.raises(ValueError):
        editor.set_new_name(source, "notes.pdf")
    with pytest.raises(ValueError):
        editor.set_new_name(source, "CON.txt")

    operation = next(item for item in editor.build().operations if item.source == source)
    assert operation.classification.category == "文档"
    assert operation.new_name == "notes.txt"


def test_excluded_rows_do_not_reserve_a_destination_name(tmp_path: Path) -> None:
    for name in ("讲义A.pdf", "讲义B.pdf"):
        (tmp_path / name).write_text("virtual", encoding="utf-8")
    editor = PlanEditor(build_plan(tmp_path, scan_files(tmp_path), classify_file))
    first, second = (row.source for row in editor.rows)

    editor.set_new_name(first, "讲义.pdf")
    editor.set_new_name(second, "讲义.pdf")
    collided = [item.target.name for item in editor.build().operations]
    assert sorted(collided) == ["讲义 (2).pdf", "讲义.pdf"]

    editor.set_excluded(first, True)
    executable = [item for item in editor.build().operations if not item.excluded]

    assert [item.target.name for item in executable] == ["讲义.pdf"]
    assert editor.counts() == (2, 1, 1)


def test_ai_failure_marker_survives_unrelated_edits_and_clears_on_review(tmp_path: Path) -> None:
    for name in ("课程资料.txt", "报告.pdf"):
        (tmp_path / name).write_text("virtual", encoding="utf-8")
    failed = {stable_file_id("课程资料.txt"): "服务商拒绝请求"}
    plan = build_plan(tmp_path, scan_files(tmp_path), classify_file, None, False, failed)
    editor = PlanEditor(plan)
    blocked = next(item for item in plan.operations if item.original_name == "课程资料.txt")
    assert "AI 批次失败" in (blocked.warning or "")

    other = next(row.source for row in editor.rows if row.original_name == "报告.pdf")
    editor.set_category(other, "学习资料")
    still_blocked = next(item for item in editor.build().operations
                         if item.original_name == "课程资料.txt")

    assert "AI 批次失败" in (still_blocked.warning or "")

    editor.set_category(blocked.source, "待确认")
    reviewed = next(item for item in editor.build().operations
                    if item.original_name == "课程资料.txt")

    assert reviewed.warning is None
    assert reviewed.classification.category == "待确认"
