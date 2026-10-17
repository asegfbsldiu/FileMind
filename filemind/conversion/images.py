"""Real single-frame image conversion with installed Pillow codecs."""

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from filemind.conversion.base import ConversionError
from filemind.conversion.models import ConversionTarget


RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff",
                   ".avif", ".ico", ".tga", ".pcx", ".ppm", ".pgm", ".pbm"}
FORMATS = {"png": ("PNG", ".png"), "jpeg": ("JPEG", ".jpg"), "webp": ("WEBP", ".webp"),
           "bmp": ("BMP", ".bmp"), "tiff": ("TIFF", ".tiff"), "gif": ("GIF", ".gif"), "avif": ("AVIF", ".avif"),
           "ico": ("ICO", ".ico"), "tga": ("TGA", ".tga"), "pcx": ("PCX", ".pcx"), "ppm": ("PPM", ".ppm")}


def image_targets() -> tuple[ConversionTarget, ...]:
    """Expose codecs registered in this installation rather than sample options."""
    Image.init()
    return tuple(ConversionTarget(key, name, extension,
                 "仅单帧；JPEG/AVIF 有损，GIF 最多 256 色；不承诺保留 EXIF、色彩配置和全部元数据。")
                 for key, (name, extension) in FORMATS.items() if name in Image.SAVE) + (
        ConversionTarget("pdf", "图片 → 单页 PDF", ".pdf", "图片置入单页 PDF；不提供 OCR 或可编辑文档。"),)


def inspect_image(source: Path) -> tuple[str, str, tuple[ConversionTarget, ...]]:
    """Read headers before any full image allocation."""
    try:
        with Image.open(source) as image:
            _validate_image(image)
            return "image", f"{image.format} · {image.width} × {image.height}", image_targets()
    except (UnidentifiedImageError, OSError) as error:
        raise ConversionError("无法识别这张图片的真实格式，或当前解码插件不可用。") from error


def _validate_image(image: Image.Image) -> None:
    if image.width * image.height > 32_000_000:
        raise ConversionError("图片超过 3200 万像素限制。")
    if getattr(image, "n_frames", 1) > 1:
        raise ConversionError("暂不转换动图或多页图片，避免静默丢失帧或页面。")


def convert_image(source: Path, key: str, staging: Path) -> None:
    """Re-encode pixels, including explicit white flattening for JPEG/PDF."""
    with Image.open(source) as original:
        _validate_image(original)
        image = ImageOps.exif_transpose(original)
        try:
            if key == "ico":
                image.thumbnail((256, 256))
                padded = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
                padded.paste(image, ((256 - image.width) // 2, (256 - image.height) // 2))
                image.close()
                image = padded
            if key in {"jpeg", "pdf", "pcx", "ppm"}:
                flattened = Image.new("RGB", image.size, "white")
                if "A" in image.getbands() or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    flattened.paste(rgba, mask=rgba.getchannel("A"))
                    rgba.close()
                else:
                    flattened.paste(image.convert("RGB"))
                image.close()
                image = flattened
            format_name = "PDF" if key == "pdf" else FORMATS[key][0]
            image.save(staging, format=format_name)
        finally:
            image.close()
