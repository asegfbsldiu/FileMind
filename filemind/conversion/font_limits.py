"""Bound compressed font streams before fontTools allocates decoded tables."""

import io
import zlib

import brotli
from fontTools.ttLib import TTLibError
from fontTools.ttLib.woff2 import WOFF2DirectoryEntry

from filemind.conversion.base import ConversionError


MAX_EXPANDED = 64 * 1024 * 1024


def validate_compressed_font(data: bytes) -> None:
    """Validate declared table sizes and independently bound actual expansion."""
    signature = data[:4]
    if signature not in {b"wOFF", b"wOF2"}:
        return
    try:
        if signature == b"wOF2":
            _validate_woff2(data)
        else:
            _validate_woff(data)
        offset = 28 if signature == b"wOF2" else 24
        meta_offset = int.from_bytes(data[offset:offset + 4], "big")
        meta_length = int.from_bytes(data[offset + 4:offset + 8], "big")
        original_length = int.from_bytes(data[offset + 8:offset + 12], "big")
        if original_length > MAX_EXPANDED:
            raise ConversionError("字体元数据展开后超过限制。")
        if meta_length:
            block = _slice(data, meta_offset, meta_length)
            expanded = _brotli_size(block) if signature == b"wOF2" else len(_inflate(block))
            if expanded != original_length:
                raise ConversionError("字体元数据长度无效。")
    except (brotli.error, zlib.error, TTLibError, EOFError, ValueError) as error:
        raise ConversionError("字体压缩数据损坏或展开后超限。") from error


def _slice(data: bytes, offset: int, length: int) -> bytes:
    if offset < 0 or length <= 0 or offset + length > len(data):
        raise ConversionError("字体压缩块超出文件范围。")
    return data[offset:offset + length]


def _brotli_size(data: bytes) -> int:
    decoder = brotli.Decompressor()
    total = 0
    for offset in range(0, len(data), 16384):
        chunk = data[offset:offset + 16384]
        while True:
            total += len(decoder.process(chunk, output_buffer_limit=1024 * 1024))
            if total > MAX_EXPANDED:
                raise ConversionError("字体展开后超过 64 MB 限制。")
            if decoder.can_accept_more_data():
                break
            chunk = b""
    if not decoder.is_finished():
        raise ConversionError("字体 Brotli 数据不完整。")
    return total


def _inflate(data: bytes) -> bytes:
    decoder = zlib.decompressobj()
    expanded = decoder.decompress(data, MAX_EXPANDED + 1)
    if len(expanded) > MAX_EXPANDED or not decoder.eof or decoder.unused_data:
        raise ConversionError("字体压缩数据不完整或展开后超限。")
    return expanded


def _validate_woff2(data: bytes) -> None:
    stream = io.BytesIO(data)
    stream.seek(48)
    total = 0
    for _index in range(int.from_bytes(data[12:14], "big")):
        entry = WOFF2DirectoryEntry()
        entry.fromFile(stream)
        total += max(entry.length, entry.origLength)
        if total > MAX_EXPANDED:
            raise ConversionError("字体表总大小超过 64 MB。")
    compressed_length = int.from_bytes(data[20:24], "big")
    _brotli_size(_slice(data, stream.tell(), compressed_length))


def _validate_woff(data: bytes) -> None:
    total = 0
    for index in range(int.from_bytes(data[12:14], "big")):
        entry = _slice(data, 44 + index * 20, 20)
        offset, length, original = (int.from_bytes(entry[start:start + 4], "big") for start in (4, 8, 12))
        total += original
        if total > MAX_EXPANDED or length > original:
            raise ConversionError("字体表大小无效或展开后超过 64 MB。")
        if length == original == 0:
            continue
        block = _slice(data, offset, length)
        if length < original and len(_inflate(block)) != original:
            raise ConversionError("字体表展开长度与声明不一致。")
