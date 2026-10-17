# -*- mode: python ; coding: utf-8 -*-
"""Windows x64 onedir build; paths are derived from the saved spec location."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

project_root = Path(SPECPATH).resolve().parent
release_data = project_root / "build" / "release"
if not (release_data / "version-info.txt").is_file():
    raise SystemExit("Run scripts/build-windows.ps1 -Stage Prepare first.")

datas = [
    (str(project_root / "filemind/ui/assets"), "filemind/ui/assets"),
    (str(project_root / "filemind/ui/styles" / "base.qss"), "filemind/ui/styles"),
    (str(project_root / "filemind/ui/styles" / "orbit.qss"), "filemind/ui/styles"),
    (str(project_root / "filemind/ui/styles" / "conversion.qss"), "filemind/ui/styles"),
    (str(project_root / "filemind/ui/styles" / "models.qss"), "filemind/ui/styles"),
    (str(project_root / "LICENSE"), "."),
    (str(release_data / "THIRD_PARTY_NOTICES.txt"), "."),
    (str(release_data / "licenses"), "THIRD_PARTY_LICENSES"),
]
binaries = []
hiddenimports = collect_submodules("filemind") + collect_submodules("fontTools.ttLib")
for package_name in ("imageio_ffmpeg", "pypdfium2", "pypdfium2_raw"):
    package_data, package_binaries, package_imports = collect_all(package_name)
    datas.extend(package_data)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_imports)
for package_name in ("docx", "pptx"):
    datas.extend(collect_data_files(package_name))

analysis = Analysis(
    [str(project_root / "main.py")], pathex=[str(project_root)],
    binaries=binaries, datas=datas, hiddenimports=sorted(set(hiddenimports)),
    hookspath=[], runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "pytest"], noarchive=False,
)
python_archive = PYZ(analysis.pure)
executable = EXE(
    python_archive, analysis.scripts, [], exclude_binaries=True, name="FileMind",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False, contents_directory="_internal",
    icon=str(project_root / "filemind/ui/assets/FileMind_AppIcon.ico"),
    version=str(release_data / "version-info.txt"),
)
collection = COLLECT(executable, analysis.binaries, analysis.datas,
                     strip=False, upx=False, name="FileMind")
