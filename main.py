"""FileMind desktop entry point with an isolated release-diagnostics mode."""

import sys


def main() -> int:
    """Run the normal locked workspace unless diagnostics are explicitly requested."""
    if "--self-check" in sys.argv[1:]:
        from filemind.release_check import main as run_checks
        return run_checks(sys.argv[1:])
    from filemind.ui.main_window import main as run_desktop
    return run_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
