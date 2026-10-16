"""Optional LibreOffice conversion, using a private profile and fixed filters."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from threading import Event

from filemind.conversion.base import ConversionError, Progress
from filemind.conversion.media import _wait_for_process
from filemind.conversion.models import ConversionTarget


GROUPS = {"document": {".doc", ".docx", ".odt", ".rtf"},
          "sheet": {".xls", ".xlsx", ".ods"}, "slides": {".ppt", ".pptx", ".odp"}}


def office_binary() -> str | None:
    """Find installed LibreOffice without inspecting personal Office profiles."""
    found = shutil.which("soffice")
    if found:
        return found
    for folder in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.environ.get(folder)
        candidate = Path(root) / "LibreOffice/program/soffice.exe" if root else None
        if candidate and candidate.is_file():
            return str(candidate)
    for candidate in (Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
                      Path("/usr/lib/libreoffice/program/soffice"),
                      Path("/snap/bin/libreoffice")):
        if candidate.is_file():
            return str(candidate)
    return None


def office_targets(source: Path) -> tuple[ConversionTarget, ...]:
    """Offer only format families handled by the installed external adapter."""
    if not office_binary():
        return ()
    group = next((name for name, suffixes in GROUPS.items() if source.suffix.lower() in suffixes), None)
    formats = {"document": ("pdf", "docx", "odt", "rtf"),
               "sheet": ("pdf", "xlsx", "ods"), "slides": ("pdf", "pptx", "odp")}.get(group, ())
    return tuple(ConversionTarget(f"lo_{extension}", f"{extension.upper()} · LibreOffice（实验性）", f".{extension}",
                 "需本机 LibreOffice；排版、字体与公式结果可能变化，复杂文件需人工核对。")
                 for extension in formats if f".{extension}" != source.suffix.lower())


def convert_office(source: Path, key: str, staging: Path, progress: Progress, cancel: Event) -> None:
    """Use a disposable user profile, avoiding the running user's Office instance."""
    binary = office_binary()
    if not binary:
        raise ConversionError("未找到 LibreOffice，无法进行此类排版转换。")
    extension = key.removeprefix("lo_")
    with tempfile.TemporaryDirectory(prefix="filemind-office-") as folder:
        root = Path(folder)
        profile = root / "profile"
        (profile / "user").mkdir(parents=True)
        (profile / "user/registrymodifications.xcu").write_text(
            '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" '
            'oor:op="fuse"><value>3</value></prop></item></oor:items>', encoding="utf-8")
        arguments = [binary, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
                     "--convert-to", extension, "--outdir", str(root), str(source)]
        progress(0, 0)
        process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            _wait_for_process(process, cancel)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
        result = root / f"{source.stem}.{extension}"
        if process.returncode or not result.is_file():
            raise ConversionError("LibreOffice 未生成结果，可能不支持该文件、字体缺失或文件被占用。")
        shutil.copyfile(result, staging)
        progress(1, 1)
