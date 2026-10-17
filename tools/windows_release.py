"""Prepare metadata, validate frozen bundles and assemble local release artifacts."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)$")
PRIVATE_NAMES = frozenset({"local_api_keys.json", "workspace.json", "auth.json", "chat_history.json"})


def read_version(root: Path) -> str:
    """Read the version as literal source data without importing the application."""
    tree = ast.parse((root / "filemind/__init__.py").read_text("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and
                                               target.id == "__version__" for target in node.targets):
            version = ast.literal_eval(node.value)
            if isinstance(version, str) and VERSION_PATTERN.fullmatch(version):
                if all(int(part) <= 65535 for part in version.split(".")):
                    return version
    raise ValueError("Set __version__ to a numeric X.Y.Z Windows release version.")


def read_pins(path: Path) -> dict[str, str]:
    """Read a fully pinned requirements file without accepting package URLs."""
    pins: dict[str, str] = {}
    for line in path.read_text("utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = PIN_PATTERN.fullmatch(line.strip())
        if not match:
            raise ValueError(f"Unpinned requirement in {path.name}.")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in pins:
            raise ValueError(f"Duplicate requirement: {name}.")
        pins[name] = match[2]
    return pins


def write_json(path: Path, payload: object) -> None:
    """Write generated non-secret build metadata using consistent UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", "utf-8")


def file_sha256(path: Path) -> str:
    """Hash a build artifact without leaving file handles open on Windows."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_config(root: Path) -> dict[str, object]:
    """Check portable release inputs without creating an environment or bundling."""
    required = ("main.py", "LICENSE", "packaging/FileMind.spec", "packaging/FileMind.iss",
                "scripts/build-windows.ps1", "filemind/ui/assets/FileMind_AppIcon.ico",
                "tools/export_installer_art.py", "packaging/installer/wizard-sidebar.bmp",
                "packaging/installer/wizard-small.bmp", "packaging/installer/LICENSE.zh-CN.txt",
                "packaging/installer/wordmark.svg",
                "packaging/installer/languages/ChineseSimplified.isl",
                "packaging/installer/languages/INNO-LICENSE.txt")
    for relative in required:
        if not (root / relative).is_file():
            raise ValueError(f"Missing release input: {relative}.")
    runtime = read_pins(root / "packaging/requirements-windows.lock")
    build = read_pins(root / "packaging/requirements-build.lock")
    for name in runtime.keys() & build.keys():
        if runtime[name] != build[name]:
            raise ValueError(f"Conflicting lock versions for {name}.")
    compile((root / "packaging/FileMind.spec").read_text("utf-8"), "FileMind.spec", "exec")
    return {"version": read_version(root), "runtime_distributions": len(runtime),
            "build_distributions": len(build), "configuration_valid": True}


def windows_version_resource(version: str) -> str:
    """Generate the Windows file-version resource from the single app version."""
    numbers = tuple(int(part) for part in version.split(".")) + (0,)
    return f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r}, mask=0x3f,
                    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'FileMind contributors'),
    StringStruct('FileDescription', 'FileMind Desktop'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('InternalName', 'FileMind'),
    StringStruct('OriginalFilename', 'FileMind.exe'),
    StringStruct('ProductName', 'FileMind'),
    StringStruct('ProductVersion', '{version}')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
'''


def collect_license_files(package: metadata.Distribution, destination: Path) -> int:
    """Copy installed license/notice files, never arbitrary external paths."""
    count = 0
    install_root = Path(sys.prefix).resolve()
    for entry in package.files or ():
        if not any(word in str(entry).lower() for word in ("license", "licence", "copying", "notice")):
            continue
        source = package.locate_file(entry).resolve()
        if not source.is_relative_to(install_root) or not source.is_file() or source.is_symlink():
            continue
        if ".." in entry.parts:
            continue
        target = destination.joinpath(*entry.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        count += 1
    return count


def collect_licenses(root: Path, output: Path) -> list[dict[str, object]]:
    """Record actual installed licenses rather than assigning MIT to dependencies."""
    packages = []
    for name, expected in read_pins(root / "packaging/requirements-windows.lock").items():
        package = metadata.distribution(name)
        if package.version != expected:
            raise ValueError(f"Installed {name} does not match the Windows runtime lock.")
        license_name = package.metadata.get("License-Expression") or package.metadata.get("License") or "See included notices"
        packages.append({"name": name, "version": package.version,
                         "license": " ".join(license_name.split()),
                         "license_files": collect_license_files(package, output / "licenses" / name)})
    lines = ["FileMind third-party runtime inventory", "",
             "FileMind source is MIT. Bundled dependencies retain their own licenses.",
             "Provider logos are used to identify their respective services.", ""]
    lines.extend(f"{item['name']}=={item['version']}: {item['license']}" for item in packages)
    (output / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(lines) + "\n", "utf-8")
    return packages


def collect_bundler_licenses(output: Path) -> None:
    """Retain notices for the shipped bootloader and any bundled runtime hooks."""
    for name in ("pyinstaller", "pyinstaller-hooks-contrib"):
        package = metadata.distribution(name)
        destination = output / "licenses/build-tools" / name
        if not collect_license_files(package, destination):
            raise ValueError(f"No installed license text found for {name}.")
    with (output / "THIRD_PARTY_NOTICES.txt").open("a", encoding="utf-8") as stream:
        stream.write("\nPyInstaller bootloader/build tools and runtime-hook notices: "
                     "see THIRD_PARTY_LICENSES/build-tools.\n")


def prepare(root: Path) -> dict[str, object]:
    """Generate version resources, installer include and dependency notices."""
    result = validate_config(root)
    output = root / "build/release"
    output.mkdir(parents=True, exist_ok=True)
    version = str(result["version"])
    packages = collect_licenses(root, output)
    collect_bundler_licenses(output)
    for license_path in (root / "packaging/licenses").glob("*.txt"):
        destination = output / "licenses/common" / license_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(license_path, destination)
    (output / "version-info.txt").write_text(windows_version_resource(version), "utf-8")
    (output / "metadata.iss").write_text(f'#define AppVersion "{version}"\n', "utf-8")
    result.update({"application": "FileMind", "architecture": "x64", "mode": "onedir",
                   "runtime": packages, "python": sys.version.split()[0],
                   "pyinstaller": metadata.version("pyinstaller"),
                   "hooks": metadata.version("pyinstaller-hooks-contrib")})
    write_json(output / "metadata.json", result)
    return result


def inspect_bundle_files(bundle: Path) -> list[Path]:
    """Reject user-state files and links before freezing artifacts into a ZIP."""
    if bundle.is_symlink() or bundle.is_junction():
        raise ValueError("The bundle root must not be a link.")
    files = []
    for path in sorted(bundle.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError("The bundle must not contain linked paths.")
        if not path.is_file():
            continue
        if path.name.lower().startswith(".env") or path.name.lower() in PRIVATE_NAMES:
            raise ValueError("A user-state file is present in the release directory.")
        files.append(path)
    if not files:
        raise ValueError("The release directory is empty.")
    return files


def verify_bundle(root: Path) -> dict[str, object]:
    """Launch the frozen self-check using generated data and a bounded timeout."""
    bundle = root / "dist/FileMind"
    executable = bundle / "FileMind.exe"
    inspect_bundle_files(bundle)
    required = ("_internal/filemind/ui/assets/FileMind_AppIcon.ico",
                "_internal/filemind/ui/assets/provider_logos/ollama_dark.png",
                "_internal/filemind/ui/styles/base.qss", "_internal/THIRD_PARTY_NOTICES.txt")
    for relative in required:
        if not (bundle / relative).is_file():
            raise ValueError(f"Missing bundled resource: {relative}.")
    if not executable.is_file():
        raise ValueError("Build dist/FileMind/FileMind.exe first.")
    report = root / "build/release/self-check.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.unlink(missing_ok=True)
    result = subprocess.run([str(executable), "--self-check", "--report", str(report)],
                            cwd=bundle, timeout=60, check=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode or not report.is_file():
        raise ValueError("Frozen application self-check failed; inspect build/release/self-check.json.")
    payload = json.loads(report.read_text("utf-8"))
    if (payload.get("version") != read_version(root) or payload.get("ok") is not True
            or payload.get("frozen") is not True):
        raise ValueError("Frozen application version or self-check result is invalid.")
    (root / "build/release/ffmpeg-license.txt").write_text(str(payload.get("ffmpeg_license", "")), "utf-8")
    license_target = bundle / "_internal/THIRD_PARTY_LICENSES/ffmpeg"
    license_target.mkdir(parents=True, exist_ok=True)
    (license_target / "FFMPEG-LICENSE.txt").write_text(str(payload.get("ffmpeg_license", "")), "utf-8")
    return payload


def create_portable_zip(bundle: Path, destination: Path) -> None:
    """Archive the entire onedir tree under a single FileMind top directory."""
    files = inspect_bundle_files(bundle)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, Path("FileMind") / path.relative_to(bundle))


def artifacts(root: Path, compiler_version: str = "manual GUI build") -> dict[str, object]:
    """Publish local ZIP, manifest and hashes only after the bundle passes checks."""
    check = verify_bundle(root)
    version = read_version(root)
    output = root / "dist/release" / version
    output.mkdir(parents=True, exist_ok=True)
    installer = root / f"dist/installer/FileMind-Setup-{version}-x64.exe"
    if not installer.is_file():
        raise ValueError("Compile the Inno Setup installer first.")
    portable = output / f"FileMind-{version}-win-x64.zip"
    create_portable_zip(root / "dist/FileMind", portable)
    setup = output / installer.name
    shutil.copy2(installer, setup)
    shutil.copy2(root / "build/release/ffmpeg-license.txt", output / "FFMPEG-LICENSE.txt")
    payload = json.loads((root / "build/release/metadata.json").read_text("utf-8"))
    payload["self_check"] = check
    payload["inno_setup"] = compiler_version
    write_json(output / "release-manifest.json", payload)
    names = [setup.name, portable.name, "FFMPEG-LICENSE.txt", "release-manifest.json"]
    checksums = [f"{file_sha256(output / name)}  {name}" for name in names]
    (output / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", "ascii")
    return {"version": version, "artifacts": names + ["SHA256SUMS.txt"]}


def main(arguments: list[str] | None = None) -> int:
    """Run one release-engineering stage without changing user application state."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("validate-config", "prepare", "verify-bundle", "artifacts", "version"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--compiler-version", default="manual GUI build")
    args = parser.parse_args(arguments)
    root = args.root.resolve()
    actions = {"validate-config": validate_config, "prepare": prepare,
               "verify-bundle": verify_bundle,
               "artifacts": lambda root: artifacts(root, args.compiler_version)}
    try:
        if args.stage == "version":
            print(read_version(root))
        else:
            print(json.dumps(actions[args.stage](root), ensure_ascii=False, indent=2))
    except (OSError, ValueError, metadata.PackageNotFoundError, subprocess.SubprocessError) as error:
        print(f"Release stage failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
