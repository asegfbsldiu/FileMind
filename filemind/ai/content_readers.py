"""Read bounded text from in-memory document snapshots, without external links."""

import io
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException


def document_excerpt(data: bytes, suffix: str, limit: int) -> str:
    """Read at most three PDF pages or bounded OOXML text, never macros/links."""
    try:
        return _pdf_excerpt(data, limit) if suffix == ".pdf" else _office_excerpt(data, suffix, limit)
    except (BadZipFile, KeyError, ParseError, DefusedXmlException, RuntimeError) as error:
        raise ValueError("文档损坏、加密或内容不受支持，未发送正文。") from error


def _office_excerpt(data: bytes, suffix: str, limit: int) -> str:
    prefixes = {".docx": ("word/document.xml",), ".pptx": ("ppt/slides/slide",),
                ".xlsx": ("xl/sharedStrings.xml", "xl/worksheets/sheet")}[suffix]
    pieces: list[str] = []
    length = 0
    with ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 3000 or sum(item.file_size for item in entries) > 64 * 1024 * 1024:
            raise ValueError("文档展开后过大，未读取。")
        for entry in sorted(entries, key=lambda item: item.filename):
            if not entry.filename.endswith(".xml") or not entry.filename.startswith(prefixes):
                continue
            if entry.file_size > 2 * 1024 * 1024:
                raise ValueError("文档内部文本超过 2 MB，未读取。")
            root = ElementTree.fromstring(archive.read(entry), forbid_dtd=True)
            for node in root.iter():
                if node.tag.rsplit("}", 1)[-1] in {"t", "v"} and node.text:
                    pieces.append(node.text[:limit])
                    length += len(pieces[-1]) + 1
                    if length >= limit:
                        return " ".join(pieces)[:limit]
    return " ".join(pieces)[:limit]


def _pdf_excerpt(data: bytes, limit: int) -> str:
    import pypdfium2 as pdfium
    from filemind.conversion.pdf import PDF_LOCK

    pieces: list[str] = []
    with PDF_LOCK, pdfium.PdfDocument(data) as document:
        for index in range(min(3, len(document))):
            page = document[index]
            try:
                text = page.get_textpage()
                try:
                    count = min(limit, text.count_chars())
                    pieces.append(text.get_text_range(0, count) if count else "")
                finally:
                    text.close()
            finally:
                page.close()
    return "\n".join(pieces)[:limit]
