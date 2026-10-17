"""Build and validate safe, reviewable file organization plans."""

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping, Sequence

from filemind.models import ClassificationResult, FileInfo, FileSuggestion, OperationPlan, PlannedOperation


INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAME = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.IGNORECASE)
MAX_NAME_UNITS = 255
MAX_COLLISION_ATTEMPTS = 1000


@dataclass(frozen=True)
class PlanEntry:
    """One plan row before its target path is computed and validated."""

    source: Path
    category: str
    reason: str
    size_bytes: int = 0
    modified_ns: int = 0
    source_kind: str = "规则"
    target_subdirectory: str = ""
    new_name: str = ""
    excluded: bool = False
    review_note: str = ""


def stable_file_id(relative_key: str) -> str:
    """Return the path-free ID shared by the AI request and the local plan."""
    return f"f_{sha256(relative_key.encode('utf-8')).hexdigest()[:20]}"


def file_key(root: Path, path: Path) -> str:
    """Return the root-relative POSIX key that identifies one scanned file."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        raise ValueError(f"文件不在所选目录中：{path}") from None


def validate_category(category: str) -> str:
    """Reject category labels that could escape the selected directory."""
    normalized = category.strip()
    if not normalized or normalized in {".", ".."} or INVALID_NAME_CHARS.search(normalized):
        raise ValueError(f"不安全的分类文件夹名称：{category!r}")
    if normalized.rstrip(" .") != normalized:
        raise ValueError(f"分类名称不能以空格或句点结尾：{category!r}")
    return validate_file_name(normalized)


def name_suffixes(name: str) -> tuple[str, ...]:
    """Share case-insensitive extension chains across AI and manual renames."""
    return tuple(suffix.casefold() for suffix in Path(name).suffixes)


def validate_file_name(name: str) -> str:
    """Reject names that are unsafe or invalid on common desktop filesystems."""
    if not name or name in {".", ".."} or INVALID_NAME_CHARS.search(name):
        raise ValueError(f"不安全的文件名：{name!r}")
    if name.endswith((".", " ")) or RESERVED_NAME.fullmatch(name):
        raise ValueError(f"文件名在 Windows 中不可用：{name!r}")
    if len(name.encode("utf-16-le")) // 2 > 255:
        raise ValueError("文件名超过 Windows 单个路径组件的长度限制")
    return name


def validate_relative_subdirectory(directory: str) -> str:
    """Validate model-selected subdirectories as safe relative path segments."""
    if not directory:
        return ""
    if len(directory) > 400 or len(directory.split("/")) > 8:
        raise ValueError("目标子目录过长或层级过深")
    if directory.startswith(("/", "\\")) or "\\" in directory or ":" in directory:
        raise ValueError(f"不安全的目标子目录：{directory!r}")
    segments = directory.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        raise ValueError(f"不安全的目标子目录：{directory!r}")
    return "/".join(validate_file_name(segment) for segment in segments)


def build_plan(
    root: Path,
    files: Sequence[FileInfo],
    classify: Callable[[FileInfo], ClassificationResult],
    suggestions: Mapping[str, FileSuggestion] | None = None,
    rename_files: bool = False,
    failed_file_ids: Mapping[str, str] | set[str] | None = None,
) -> OperationPlan:
    """Create a plan and reject any source or destination outside ``root``."""
    selected_root = _selected_root(root)
    entries: list[PlanEntry] = []
    for file_info in files:
        source = _validated_source(selected_root, file_info.path)
        suggestion = suggestions.get(stable_file_id(file_key(selected_root, source))) if suggestions else None
        if suggestion is not None:
            entry = PlanEntry(
                source, suggestion.category, suggestion.reason,
                file_info.size_bytes, file_info.modified_ns, "AI",
                suggestion.target_subdirectory,
                suggestion.new_name if rename_files else "",
                review_note=_review_note(stable_file_id(file_key(selected_root, source)), failed_file_ids),
            )
        else:
            classification = classify(file_info)
            entry = PlanEntry(
                source, classification.category, classification.reason,
                file_info.size_bytes, file_info.modified_ns, classification.source,
                classification.target_subdirectory,
                review_note=_review_note(stable_file_id(file_key(selected_root, source)), failed_file_ids),
            )
        entries.append(entry)
    return assemble_plan(selected_root, entries)


def assemble_plan(
    root: Path,
    entries: Sequence[PlanEntry],
) -> OperationPlan:
    """Compute targets, resolve collisions inside the plan, and mark risky rows.

    Expected conditions such as an existing destination become warnings so the rest
    of the plan stays reviewable; unsafe paths and names still raise.
    """
    selected_root = _selected_root(root)
    operations: list[PlannedOperation] = []
    seen_targets: set[str] = set()
    for entry in entries:
        source = _validated_source(selected_root, entry.source)
        category = validate_category(entry.category)
        target_directory = selected_root / category
        subdirectory = validate_relative_subdirectory(entry.target_subdirectory)
        if subdirectory:
            target_directory = target_directory.joinpath(*subdirectory.split("/"))
        _validate_target_directory(selected_root, target_directory)
        requested_name = entry.new_name or source.name
        if name_suffixes(requested_name) != name_suffixes(source.name):
            raise ValueError(f"新文件名必须保留原扩展名：{source.suffix or '无扩展名'}")
        new_name = unique_target_name(target_directory,
                                      validate_file_name(requested_name), seen_targets)
        target = target_directory / new_name
        if not entry.excluded:
            # An excluded row is never moved, so it must not reserve a destination name.
            seen_targets.add(target.as_posix().casefold())
        classification = ClassificationResult(category, entry.reason, source=entry.source_kind,
                                              target_subdirectory=subdirectory)
        operations.append(PlannedOperation(
            source=source, target=target, original_name=source.name, new_name=new_name,
            classification=classification, size_bytes=entry.size_bytes,
            modified_ns=entry.modified_ns,
            warning=plan_warning(target, entry.review_note),
            excluded=entry.excluded, requested_name=requested_name, review_note=entry.review_note))
    return OperationPlan(selected_root, tuple(operations))


def _review_note(file_id: str, failed_file_ids: Mapping[str, str] | set[str] | None) -> str:
    """Describe why one row still needs the user's review before it may run."""
    if not failed_file_ids or file_id not in failed_file_ids:
        return ""
    if isinstance(failed_file_ids, Mapping):
        return f"AI 批次失败：{failed_file_ids[file_id]}；此行使用本地规则"
    return "AI 批次失败；此行使用本地规则"


def unique_target_name(directory: Path, name: str, taken: set[str]) -> str:
    """Return a name that does not collide inside this plan; targets are never overwritten."""
    if (directory / name).as_posix().casefold() not in taken:
        return name
    stem, suffix = _split_name(name)
    for index in range(2, MAX_COLLISION_ATTEMPTS + 2):
        candidate = f"{stem} ({index}){suffix}"
        if (directory / candidate).as_posix().casefold() in taken:
            continue
        if len(candidate.encode("utf-16-le")) // 2 > MAX_NAME_UNITS:
            raise ValueError(f"目标名称冲突后超出 Windows 长度限制：{name!r}")
        return candidate
    raise ValueError(f"目标名称冲突过多，无法为 {name!r} 生成安全的新名称")


def _split_name(name: str) -> tuple[str, str]:
    suffix = Path(name).suffix
    return (name[: len(name) - len(suffix)], suffix) if suffix else (name, "")


def _selected_root(root: Path) -> Path:
    selected_root = root.expanduser().resolve(strict=True)
    if not selected_root.is_dir():
        raise NotADirectoryError(f"所选路径不是文件夹：{selected_root}")
    return selected_root


def _validated_source(root: Path, path: Path) -> Path:
    """Accept a regular file directly inside the selected root; never a symlink."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"源文件不是普通文件或是符号链接：{path}")
    source = path.resolve(strict=True)
    if source.parent != root:
        raise ValueError(f"源文件不在所选目录顶层：{path}")
    return source


def _validate_target_directory(root: Path, target_directory: Path) -> None:
    if not _safe_directory_chain(root, target_directory):
        raise ValueError(f"目标目录不安全或指向所选目录之外：{target_directory}")


def _safe_directory_chain(root: Path, directory: Path) -> bool:
    """Reject a directory chain that leaves the root or passes through a symlink."""
    try:
        if not directory.resolve(strict=False).is_relative_to(root):
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


def plan_warning(target: Path, review_note: str = "") -> str | None:
    """Return the reason this target cannot run, or ``None`` when it is safe."""
    if review_note:
        return f"{review_note}；尚未确认，执行时会跳过"
    if target.is_symlink():
        return "目标路径是符号链接，不能执行"
    if target.exists():
        return "目标位置已存在同名文件，执行时会跳过"
    if any(parent.exists() and not parent.is_dir() for parent in target.parents if parent != target.anchor):
        return "目标路径的上级位置已存在非目录文件"
    return None
