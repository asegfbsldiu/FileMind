"""Route adapters while keeping publication safety in the service."""

from pathlib import Path
from threading import Event

from filemind.conversion.base import ConversionError, Progress, check_archive
from filemind.conversion.models import ConversionTarget


def inspect_extra(source: Path) -> tuple[str, str, tuple[ConversionTarget, ...]] | None:
    """Discover implemented local targets for a selected non-raster input."""
    from filemind.conversion.documents import inspect_document
    from filemind.conversion.media import DEMUXERS, inspect_media
    from filemind.conversion.office import office_targets
    suffix = source.suffix.lower()
    if suffix in {".ttf", ".otf", ".woff", ".woff2"}:
        from filemind.conversion.fonts import inspect_font
        return inspect_font(source)
    if suffix == ".pdf":
        from filemind.conversion.pdf import inspect_pdf
        return inspect_pdf(source)
    if suffix in DEMUXERS:
        return inspect_media(source)
    if suffix == ".epub":
        check_archive(source)
        target = ConversionTarget("epub_text", "EPUB → TXT", ".txt", "按阅读顺序提取 UTF-8 章节文字；不移除 DRM，不读取外链。")
        return "epub", "EPUB · 本地章节文字提取", (target,)
    document = inspect_document(source)
    external = office_targets(source)
    if document:
        kind, description, targets = document
        return kind, description, targets + external
    if external:
        return "office", "本机 LibreOffice · 实验性排版转换", external
    return None


def write_extra(source: Path, key: str, staging: Path, progress: Progress, cancel: Event) -> None:
    """Delegate only registered operations; adapters cannot publish files."""
    if key.startswith("font_"):
        from filemind.conversion.fonts import convert_font
        convert_font(source, key, staging, progress, cancel)
    elif key.startswith("pdf_"):
        from filemind.conversion.pdf import convert_pdf
        convert_pdf(source, key, staging, progress, cancel)
    elif key.startswith(("office_", "sheet_")):
        from filemind.conversion.documents import convert_document
        convert_document(source, key, staging, progress, cancel)
    elif key.startswith("lo_"):
        from filemind.conversion.office import convert_office
        convert_office(source, key, staging, progress, cancel)
    elif key.startswith("media_"):
        from filemind.conversion.media import convert_media
        convert_media(source, key, staging, progress, cancel)
    elif key == "epub_text":
        from filemind.conversion.text import convert_epub
        convert_epub(source, staging, progress, cancel)
    else:
        raise ConversionError("未注册这个本地转换操作。")
