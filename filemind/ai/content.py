"""Opt-in, bounded content snapshots for organization; no persistent contents."""

from __future__ import annotations

import base64
import io
import os
import re
from dataclasses import replace
from pathlib import Path
from threading import Event

from PIL import Image, ImageOps, UnidentifiedImageError

from filemind.ai.chat_attachments import TEXT_TYPES
from filemind.ai.content_readers import document_excerpt
from filemind.ai.schemas import AIBatchFailure, AIFileMetadata, file_metadata
from filemind.models import FileInfo
from filemind.storage.settings import AISettings


MAX_CONTENT_BYTES = 8 * 1024 * 1024
MAX_EXCERPT_CHARS = 1800
MAX_CONTENT_FILES = 128
MAX_JOB_IMAGE_CHARS = 12 * 1024 * 1024
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
DOCUMENT_SUFFIXES = {".pdf", ".docx", ".xlsx", ".pptx"}
SENSITIVE_NAMES = ("password", "secret", "credential", "api_key", "apikey", "id_rsa",
                   "access_token", "auth_token", "sk-", "sk_", "密钥", "秘钥", "密码", "私钥")
SECRET_VALUE = re.compile(
    r"(?i)(?:sk[-_][a-z0-9_-]{12,}|(?:api[_ -]?key|token|password|密码|密钥|秘钥)\s*[=:：]\s*[^\s,;\"']+)"
)


def supports_organization_images(settings: AISettings) -> bool:
    """Only expose an image protocol verified against this provider's docs."""
    return settings.provider_id == "deepseek" and settings.model == "deepseek-flash"


def prepare_content_metadata(
    root: Path, files: list[FileInfo], settings: AISettings, cancel: Event,
) -> tuple[list[AIFileMetadata], tuple[AIBatchFailure, ...]]:
    """Read selected regular files only after the controller obtains consent."""
    prepared: list[AIFileMetadata] = []
    failures: list[AIBatchFailure] = []
    image_chars = 0
    for index, info in enumerate(files):
        if cancel.is_set():
            raise InterruptedError("内容分析已取消")
        metadata = file_metadata(info)
        try:
            if index >= MAX_CONTENT_FILES:
                raise ValueError("本次内容识别最多 128 个文件；其余文件已明确跳过，请分批选择目录。")
            if info.suffix in IMAGE_SUFFIXES and image_chars >= MAX_JOB_IMAGE_CHARS:
                raise ValueError("本次图片总请求大小达到 12 MB，请分批处理。")
            item = _prepare_one(root, info, settings, metadata)
            if image_chars + len(item.image_data_url) > MAX_JOB_IMAGE_CHARS:
                raise ValueError("本次图片总请求大小达到 12 MB，请分批处理。")
            image_chars += len(item.image_data_url)
            prepared.append(item)
        except (OSError, ValueError) as error:
            message = str(error) if isinstance(error, ValueError) else "无法安全读取文件，请检查权限或重新扫描。"
            failures.append(AIBatchFailure((metadata.file_id,), message))
    return prepared, tuple(failures)


def _prepare_one(root: Path, info: FileInfo, settings: AISettings, item: AIFileMetadata) -> AIFileMetadata:
    name = info.name.casefold()
    if name.startswith(".env") or any(word in name for word in SENSITIVE_NAMES) or info.suffix in {".key", ".pem", ".pfx"}:
        raise ValueError("疑似凭据文件已排除；未读取正文，也未发送文件名。")
    if info.suffix in IMAGE_SUFFIXES and not supports_organization_images(settings):
        raise ValueError("当前模型未启用图片理解；本版支持 DeepSeek deepseek-flash，或改用元数据分类。")
    if info.suffix not in IMAGE_SUFFIXES | DOCUMENT_SUFFIXES | TEXT_TYPES:
        raise ValueError("此格式暂不支持内容识别；可改用文件名分类或本地规则。")
    data = _read_snapshot(root, info)
    if info.suffix in IMAGE_SUFFIXES:
        return replace(item, image_data_url=_image_snapshot(data), content_note="已授权图片缩略图；不含 EXIF")
    text = _text_snapshot(data, info.suffix)
    if "-----BEGIN " in text and "PRIVATE KEY-----" in text:
        raise ValueError("检测到私钥标识，已排除整个文件。")
    text = SECRET_VALUE.sub("[已遮蔽凭据]", text)[:MAX_EXCERPT_CHARS]
    if not text.strip():
        raise ValueError("没有可读取的文本；扫描版 PDF 暂不支持 OCR。")
    return replace(item, content_excerpt=text, content_note="已授权开头片段；可能截断，不代表全文")


def _read_snapshot(root: Path, info: FileInfo) -> bytes:
    path = info.path
    if path.is_symlink() or path.parent.resolve() != root.resolve() or not path.is_file():
        raise ValueError("文件已移出所选目录或为符号链接，未读取内容。")
    if not 0 < info.size_bytes <= MAX_CONTENT_BYTES:
        raise ValueError("内容识别仅支持非空且不超过 8 MB 的文件。")
    before = path.stat()
    if (before.st_size, before.st_mtime_ns) != (info.size_bytes, info.modified_ns):
        raise ValueError("扫描后文件发生变化，请重新读取文件列表。")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("文件在读取前被替换，已停止。")
        data = stream.read(MAX_CONTENT_BYTES + 1)
        after = os.fstat(stream.fileno())
    current = path.stat()
    if (_snapshot_fingerprint(after) != _snapshot_fingerprint(opened)
            or _snapshot_fingerprint(current) != _snapshot_fingerprint(before)
            or len(data) != info.size_bytes):
        raise ValueError("文件在读取期间发生变化，已丢弃内容。")
    return data


def _snapshot_fingerprint(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _text_snapshot(data: bytes, suffix: str) -> str:
    if suffix in DOCUMENT_SUFFIXES:
        return document_excerpt(data, suffix, MAX_EXCERPT_CHARS)
    try:
        encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        text = data.decode(encoding)[:MAX_EXCERPT_CHARS]
        if "\x00" in text:
            raise ValueError("文件含二进制内容，未作为文本发送。")
        return text
    except UnicodeError as error:
        raise ValueError("文本不是 UTF-8 或带 BOM 的 UTF-16，未发送乱码。") from error


def _image_snapshot(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as original:
            if original.width * original.height > 20_000_000 or getattr(original, "n_frames", 1) > 1:
                raise ValueError("图片超过 2000 万像素或包含多帧，暂不读取。")
            with ImageOps.exif_transpose(original) as oriented:
                oriented.thumbnail((1024, 1024))
                with oriented.convert("RGBA") as rgba, Image.new("RGB", rgba.size, "white") as image:
                    image.paste(rgba, mask=rgba.getchannel("A"))
                    with io.BytesIO() as buffer:
                        image.save(buffer, "JPEG", quality=75)
                        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        if len(encoded) > 512 * 1024:
            raise ValueError("图片压缩后仍超过 512 KB，未发送。")
        return f"data:image/jpeg;base64,{encoded}"
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("图片损坏或当前解码器不支持，未发送。") from error
