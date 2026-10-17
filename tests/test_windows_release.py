"""Focused release-engineering tests; no real bundler, installer or account data."""

import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zipfile import ZipFile

import pytest
import yaml

from tools import windows_release as release


ROOT = Path(__file__).parents[1]


def create_project(root: Path, version: str = "1.2.3") -> Path:
    """Create a generated release tree for deterministic metadata checks."""
    for name in ("main.py", "LICENSE", "packaging/FileMind.spec", "packaging/FileMind.iss",
                 "scripts/build-windows.ps1", "filemind/ui/assets/FileMind_AppIcon.ico",
                 "tools/export_installer_art.py", "packaging/installer/wizard-sidebar.bmp",
                 "packaging/installer/wizard-small.bmp", "packaging/installer/LICENSE.zh-CN.txt",
                 "packaging/installer/wordmark.svg",
                 "packaging/installer/languages/ChineseSimplified.isl",
                 "packaging/installer/languages/INNO-LICENSE.txt"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", "utf-8")
    (root / "filemind/__init__.py").write_text(f'__version__ = "{version}"\n', "utf-8")
    for name in ("requirements-windows.lock", "requirements-build.lock"):
        (root / "packaging" / name).write_text("example==1.0\n", "utf-8")
    return root


def create_bundle(root: Path) -> Path:
    """Create inert test bytes, never a runnable application."""
    bundle = root / "dist/FileMind"
    for name in ("FileMind.exe", "_internal/filemind/ui/assets/FileMind_AppIcon.ico",
                 "_internal/filemind/ui/assets/provider_logos/ollama_dark.png",
                 "_internal/filemind/ui/styles/base.qss", "_internal/THIRD_PARTY_NOTICES.txt"):
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"generated release test fixture")
    return bundle


@pytest.mark.parametrize("value", ["1.2.3", "0.1.0", "65535.0.1"])
def test_version_is_literal_and_valid_for_windows(tmp_path: Path, value: str) -> None:
    root = create_project(tmp_path, value)
    assert release.read_version(root) == value
    compile(release.windows_version_resource(value), "version-info.txt", "eval")


@pytest.mark.parametrize("value", ["1.2", "v1.2.3", "1.2.3rc1", "65536.0.0", "01.0.0"])
def test_invalid_release_versions_are_rejected(tmp_path: Path, value: str) -> None:
    root = create_project(tmp_path, value)
    with pytest.raises(ValueError):
        release.read_version(root)


def test_version_reader_never_executes_source(tmp_path: Path) -> None:
    root = create_project(tmp_path)
    (root / "filemind/__init__.py").write_text('__version__ = "1.2.3"\nraise RuntimeError("not executed")\n')
    assert release.read_version(root) == "1.2.3"


def test_real_configuration_and_locks_are_consistent() -> None:
    payload = release.validate_config(ROOT)
    assert payload["configuration_valid"]
    assert payload["runtime_distributions"] >= 12
    runtime = release.read_pins(ROOT / "packaging/requirements-windows.lock")
    assert runtime["pyside6-essentials"] == "6.12.0"
    assert release.read_pins(ROOT / "packaging/requirements-build.lock")["pyinstaller"] == "6.21.0"


@pytest.mark.parametrize("line", ["example>=1", "https://example.test/wheel", "example==1\nexample==1"])
def test_lock_rejects_unpinned_or_duplicate_requirements(tmp_path: Path, line: str) -> None:
    path = tmp_path / "test.lock"
    path.write_text(line)
    with pytest.raises(ValueError):
        release.read_pins(path)


def test_validate_rejects_conflicting_build_lock(tmp_path: Path) -> None:
    root = create_project(tmp_path)
    (root / "packaging/requirements-build.lock").write_text("example==2.0\n")
    with pytest.raises(ValueError, match="Conflicting"):
        release.validate_config(root)


@pytest.mark.parametrize("filename", ["ChineseSimplified.isl", "INNO-LICENSE.txt"])
def test_validate_requires_bundled_installer_language(tmp_path: Path, filename: str) -> None:
    root = create_project(tmp_path)
    (root / "packaging/installer/languages" / filename).unlink()
    with pytest.raises(ValueError, match="Missing release input"):
        release.validate_config(root)


def test_version_resource_and_inno_metadata_share_one_version(tmp_path: Path) -> None:
    root = create_project(tmp_path)
    with patch.object(release, "collect_licenses", return_value=[]), \
            patch.object(release, "collect_bundler_licenses"), \
            patch.object(release.metadata, "version", return_value="fixture"):
        result = release.prepare(root)
    assert result["version"] == "1.2.3"
    assert '(1, 2, 3, 0)' in (root / "build/release/version-info.txt").read_text()
    assert '#define AppVersion "1.2.3"' in (root / "build/release/metadata.iss").read_text()


def test_windows_resource_is_readable_by_the_locked_pyinstaller(tmp_path: Path) -> None:
    versioninfo = pytest.importorskip("PyInstaller.utils.win32.versioninfo")

    resource_path = tmp_path / "version-info.txt"
    resource_path.write_text(release.windows_version_resource("1.2.3"), "utf-8")
    resource = versioninfo.load_version_info_from_text_file(str(resource_path))
    assert resource.ffi.fileVersionMS == (1 << 16) + 2
    assert resource.ffi.fileVersionLS == 3 << 16


def test_spec_keeps_onedir_resources_without_running_a_bundler(tmp_path: Path) -> None:
    hooks = pytest.importorskip("PyInstaller.utils.hooks")

    root = create_project(tmp_path / "release project with spaces")
    source = ROOT / "packaging/FileMind.spec"
    (root / "build/release").mkdir(parents=True)
    (root / "build/release/version-info.txt").write_text("generated fixture")
    invocation: dict[str, object] = {}

    def capture_analysis(entries: list[str], **options: object) -> SimpleNamespace:
        invocation["entries"] = entries
        invocation["analysis"] = options
        return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])

    def capture_executable(*arguments: object, **options: object) -> object:
        invocation["exe"] = options
        return object()

    def capture_collection(*arguments: object, **options: object) -> None:
        invocation["collection"] = options

    globals_for_spec = {"SPECPATH": str(root / "packaging"), "Analysis": capture_analysis,
                        "PYZ": lambda value: value, "EXE": capture_executable,
                        "COLLECT": capture_collection}
    with patch.object(hooks, "collect_all", return_value=([], [], [])), \
            patch.object(hooks, "collect_submodules", return_value=[]), \
            patch.object(hooks, "collect_data_files", return_value=[]):
        runpy.run_path(str(source), init_globals=globals_for_spec)
    assert invocation["entries"] == [str(root / "main.py")]
    options = invocation["analysis"]
    assert (str(root / "filemind/ui/assets"), "filemind/ui/assets") in options["datas"]
    assert invocation["exe"]["exclude_binaries"] is True
    assert invocation["exe"]["contents_directory"] == "_internal"
    assert invocation["exe"]["console"] is False
    assert invocation["collection"]["name"] == "FileMind"


@pytest.mark.parametrize("filename", [".env", ".ENV.local", "local_api_keys.json", "workspace.json", "auth.json"])
def test_release_inspection_rejects_generated_private_state_names(tmp_path: Path, filename: str) -> None:
    bundle = create_bundle(tmp_path)
    (bundle / filename).write_text("generated fixture, not user data")
    with pytest.raises(ValueError, match="user-state"):
        release.inspect_bundle_files(bundle)


def test_portable_zip_keeps_whole_internal_tree(tmp_path: Path) -> None:
    bundle = create_bundle(tmp_path)
    output = tmp_path / "portable.zip"
    release.create_portable_zip(bundle, output)
    with ZipFile(output) as archive:
        assert "FileMind/FileMind.exe" in archive.namelist()
        assert "FileMind/_internal/filemind/ui/styles/base.qss" in archive.namelist()


@pytest.mark.parametrize("frozen,version,ok", [(False, "1.2.3", True), (True, "9.9.9", True), (True, "1.2.3", False)])
def test_bundle_verification_rejects_wrong_binary_or_failed_checks(tmp_path: Path, frozen: bool, version: str, ok: bool) -> None:
    root = create_project(tmp_path)
    create_bundle(root)

    def simulated_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        release.write_json(Path(command[-1]), {"frozen": frozen, "version": version, "ok": ok})
        return subprocess.CompletedProcess(command, 0)

    with patch.object(release.subprocess, "run", side_effect=simulated_run):
        with pytest.raises(ValueError, match="version or self-check"):
            release.verify_bundle(root)


def test_bundle_verifier_uses_argument_list_and_copies_ffmpeg_notice(tmp_path: Path) -> None:
    root = create_project(tmp_path / "project with spaces")
    create_bundle(root)

    def simulated_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        assert command[1:3] == ["--self-check", "--report"]
        assert kwargs["timeout"] == 60
        release.write_json(Path(command[-1]), {"frozen": True, "version": "1.2.3", "ok": True,
                                               "ffmpeg_license": "generated license fixture"})
        return subprocess.CompletedProcess(command, 0)

    with patch.object(release.subprocess, "run", side_effect=simulated_run):
        assert release.verify_bundle(root)["ok"]
    assert (root / "dist/FileMind/_internal/THIRD_PARTY_LICENSES/ffmpeg/FFMPEG-LICENSE.txt").is_file()


def test_assembled_release_is_versioned_and_checksum_matches(tmp_path: Path) -> None:
    root = create_project(tmp_path)
    create_bundle(root)
    installer = root / "dist/installer/FileMind-Setup-1.2.3-x64.exe"
    installer.parent.mkdir()
    installer.write_bytes(b"generated installer fixture")
    release.write_json(root / "build/release/metadata.json", {"version": "1.2.3"})
    (root / "build/release/ffmpeg-license.txt").write_text("generated license fixture")
    with patch.object(release, "verify_bundle", return_value={"ok": True}):
        result = release.artifacts(root)
    output = root / "dist/release/1.2.3"
    assert (output / result["artifacts"][0]).is_file()
    for line in (output / "SHA256SUMS.txt").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected


def test_diagnostic_ui_imports_do_not_open_account_stores() -> None:
    from filemind.release_check import _check_ui
    from filemind.storage.chat_history import ChatHistoryStore
    from filemind.storage.settings import SettingsStore
    from filemind.storage.local_lock import LocalLockStore

    with patch.object(SettingsStore, "__init__", side_effect=AssertionError("no model settings")), \
            patch.object(ChatHistoryStore, "__init__", side_effect=AssertionError("no user conversations")), \
            patch.object(LocalLockStore, "__init__", side_effect=AssertionError("no user authentication")):
        assert _check_ui()["icon"]


def test_existing_source_tests_were_preserved() -> None:
    snapshot = json.loads((ROOT / "SOURCE_SNAPSHOT.json").read_text("utf-8"))
    for name in snapshot["sha256"]:
        if name.startswith("tests/"):
            # The main repository can improve tests after integration; keep each file.
            assert (ROOT / name).is_file(), name


@pytest.mark.parametrize("diagnostics", [False, True])
def test_entry_point_preserves_desktop_startup_and_explicit_diagnostics(diagnostics: bool) -> None:
    desktop = Mock(return_value=0)
    checks = Mock(return_value=0)
    arguments = ["FileMind.exe"]
    if diagnostics:
        arguments += ["--self-check", "--report", "generated-report.json"]
    modules = {"filemind.ui.main_window": SimpleNamespace(main=desktop),
               "filemind.release_check": SimpleNamespace(main=checks)}
    with patch.dict(sys.modules, modules), patch.object(sys, "argv", arguments):
        entry = runpy.run_path(str(ROOT / "main.py"))
        assert entry["main"]() == 0
    if diagnostics:
        checks.assert_called_once_with(arguments[1:])
        desktop.assert_not_called()
    else:
        desktop.assert_called_once_with()
        checks.assert_not_called()


def test_icon_export_preserves_transparency_in_all_generated_layers(tmp_path: Path) -> None:
    from PIL import Image
    from tools.export_app_icon import export_icons

    svg = ROOT / "filemind/ui/assets/FileMind_AppIcon.svg"
    (tmp_path / svg.name).write_bytes(svg.read_bytes())
    export_icons(tmp_path)
    with Image.open(tmp_path / "FileMind_AppIcon.ico") as icon:
        assert len(icon.ico.sizes()) == 7
        for width, height in icon.ico.sizes():
            with icon.ico.getimage((width, height)).convert("RGBA") as layer:
                corners = ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))
                assert all(layer.getpixel(point)[3] == 0 for point in corners)


def test_release_workflow_creates_drafts_and_keeps_build_token_read_only() -> None:
    workflow = yaml.load((ROOT / ".github/workflows/release-windows.yml").read_text("utf-8"), Loader=yaml.BaseLoader)
    assert workflow["permissions"]["contents"] == "read"
    assert workflow["jobs"]["draft-release"]["permissions"]["contents"] == "write"
    commands = workflow["jobs"]["draft-release"]["steps"][-1]["run"]
    assert "--draft --verify-tag" in commands
    assert '"$is_draft" != "true"' in commands
    ci = yaml.load((ROOT / ".github/workflows/ci.yml").read_text("utf-8"), Loader=yaml.BaseLoader)
    assert {"master", "main"} <= set(ci["on"]["push"]["branches"])
