"""Platform directory rules, tested for every operating system from anywhere."""

from pathlib import Path

from filemind.storage import paths

HOME = Path("/home/tester")


def test_windows_prefers_roaming_for_config_and_local_for_data() -> None:
    environ = {"APPDATA": r"C:\Users\tester\AppData\Roaming",
               "LOCALAPPDATA": r"C:\Users\tester\AppData\Local"}

    assert paths._config_dir("nt", "win32", environ, HOME) == Path(environ["APPDATA"]) / "FileMind"
    assert paths._data_dir("nt", "win32", environ, HOME) == Path(environ["LOCALAPPDATA"]) / "FileMind"


def test_windows_falls_back_when_the_environment_is_missing() -> None:
    assert paths._config_dir("nt", "win32", {}, HOME) == HOME / "AppData" / "Roaming" / "FileMind"
    assert paths._data_dir("nt", "win32", {}, HOME) == HOME / "AppData" / "Local" / "FileMind"


def test_macos_uses_application_support_for_both() -> None:
    expected = HOME / "Library" / "Application Support" / "FileMind"

    assert paths._config_dir("posix", "darwin", {}, HOME) == expected
    assert paths._data_dir("posix", "darwin", {}, HOME) == expected


def test_linux_follows_xdg_with_defaults_and_overrides(tmp_path: Path) -> None:
    assert paths._config_dir("posix", "linux", {}, HOME) == HOME / ".config" / "FileMind"
    assert paths._data_dir("posix", "linux", {}, HOME) == HOME / ".local" / "share" / "FileMind"

    # 用当前平台的绝对路径，这样断言在 Windows、Linux 和 macOS 上都成立。
    overridden = {"XDG_CONFIG_HOME": str(tmp_path / "conf"), "XDG_DATA_HOME": str(tmp_path / "data")}
    assert paths._config_dir("posix", "linux", overridden, HOME) == tmp_path / "conf" / "FileMind"
    assert paths._data_dir("posix", "linux", overridden, HOME) == tmp_path / "data" / "FileMind"


def test_relative_xdg_values_are_ignored() -> None:
    environ = {"XDG_CONFIG_HOME": "relative/path", "XDG_DATA_HOME": ""}

    assert paths._config_dir("posix", "linux", environ, HOME) == HOME / ".config" / "FileMind"
    assert paths._data_dir("posix", "linux", environ, HOME) == HOME / ".local" / "share" / "FileMind"
