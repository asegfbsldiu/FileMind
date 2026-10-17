"""Create a self-contained EPUB 3 from plain text, without remote resources."""

from html import escape
from pathlib import Path
from threading import Event
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from filemind.conversion.base import check_cancel


def write_epub(text: str, output: Path, cancel: Event) -> None:
    """Build a real EPUB container; scripts and markup remain escaped text."""
    check_cancel(cancel)
    identifier = f"urn:uuid:{uuid4()}"
    lines = (f"<p>{escape(line) or '&#160;'}</p>" for line in text.splitlines())
    chapter = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<html xmlns="http://www.w3.org/1999/xhtml" lang="zh-CN"><head>'
               '<title>文本内容</title></head><body>' + "".join(lines) + '</body></html>')
    package = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               f'<dc:identifier id="book">{identifier}</dc:identifier><dc:title>文本内容</dc:title>'
               '<dc:language>zh-CN</dc:language><meta property="dcterms:modified">2000-01-01T00:00:00Z</meta>'
               '</metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
               '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
               '</manifest><spine><itemref idref="chapter"/></spine></package>')
    container = ('<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                 '<rootfiles><rootfile full-path="book/package.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    nav = ('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
           '<head><title>目录</title></head><body><nav epub:type="toc"><ol><li>'
           '<a href="chapter.xhtml">文本内容</a></li></ol></nav></body></html>')
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        for name, content in (("META-INF/container.xml", container), ("book/package.opf", package),
                              ("book/chapter.xhtml", chapter), ("book/nav.xhtml", nav)):
            check_cancel(cancel)
            archive.writestr(name, content)
