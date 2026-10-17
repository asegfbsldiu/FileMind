"""Bounded local image/text/structured-data conversion without overwrites."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from threading import Event


from filemind.conversion.models import ConversionInput, ConversionResult, ConversionTarget
from filemind.conversion.base import ConversionError, Progress
from filemind.conversion.images import RASTER_SUFFIXES, inspect_image, convert_image
from filemind.conversion.text import TEXT_SUFFIXES, EXTRA_TARGETS, extra_text_targets, write_transformed
from filemind.conversion.adapters import inspect_extra, write_extra


MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_TEXT_BYTES = 8 * 1024 * 1024
ZIP = ConversionTarget("zip", "ZIP 打包（保留源文件）", ".zip", "只将当前选中的一个文件压缩，不解压、不递归目录。")
UTF8 = ConversionTarget("utf8", "UTF-8 文本", ".txt", "支持 UTF-8 或带 BOM 的 UTF-16 输入；不解析 PDF / Office。")
UTF16 = ConversionTarget("utf16", "UTF-16 文本", ".txt", "输出带 BOM 的 UTF-16；代码文件按纯文本处理。")
JSON = ConversionTarget("json", "JSON", ".json", "CSV 转字符串记录列表，或格式化已有 JSON；不猜测字段类型。")
CSV = ConversionTarget("csv", "CSV", ".csv", "仅支持由扁平对象组成的 JSON 数组，不展开嵌套字段。")


def fingerprint(path: Path) -> tuple[int, int, int, int]:
    """Snapshot identity, size and modification time without reading contents."""
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _check_cancel(cancel: Event) -> None:
    if cancel.is_set():
        raise InterruptedError("转换已取消，未发布输出文件。")






def inspect_input(source: Path) -> ConversionInput:
    """Discover only locally implemented formats for one explicitly chosen file."""
    if source.is_symlink() or not source.is_file():
        raise ConversionError("请选择普通文件；不接受文件夹或符号链接。")
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise ConversionError("第一版单文件上限为 64 MB。")
    source = source.resolve(strict=True)
    suffix = source.suffix.lower()
    if suffix in RASTER_SUFFIXES:
        kind, description, targets = inspect_image(source)
        return ConversionInput(source, kind, description, targets + (ZIP,), fingerprint(source))
    if suffix in TEXT_SUFFIXES:
        if source.stat().st_size > MAX_TEXT_BYTES:
            raise ConversionError("文本转换上限为 8 MB；较大文件请使用其他本地工具。")
        targets = (UTF8, UTF16) + ((JSON,) if suffix == ".csv" else
                                   (JSON, CSV) if suffix == ".json" else ()) + extra_text_targets(suffix) + (ZIP,)
        return ConversionInput(source, "text", f"{suffix[1:].upper()} 文本 · 转换时验证编码", targets, fingerprint(source))
    extra = inspect_extra(source)
    if extra:
        kind, description, targets = extra
        return ConversionInput(source, kind, description, targets + (ZIP,), fingerprint(source))
    description = "此格式未集成内容转换；当前可用 ZIP 打包"
    return ConversionInput(source, "other", description, (ZIP,), fingerprint(source))


def _decode_text(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > MAX_TEXT_BYTES:
        raise ConversionError("文本超过 8 MB 限制。")
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        text = data.decode(encoding)
    except UnicodeError as error:
        raise ConversionError("文件不是 UTF-8 或带 BOM 的 UTF-16；未猜测编码或替换乱码。") from error
    if "\x00" in text:
        raise ConversionError("检测到二进制或不支持的文本编码。")
    return text


def _csv_to_json(text: str) -> str:
    rows = csv.reader(io.StringIO(text))
    header = next(rows, [])
    if not header:
        return "[]\n"
    if any(not key.strip() for key in header) or len(set(header)) != len(header):
        raise ConversionError("CSV 表头为空或重复，无法安全转换为 JSON。")
    records = []
    for row in rows:
        if not row:
            continue
        if len(row) != len(header):
            raise ConversionError("CSV 行的列数与表头不一致。")
        records.append(dict(zip(header, row)))
    return json.dumps(records, ensure_ascii=False, indent=2) + "\n"


def _json_to_csv(value: object) -> str:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ConversionError("JSON 转 CSV 需要由扁平对象组成的数组。")
    if any(isinstance(field, (dict, list)) for item in value for field in item.values()):
        raise ConversionError("JSON 含有嵌套字段，未进行可能丢失数据的展开。")
    columns = list(dict.fromkeys(key for item in value for key in item))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    if columns:
        writer.writeheader()
        writer.writerows(value)
    return stream.getvalue()


def _write_text(item: ConversionInput, key: str, staging: Path) -> None:
    text = _decode_text(item.path)
    if key in {"json", "csv"}:
        if item.path.suffix.lower() == ".csv":
            text = _csv_to_json(text)
        else:
            value = json.loads(text)
            text = _json_to_csv(value) if key == "csv" else json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    staging.write_bytes(text.encode("utf-16" if key == "utf16" else "utf-8"))




def _write_zip(item: ConversionInput, staging: Path, progress: Progress, cancel: Event) -> None:
    total = item.fingerprint[2]
    completed = 0
    with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        with item.path.open("rb") as source, archive.open(item.path.name, "w") as target:
            while block := source.read(1024 * 1024):
                _check_cancel(cancel)
                target.write(block)
                completed += len(block)
                progress(completed, max(total, 1))


def _validate_output(source: Path, output: Path, extension: str) -> None:
    if output.absolute() == source or output.exists() or output.is_symlink():
        raise ConversionError("输出位置已存在文件或与源文件相同，请选择新名称；不会覆盖。")
    if output.suffix.lower() != extension:
        raise ConversionError(f"输出扩展名必须为 {extension}。")
    if not output.parent.is_dir():
        raise ConversionError("输出目录不存在，请先选择有效的保存位置。")
    if any(parent.is_symlink() or parent.is_junction() for parent in output.parents):
        raise ConversionError("输出目录不能经过符号链接或目录联接。")


def convert_file(item: ConversionInput, target_key: str, output: Path,
                 progress: Progress, cancel: Event) -> ConversionResult:
    """Convert to a staging file and atomically publish without overwriting."""
    _check_cancel(cancel)
    current = inspect_input(item.path)
    if current.fingerprint != item.fingerprint:
        raise ConversionError("源文件在选择后发生了变化，请重新选择。")
    target = next((option for option in current.targets if option.key == target_key), None)
    if target is None:
        raise ConversionError("当前文件或本机环境不支持这个目标格式。")
    output = output.absolute()
    _validate_output(item.path, output, target.extension)
    try:
        descriptor, name = tempfile.mkstemp(prefix=".filemind-convert-", dir=output.parent)
    except OSError as error:
        raise ConversionError("无法创建转换临时文件，请检查输出目录权限。") from error
    os.close(descriptor)
    staging = Path(name)
    try:
        progress(0, 100)
        if target_key == "zip":
            _write_zip(item, staging, progress, cancel)
        elif current.kind == "image":
            convert_image(item.path, target_key, staging)
        elif current.kind == "text" and target_key in EXTRA_TARGETS:
            write_transformed(_decode_text(item.path), target_key, staging, cancel)
        elif current.kind == "text":
            _write_text(item, target_key, staging)
        else:
            write_extra(item.path, target_key, staging, progress, cancel)
        _check_cancel(cancel)
        if fingerprint(item.path) != item.fingerprint:
            raise ConversionError("转换期间源文件发生变化，未发布结果。")
        _validate_output(item.path, output, target.extension)
        if os.name == "nt":
            os.rename(staging, output)
        else:
            os.link(staging, output)
        progress(100, 100)
        return ConversionResult(output, output.stat().st_size, target.title)
    except InterruptedError:
        raise
    except (OSError, ValueError, csv.Error) as error:
        raise ConversionError("转换失败：请检查输入内容、文件占用、输出冲突或目录权限。") from error
    finally:
        staging.unlink(missing_ok=True)
