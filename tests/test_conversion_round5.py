"""Real extra formats using disposable generated fonts, images and text."""

from pathlib import Path
from threading import Event
from zipfile import ZipFile, ZIP_STORED

import pytest
import brotli
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QLabel

from filemind.conversion import media
from filemind.conversion import font_limits
from filemind.conversion.base import ConversionError
from filemind.conversion.capabilities import capabilities
from filemind.conversion.service import convert_file, inspect_input
from filemind.ui.pages.conversion_page import ConversionPage
from filemind.ui.styles.theme import apply_theme
from tests.test_extended_conversion import create_text_pdf, assert_media_decodes


def convert(source: Path, key: str, output: Path):
    return convert_file(inspect_input(source), key, output, lambda *_: None, Event())


def create_font(output: Path) -> None:
    """Generate a tiny licensed-by-this-test font rather than reading OS fonts."""
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A"])
    builder.setupCharacterMap({65: "A"})
    pen = TTGlyphPen(None)
    pen.moveTo((100, 0))
    pen.lineTo((300, 700))
    pen.lineTo((500, 0))
    pen.closePath()
    builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()})
    builder.setupHorizontalMetrics({".notdef": (500, 0), "A": (600, 100)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupNameTable({"familyName": "FileMind Generated", "styleName": "Regular"})
    builder.setupPost()
    builder.save(output)


@pytest.mark.parametrize("flavor", ["woff", "woff2"])
def test_real_font_container_roundtrip_retains_glyphs(tmp_path: Path, flavor: str) -> None:
    source = tmp_path / "generated.ttf"
    create_font(source)
    options = {target.key for target in inspect_input(source).targets}
    assert {"font_woff", "font_woff2"} <= options
    assert "font_otf" not in options
    compressed = tmp_path / f"generated.{flavor}"
    convert(source, f"font_{flavor}", compressed)
    assert compressed.read_bytes()[:4] == (b"wOFF" if flavor == "woff" else b"wOF2")
    restored = tmp_path / f"restored-{flavor}.ttf"
    convert(compressed, "font_ttf", restored)
    with TTFont(restored) as font:
        assert font.getBestCmap() == {65: "A"}
        assert "glyf" in font and font.flavor is None


def test_invalid_font_cannot_masquerade_as_conversion(tmp_path: Path) -> None:
    source = tmp_path / "not-font.ttf"
    source.write_text("not a font", encoding="utf-8")
    with pytest.raises(ConversionError, match="字体"):
        inspect_input(source)


def test_compressed_font_expansion_is_bounded_before_fonttools(tmp_path: Path) -> None:
    from unittest.mock import patch
    from filemind.conversion.fonts import inspect_font

    source = tmp_path / "generated.ttf"
    create_font(source)
    compressed = tmp_path / "generated.woff2"
    convert(source, "font_woff2", compressed)
    with patch.object(font_limits, "MAX_EXPANDED", 16), \
            patch("filemind.conversion.fonts.TTFont", side_effect=AssertionError("must reject before library decode")):
        with pytest.raises(ConversionError, match="大小|超过|超限"):
            inspect_font(compressed)
    with patch.object(font_limits, "MAX_EXPANDED", 64):
        with pytest.raises(ConversionError, match="超过"):
            font_limits._brotli_size(brotli.compress(b"x" * 10000))


@pytest.mark.parametrize("key,extension,expected", [
    ("ico", ".ico", "ICO"), ("tga", ".tga", "TGA"), ("pcx", ".pcx", "PCX"), ("ppm", ".ppm", "PPM"),
])
def test_added_raster_targets_are_reencoded_and_aspect_safe(tmp_path: Path, key: str, extension: str, expected: str) -> None:
    source = tmp_path / "source.png"
    with Image.new("RGBA", (100, 50), (255, 0, 0, 180)) as image:
        image.save(source)
    output = tmp_path / f"converted{extension}"
    convert(source, key, output)
    with Image.open(output) as image:
        image.load()
        assert image.format == expected
        if key == "ico":
            assert image.size == (256, 256)
            assert image.getpixel((128, 0))[3] == 0
            assert image.getpixel((128, 128))[0] == 255
        else:
            assert image.size == (100, 50)


def test_plain_text_epub_is_real_safe_archive_and_roundtrips(tmp_path: Path) -> None:
    source = tmp_path / "lesson.txt"
    source.write_text("数据结构\n<重点>&二叉树\n第二章", encoding="utf-8")
    epub = tmp_path / "lesson.epub"
    convert(source, "text_epub", epub)
    with ZipFile(epub) as archive:
        assert archive.infolist()[0].filename == "mimetype"
        assert archive.infolist()[0].compress_type == ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"
        chapter = archive.read("book/chapter.xhtml").decode()
        assert "&lt;重点&gt;&amp;" in chapter
    text = tmp_path / "restored.txt"
    convert(epub, "epub_text", text)
    assert "<重点>&二叉树" in text.read_text(encoding="utf-8")


@pytest.mark.parametrize("key,extension", [("pdf_docx", ".docx"), ("pdf_html", ".html")])
def test_pdf_text_rebuilt_as_real_document(tmp_path: Path, key: str, extension: str) -> None:
    source = tmp_path / "source.pdf"
    create_text_pdf(source)
    output = tmp_path / f"converted{extension}"
    convert(source, key, output)
    if key == "pdf_docx":
        from docx import Document
        text = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
    else:
        text = output.read_text(encoding="utf-8")
        assert "<section>" in text
    assert "Generated PDF page 1" in text and "Generated PDF page 2" in text


@pytest.mark.parametrize("key,extension", [("media_aac", ".aac"), ("media_m4a", ".m4a"),
                                          ("media_opus", ".opus"), ("media_wma", ".wma")])
def test_new_audio_outputs_are_decodable(tmp_path: Path, key: str, extension: str) -> None:
    import wave
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(48000)
        stream.writeframes(b"\x00\x00" * 4800)
    binary = media.ffmpeg_binary()
    assert binary, "The declared FFmpeg dependency must be available in this environment"
    assert key in {target.key for target in inspect_input(source).targets}
    output = tmp_path / f"converted{extension}"
    convert(source, key, output)
    assert "Audio:" in assert_media_decodes(binary, output)


def test_mov_output_is_a_real_playable_video(tmp_path: Path) -> None:
    import subprocess

    binary = media.ffmpeg_binary()
    assert binary
    source = tmp_path / "generated.mp4"
    generated = subprocess.run(
        [binary, "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i", "color=c=blue:s=32x24:r=5:d=0.4",
         "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
        capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert generated.returncode == 0, generated.stderr.decode(errors="replace")
    output = tmp_path / "converted.mov"
    convert(source, "media_mov", output)
    assert "Video: h264" in assert_media_decodes(binary, output)


def test_format_lists_use_commas_and_list_installed_encoders_only() -> None:
    cards = capabilities(detect_codecs=True)
    assert {"字体容器", "图片", "音频", "视频", "文本与电子书"} <= {item.title for item in cards}
    assert all(" · " not in item.inputs + item.outputs and "等" not in item.inputs + item.outputs for item in cards)
    audio = next(item for item in cards if item.title == "音频")
    assert set(audio.outputs.split(", ")) == set(media.available_media_extensions(False))


@pytest.mark.parametrize("width,height", [(1024, 700), (1280, 850), (600, 700)])
def test_qss_steps_and_responsive_cards_are_not_clipped(width: int, height: int) -> None:
    apply_theme(QApplication.instance())
    page = ConversionPage()
    page.resize(width, height)
    page.show()
    loop = QEventLoop()
    QTimer.singleShot(200, loop.quit)
    loop.exec()
    assert page.steps_label.height() >= page.steps_label.heightForWidth(page.steps_label.width())
    assert page.workspace_holder.height() >= 340
    assert not page.convert_button.isEnabled()
    labels = page.findChildren(QLabel, "CapabilityDetail")
    assert labels and any(", " in label.text() for label in labels)
    assert page.minimumSizeHint().width() <= width
    page.close()
