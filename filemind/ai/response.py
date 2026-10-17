"""Validate structured AI suggestions without accepting model-supplied paths."""

import json
from typing import Any

from filemind.core.planner import (name_suffixes, validate_category, validate_file_name,
                                   validate_relative_subdirectory)
from filemind.models import FileInfo, FileSuggestion


MAX_RESPONSE_BYTES = 1_000_000
SUGGESTION_FIELDS = {"file_name", "category", "new_name", "reason"}
AI_SUGGESTION_FIELDS = {"file_id", "category", "target_subdirectory", "new_name", "reason"}


def parse_suggestions(response_text: str, expected_names: set[str]) -> dict[str, FileSuggestion]:
    """Parse exact per-file suggestions; model output cannot choose filesystem paths."""
    if len(response_text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("模型返回内容超过大小限制")
    try:
        payload: Any = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError("模型返回的内容不是合法 JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"suggestions"}:
        raise ValueError("模型返回格式必须包含 suggestions 数组")
    items = payload["suggestions"]
    if not isinstance(items, list) or len(items) != len(expected_names):
        raise ValueError("模型必须为每个文件返回且只返回一条建议")

    suggestions: dict[str, FileSuggestion] = {}
    for item in items:
        suggestion = _parse_item(item, expected_names)
        if suggestion.file_name in suggestions:
            raise ValueError(f"模型重复返回文件：{suggestion.file_name}")
        suggestions[suggestion.file_name] = suggestion
    if set(suggestions) != expected_names:
        raise ValueError("模型返回的文件名与待整理文件不一致")
    return suggestions


def parse_file_suggestions(
    response_text: str,
    expected_files: dict[str, FileInfo],
    rename_enabled: bool,
) -> dict[str, FileSuggestion]:
    """Validate stable-ID suggestions and reject all model-selected path escapes."""
    if len(response_text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("模型返回内容超过大小限制")
    try:
        payload: Any = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError("模型返回的内容不是合法 JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"suggestions"}:
        raise ValueError("模型返回格式必须包含 suggestions 数组")
    items = payload["suggestions"]
    if not isinstance(items, list) or len(items) != len(expected_files):
        raise ValueError("模型必须为每个文件返回且只返回一条建议")
    suggestions: dict[str, FileSuggestion] = {}
    for item in items:
        suggestion = _parse_file_item(item, expected_files, rename_enabled)
        if suggestion.file_id in suggestions:
            raise ValueError(f"模型重复返回文件 ID：{suggestion.file_id}")
        suggestions[suggestion.file_id] = suggestion
    if set(suggestions) != set(expected_files):
        raise ValueError("模型返回的文件 ID 与待整理文件不一致")
    return suggestions


def _parse_file_item(
    item: Any,
    expected_files: dict[str, FileInfo],
    rename_enabled: bool,
) -> FileSuggestion:
    if not isinstance(item, dict) or set(item) != AI_SUGGESTION_FIELDS:
        raise ValueError("AI 建议字段无效；不接受路径、命令或额外指令")
    if not isinstance(item["file_id"], str) or item["file_id"] not in expected_files:
        raise ValueError("模型返回了未知文件 ID")
    for field in ("category", "target_subdirectory", "reason"):
        if not isinstance(item[field], str):
            raise ValueError(f"AI 建议字段 {field} 必须是文本")
    if item["new_name"] is not None and not isinstance(item["new_name"], str):
        raise ValueError("AI 建议字段 new_name 必须是文本或 null")
    file_id = item["file_id"]
    file_info = expected_files[file_id]
    category = validate_category(item["category"])
    subdirectory = validate_relative_subdirectory(item["target_subdirectory"])
    reason = item["reason"].strip()
    if not reason:
        raise ValueError("整理理由不能为空")
    if len(reason) > 500:
        raise ValueError("整理理由超过 500 个字符")
    suggested_name = item["new_name"] or ""
    if suggested_name:
        validate_file_name(suggested_name)
        if _suffixes(suggested_name) != _suffixes(file_info.name):
            raise ValueError(f"新文件名必须保留原扩展名：{file_info.name}")
    if not rename_enabled:
        suggested_name = ""
    return FileSuggestion(file_info.name, category, suggested_name, reason, file_id, subdirectory)


def _suffixes(file_name: str) -> tuple[str, ...]:
    return name_suffixes(file_name)


def parse_partial_file_suggestions(response_text: str, expected_files: dict[str, FileInfo],
                                   rename_enabled: bool) -> tuple[dict[str, FileSuggestion], dict[str, str]]:
    """Isolate bad rows while retaining strict field, path and rename validation."""
    if len(response_text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("模型返回内容超过大小限制")
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError("模型返回的内容不是合法 JSON") from error
    if (not isinstance(payload, dict) or set(payload) != {"suggestions"}
            or not isinstance(payload["suggestions"], list)):
        raise ValueError("模型返回格式必须包含 suggestions 数组")
    suggestions: dict[str, FileSuggestion] = {}
    failures: dict[str, str] = {}
    for item in payload["suggestions"]:
        identifier = item.get("file_id") if isinstance(item, dict) else None
        if not isinstance(identifier, str) or identifier not in expected_files:
            continue
        if identifier in suggestions or identifier in failures:
            suggestions.pop(identifier, None)
            failures[identifier] = "模型重复返回该文件 ID，请重新确认建议"
            continue
        normalized = {"target_subdirectory": "", "new_name": None, "reason": "AI 分类建议", **item}
        if normalized["target_subdirectory"] is None:
            normalized["target_subdirectory"] = ""
        try:
            suggestions[identifier] = _parse_file_item(normalized, expected_files, rename_enabled)
        except ValueError:
            failures[identifier] = "该文件的 AI 建议未通过本地格式、路径或文件名校验"
    for identifier in expected_files.keys() - suggestions.keys() - failures.keys():
        failures[identifier] = "模型未返回该文件的有效建议"
    return suggestions, failures


def _parse_item(item: Any, expected_names: set[str]) -> FileSuggestion:
    if not isinstance(item, dict) or set(item) != SUGGESTION_FIELDS:
        raise ValueError("单条建议字段无效，模型不得返回目标路径或操作命令")
    if not all(isinstance(item[field], str) for field in SUGGESTION_FIELDS):
        raise ValueError("建议字段必须全部为文本")
    file_name = item["file_name"]
    if file_name not in expected_names:
        raise ValueError(f"模型返回了未扫描的文件：{file_name}")
    category = validate_category(item["category"])
    new_name = validate_file_name(item["new_name"])
    reason = item["reason"].strip()
    if not reason:
        raise ValueError("整理理由不能为空")
    original_suffix = "".join(name_suffixes(file_name))
    suggested_suffix = "".join(name_suffixes(new_name))
    if suggested_suffix != original_suffix:
        raise ValueError(f"新文件名必须保留原扩展名：{file_name}")
    return FileSuggestion(file_name, category, new_name, reason)
