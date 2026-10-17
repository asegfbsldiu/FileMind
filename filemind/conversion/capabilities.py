"""Truthful local capabilities, with optional background codec discovery."""

from dataclasses import dataclass
from importlib.util import find_spec
import shutil

from PIL import Image

from filemind.conversion.images import RASTER_SUFFIXES, image_targets
from filemind.conversion.office import office_binary


@dataclass(frozen=True)
class FormatCapability:
    """Describe an installed adapter and its actual limits."""

    title: str
    inputs: str
    outputs: str
    state: str
    detail: str
    tint: str
    available: bool = True


def capabilities(detect_codecs: bool = False) -> tuple[FormatCapability, ...]:
    """Probe media encoders only when explicitly called from a background task."""
    pdf = find_spec("pypdfium2") is not None
    media = bool(shutil.which("ffmpeg")) or find_spec("imageio_ffmpeg") is not None
    office = office_binary() is not None
    fonts = find_spec("fontTools") is not None and find_spec("brotli") is not None
    Image.init()
    extensions = Image.registered_extensions()
    image_inputs = ", ".join(suffix[1:].upper() for suffix in sorted(RASTER_SUFFIXES)
                             if extensions.get(suffix) in Image.OPEN)
    image_outputs = ", ".join(target.extension[1:].upper() for target in image_targets())
    audio_outputs, video_outputs = _media_outputs(media, detect_codecs)
    catalog = (
        FormatCapability("图片", image_inputs, image_outputs, "单帧转换",
                         "重新编码像素，ICO 等比留白；JPEG/AVIF 有损。动图、多页图片不转换。", "mint"),
        FormatCapability("文本与电子书", "TXT, MD, HTML, JSON, CSV, XML, YAML, EPUB",
                         "TXT, HTML, DOCX, EPUB, JSON, YAML, CSV, XLSX", "本机处理",
                         "目标按输入类型显示。EPUB 可创建或提取章节；不移除 DRM。", "blue"),
        FormatCapability("Word 文档", "DOCX", "TXT, HTML", "文字提取",
                         "提取段落、表格文字，不保留页面排版和图片。", "amber"),
        FormatCapability("Excel 表格", "XLSX, CSV", "JSON, CSV (ZIP), XLSX", "值导出",
                         "按工作表导出已有值，不计算公式，不保留样式。", "mint"),
        FormatCapability("PPT 演示", "PPTX", "TXT, HTML", "文字提取",
                         "按页提取文本框，不导出动画、备注或页面图像。", "blue"),
        FormatCapability("PDF", "PDF", "TXT, DOCX, HTML, PNG (ZIP), JPEG (ZIP)", "文本 / 页面图像",
                         "最多 100 页。DOCX/HTML 为文本重建，不保留排版；无 OCR。", "amber", pdf),
        FormatCapability("音频", "MP3, WAV, FLAC, OGG, OPUS, AAC, M4A, WMA",
                         audio_outputs, "编码器已检测" if detect_codecs else "后台检测中",
                         "本机重新编码首条音轨；有损目标会损失音质，不保留全部元数据。", "mint",
                         media and bool(audio_outputs)),
        FormatCapability("视频", "MP4, MOV, MKV, WEBM, AVI, WMV, FLV, MPG, MPEG, M2TS",
                         video_outputs, "编码器已检测" if detect_codecs else "后台检测中",
                         "重新编码首条视频/音轨，或提取音轨；不保留字幕和全部元数据。", "blue",
                         media and bool(video_outputs)),
        FormatCapability("字体容器", "TTF, OTF, WOFF, WOFF2", "WOFF, WOFF2, 原始 TTF/OTF",
                         "容器转换", "保留字形；不做 TTF/CFF 轮廓互转。请遵守字体自身授权。", "lavender", fonts),
        FormatCapability("Office 排版", "DOC, DOCX, ODT, RTF, XLS, XLSX, ODS, PPT, PPTX, ODP",
                         "PDF, DOCX, ODT, RTF, XLSX, ODS, PPTX, ODP", "实验性",
                         "按文档类别转换，依赖本机 LibreOffice，复杂排版需核对。", "amber", office),
        FormatCapability("任意普通文件", "用户主动选择的单个文件", "ZIP", "本机压缩",
                         "另存压缩包，保留源文件；不递归目录、不自动解压。", "mint"),
    )
    return tuple(item for item in catalog if item.available)


def _media_outputs(installed: bool, detect: bool) -> tuple[str, str]:
    if not installed:
        return "", ""
    if not detect:
        return "正在检测本机编码器…", "正在检测本机编码器…"
    from filemind.conversion.media import available_media_extensions
    audio = ", ".join(available_media_extensions(False))
    video = ", ".join(available_media_extensions(True))
    return audio, (video + (", 音轨提取" if audio else "")) if video else ""
