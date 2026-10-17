"""Typed, path-free request metadata sent to external model providers."""

from dataclasses import dataclass
from hashlib import sha256

from filemind.models import FileInfo, FileSuggestion


@dataclass(frozen=True)
class AIFileMetadata:
    """Minimum file metadata needed for model suggestions."""

    file_id: str
    file_name: str
    extension: str
    size_bytes: int
    modified_ns: int
    content_excerpt: str = ""
    image_data_url: str = ""
    content_note: str = ""


@dataclass(frozen=True)
class AIBatchFailure:
    """Visible failure associated with the affected batch's stable IDs."""

    file_ids: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class AIOrganizationResult:
    """Validated suggestions plus any batch-level failures."""

    suggestions: dict[str, FileSuggestion]
    failures: tuple[AIBatchFailure, ...]


def file_metadata(file_info: FileInfo) -> AIFileMetadata:
    """Build a stable, non-path identifier and minimal request metadata."""
    identifier = sha256(file_info.name.encode("utf-8")).hexdigest()[:20]
    return AIFileMetadata(f"f_{identifier}", file_info.name, file_info.suffix, file_info.size_bytes,
                          file_info.modified_ns)
