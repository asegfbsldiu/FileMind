"""Font container conversions without changing outlines, names or licensing."""

from pathlib import Path
from threading import Event

from fontTools.ttLib import TTFont, TTLibError

from filemind.conversion.base import ConversionError, Progress, check_cancel
from filemind.conversion.models import ConversionTarget
from filemind.conversion.font_limits import validate_compressed_font


FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2"}
MAX_FONT_BYTES = 16 * 1024 * 1024


def _validate_header(source: Path) -> None:
    if source.stat().st_size > MAX_FONT_BYTES:
        raise ConversionError("字体超过 16 MB 限制。")
    with source.open("rb") as stream:
        header = stream.read(48)
    if len(header) < 12 or header[:4] not in {b"\x00\x01\x00\x00", b"OTTO", b"wOFF", b"wOF2"}:
        raise ConversionError("不是受支持的 TTF、OTF、WOFF 或 WOFF2 字体；暂不处理字体集合。")
    compressed = header[:4] in {b"wOFF", b"wOF2"}
    table_count = int.from_bytes(header[12:14] if compressed else header[4:6], "big")
    if table_count > 256 or (compressed and (len(header) < 48 or int.from_bytes(header[16:20], "big") > 64 * 1024 * 1024)):
        raise ConversionError("字体展开后过大或表数量超过限制。")
    if compressed:
        validate_compressed_font(source.read_bytes())


def inspect_font(source: Path) -> tuple[str, str, tuple[ConversionTarget, ...]]:
    """Inspect the real outline type; never offer a fake TTF/OTF rename."""
    _validate_header(source)
    try:
        with TTFont(source, lazy=True) as font:
            native = "otf" if font.sfntVersion == "OTTO" else "ttf"
            current = font.flavor or native
        keys = [key for key in (native, "woff", "woff2") if key != current]
        targets = tuple(ConversionTarget(f"font_{key}", f"字体 → {key.upper()}", f".{key}",
                        "重新编码字体容器，保留原始字形；不转换 TTF/CFF 轮廓，不修改字体授权。") for key in keys)
        return "font", f"{current.upper()} 字体 · {native.upper()} 字形 · 本地 fontTools", targets
    except (TTLibError, OSError, ValueError) as error:
        raise ConversionError("字体损坏、压缩格式不受支持或 Brotli 不可用。") from error


def convert_font(source: Path, key: str, staging: Path, progress: Progress, cancel: Event) -> None:
    """Re-encode a validated font into the caller's protected staging file."""
    _validate_header(source)
    check_cancel(cancel)
    try:
        with TTFont(source, lazy=False, recalcTimestamp=False) as font:
            native = "otf" if font.sfntVersion == "OTTO" else "ttf"
            target = key.removeprefix("font_")
            if target not in {native, "woff", "woff2"}:
                raise ConversionError("不能通过改变容器实现 TTF 与 CFF 字形互转。")
            font.flavor = target if target in {"woff", "woff2"} else None
            font.save(staging)
    except (TTLibError, OSError, ValueError) as error:
        raise ConversionError("字体转换失败；源文件未修改。") from error
    check_cancel(cancel)
    progress(1, 1)
