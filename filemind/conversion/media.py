"""Local FFmpeg adapters with explicit demuxers, codecs and cancellation."""

import re
import shutil
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from threading import Event

from filemind.conversion.base import ConversionError, Progress, check_cancel
from filemind.conversion.models import ConversionTarget


DEMUXERS = {".mp4": "mov", ".m4v": "mov", ".mov": "mov", ".m4a": "mov",
            ".mkv": "matroska", ".webm": "matroska", ".avi": "avi", ".wmv": "asf",
            ".mp3": "mp3", ".wav": "wav", ".flac": "flac", ".ogg": "ogg",
            ".opus": "ogg", ".aac": "aac", ".wma": "asf", ".flv": "flv", ".mpg": "mpeg",
            ".mpeg": "mpeg", ".m2ts": "mpegts"}
CODECS = {
    "media_mp3": ("MP3 音频", ".mp3", "libmp3lame", "mp3", ("-vn", "-c:a", "libmp3lame", "-q:a", "2")),
    "media_wav": ("WAV 音频", ".wav", "pcm_s16le", "wav", ("-vn", "-c:a", "pcm_s16le")),
    "media_flac": ("FLAC 音频", ".flac", "flac", "flac", ("-vn", "-c:a", "flac")),
    "media_ogg": ("Ogg Vorbis 音频", ".ogg", "libvorbis", "ogg", ("-vn", "-c:a", "libvorbis")),
    "media_aac": ("AAC 音频", ".aac", "aac", "adts", ("-vn", "-c:a", "aac")),
    "media_m4a": ("M4A 音频（AAC）", ".m4a", "aac", "ipod", ("-vn", "-c:a", "aac")),
    "media_opus": ("Opus 音频", ".opus", "libopus", "opus", ("-vn", "-c:a", "libopus")),
    "media_wma": ("WMA 音频", ".wma", "wmav2", "asf", ("-vn", "-c:a", "wmav2")),
    "media_mp4": ("MP4 视频（H.264）", ".mp4", "libx264", "mp4", ("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac")),
    "media_webm": ("WebM 视频（VP9）", ".webm", "libvpx-vp9", "webm", ("-c:v", "libvpx-vp9", "-c:a", "libopus")),
    "media_mkv": ("MKV 视频（H.264）", ".mkv", "libx264", "matroska", ("-c:v", "libx264", "-c:a", "aac")),
    "media_mov": ("MOV 视频（H.264）", ".mov", "libx264", "mov", ("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac")),
}
VIDEO_KEYS = {"media_mp4", "media_webm", "media_mkv", "media_mov"}


@lru_cache(maxsize=1)
def ffmpeg_binary() -> str | None:
    """Prefer an installed tool, otherwise the declared package's local binary."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        return None


def _run(arguments: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


@lru_cache(maxsize=2)
def _encoders(binary: str) -> frozenset[str]:
    result = _run([binary, "-hide_banner", "-encoders"])
    return frozenset(parts[1] for line in result.stdout.splitlines()
                     if len(parts := line.split()) >= 2 and len(parts[0]) == 6)


def inspect_media(source: Path) -> tuple[str, str, tuple[ConversionTarget, ...]]:
    """Probe actual streams and encoders before offering media targets."""
    binary = ffmpeg_binary()
    if not binary:
        return "other", "FFmpeg 未安装，当前只可 ZIP 打包", ()
    try:
        result = _run([binary, "-hide_banner", "-nostdin", "-protocol_whitelist", "file,pipe",
                       "-f", DEMUXERS[source.suffix.lower()], "-i", str(source)])
        video, audio = "Video:" in result.stderr, "Audio:" in result.stderr
        if not video and not audio:
            raise ConversionError("FFmpeg 未识别到音视频流，文件可能损坏或格式不匹配。")
        encoders = _encoders(binary)
        targets = tuple(ConversionTarget(key, title, suffix,
                        "本机重新编码，可能有损；只保留首个对应媒体流，不承诺字幕、封面和元数据保留。")
                        for key, (title, suffix, codec, _muxer, _args) in CODECS.items()
                        if codec in encoders and _audio_encoder_available(key, encoders, audio)
                        and (video if key in VIDEO_KEYS else audio))
        return "media", "FFmpeg · " + ("视频" if video else "音频") + (" + 音频" if video and audio else ""), targets
    except (OSError, subprocess.SubprocessError) as error:
        raise ConversionError("FFmpeg 无法运行或探测超时，请检查本机后端安装。") from error


def convert_media(source: Path, key: str, staging: Path, progress: Progress, cancel: Event) -> None:
    """Run only fixed codec arguments; never accept model or shell commands."""
    binary = ffmpeg_binary()
    if binary is None:
        raise ConversionError("FFmpeg 后端不可用。")
    _title, _suffix, _codec, muxer, codec_args = CODECS[key]
    maps = ["-map", "0:v:0?", "-map", "0:a:0?"] if key in VIDEO_KEYS else ["-map", "0:a:0"]
    command = [binary, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
               "-protocol_whitelist", "file,pipe", "-f", DEMUXERS[source.suffix.lower()], "-i", str(source),
               *maps, "-map_metadata", "-1", *codec_args, "-threads", "2", "-f", muxer, str(staging)]
    progress(0, 0)
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            _wait_for_process(process, cancel)
            if process.returncode:
                raise ConversionError("音视频转换失败：输入无法解码、编码器不兼容或输出权限不足。")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    progress(1, 1)


def _wait_for_process(process: subprocess.Popen[bytes], cancel: Event) -> None:
    started = time.monotonic()
    while process.poll() is None:
        check_cancel(cancel)
        if time.monotonic() - started > 300:
            raise ConversionError("转换超过 5 分钟限制，已停止本次子进程。")
        cancel.wait(0.05)


def _audio_encoder_available(key: str, encoders: frozenset[str], has_audio: bool) -> bool:
    if key not in VIDEO_KEYS or not has_audio:
        return True
    return ("libopus" if key == "media_webm" else "aac") in encoders


def available_media_extensions(video: bool) -> tuple[str, ...]:
    """Report installed output encoders; callers must run discovery in a worker."""
    binary = ffmpeg_binary()
    if not binary:
        return ()
    encoders = _encoders(binary)
    return tuple(suffix[1:].upper() for key, (_title, suffix, codec, _muxer, _args) in CODECS.items()
                 if (key in VIDEO_KEYS) == video and codec in encoders and _audio_encoder_available(key, encoders, True))
