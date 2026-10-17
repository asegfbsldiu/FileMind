"""Targeted checks for the Chinese six-page native installer and its artwork."""

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from tools import windows_release as release
from tools.export_installer_art import export_installer_assets


ROOT = Path(__file__).resolve().parents[1]


def installer_script() -> str:
    """Read the committed installer configuration, never a compiled executable."""
    return (ROOT / "packaging/FileMind.iss").read_text("utf-8")


def test_six_native_pages_and_bundled_chinese_language_are_enabled() -> None:
    script = installer_script()
    for setting in ("DisableWelcomePage=no", "DisableDirPage=no", "DisableReadyPage=yes",
                    "DisableFinishedPage=no", "WizardStyle=modern", "ShowLanguageDialog=no"):
        assert setting in script
    assert ('MessagesFile: "{#ProjectRoot}\\packaging\\installer\\languages\\ChineseSimplified.isl"'
            in script)
    language = (ROOT / "packaging/installer/languages/ChineseSimplified.isl").read_text("utf-8-sig")
    assert "LanguageName=简体中文" in language
    assert "LanguageID=$0804" in language
    assert "[Messages]" in language
    assert (ROOT / "packaging/installer/languages/INNO-LICENSE.txt").is_file()
    assert "DialogFontName=Microsoft YaHei UI" in script
    assert "WizardImageFile={#ProjectRoot}\\packaging\\installer\\wizard-sidebar.bmp" in script
    assert "WizardSmallImageFile={#ProjectRoot}\\packaging\\installer\\wizard-small.bmp" in script


def test_shortcuts_and_startup_are_separate_user_choices() -> None:
    lines = installer_script().splitlines()
    desktop = next(line for line in lines if line.startswith('Name: "desktopicon"'))
    startup = next(line for line in lines if line.startswith('Name: "startup"'))
    assert "unchecked" not in desktop
    assert "Flags: unchecked" in startup
    assert any('Name: "{userstartup}\\FileMind"' in line and "Tasks: startup" in line for line in lines)
    assert any('Name: "{autodesktop}\\FileMind"' in line and "Tasks: desktopicon" in line for line in lines)
    deletions = [line for line in lines if line.startswith("Type: files;")]
    assert len(deletions) == 2
    assert all("FileMind.lnk" in line and "Tasks: not " in line and "*" not in line for line in deletions)


def test_license_page_uses_an_explicit_agree_button_and_keeps_finish_caption() -> None:
    script = installer_script()
    assert "AcceptLicenseButton=我同意(&I)" in script
    assert "LicenseHint.Parent := WizardForm.LicensePage" in script
    assert "WizardForm.LicenseAcceptedRadio.Visible := False" in script
    assert "CustomMessage('AcceptLicenseButton')" in script
    assert "else if CurPageID <> wpFinished then" in script
    assert "SetupMessage(msgButtonInstall)" in script
    assert 'Description: "{cm:LaunchFileMind}"; Flags: nowait postinstall skipifsilent' in script


def test_chinese_license_keeps_the_exact_original_mit_text() -> None:
    license_text = (ROOT / "packaging/installer/LICENSE.zh-CN.txt").read_text("utf-8-sig")
    assert license_text.endswith((ROOT / "LICENSE").read_text("utf-8"))
    assert "_internal\\THIRD_PARTY_LICENSES" in license_text
    assert "仅供个人学习" not in license_text


def test_installer_art_export_is_repeatable_and_supports_high_dpi(tmp_path: Path) -> None:
    assets = tmp_path / "filemind/ui/assets"
    assets.mkdir(parents=True)
    svg = ROOT / "filemind/ui/assets/FileMind_AppIcon.svg"
    (assets / svg.name).write_bytes(svg.read_bytes())
    output = tmp_path / "packaging/installer"
    output.mkdir(parents=True)
    wordmark = ROOT / "packaging/installer/wordmark.svg"
    (output / wordmark.name).write_bytes(wordmark.read_bytes())
    (tmp_path / "LICENSE").write_text("Generated MIT test fixture.\n", "utf-8")
    export_installer_assets(tmp_path)
    first = {path.name: path.read_bytes() for path in output.iterdir()}
    export_installer_assets(tmp_path)
    assert first == {path.name: path.read_bytes() for path in output.iterdir()}
    with Image.open(output / "wizard-sidebar.bmp") as sidebar:
        assert sidebar.size == (656, 1256)
        assert sidebar.width * 314 == sidebar.height * 164
        assert sidebar.getpixel((0, 0)) != sidebar.getpixel((0, sidebar.height - 1))
        with sidebar.crop((0, 143 * 4, 164 * 4, 205 * 4)) as region:
            colors = region.getcolors(maxcolors=region.width * region.height)
            assert any(count > 1000 and color[:3] == (255, 255, 255) for count, color in colors)
    assert "<text" not in wordmark.read_text("utf-8")
    with Image.open(output / "wizard-small.bmp") as small:
        assert small.size == (232, 232)
        assert small.getpixel((0, 0))[:3] == (255, 255, 255)


def test_missing_installer_art_is_rejected_by_release_validation() -> None:
    original_is_file = Path.is_file

    def without_sidebar(path: Path) -> bool:
        return path.name != "wizard-sidebar.bmp" and original_is_file(path)

    with patch.object(Path, "is_file", without_sidebar):
        with pytest.raises(ValueError, match="wizard-sidebar.bmp"):
            release.validate_config(ROOT)
