"""Desktop entry point, including paths and diagnostics for a windowed frozen app."""

import ctypes
import os
import sys
import tempfile
import traceback
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TextIO

from bne.__main__ import main as cli_main


def game_directory() -> Path:
    """Keep game/ outside the executable; never use PyInstaller's temporary directory."""
    base = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1]
    )
    return base / "game"


def open_log() -> tuple[TextIO, Path | None]:
    """A pythonw/windowed executable has no stdout/stderr. Keep its errors readable."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "state")
    for directory in (base / "BerlNovellaEngine", Path(tempfile.gettempdir()) / "BNE"):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "last-run.log"
            return path.open("w", encoding="utf-8", buffering=1), path
        except OSError:
            continue
    return open(os.devnull, "w", encoding="utf-8"), None


def show_error(message: str, log_path: Path | None) -> None:
    """Windows' native error box needs neither a console nor a working pygame window."""
    if log_path:
        message += f"\n\nЖурнал ошибки: {log_path}"
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, "Berl Novella Engine — ошибка", 0x10)
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    windowless = sys.stdout is None or sys.stderr is None
    with ExitStack() as stack:
        log_path = None
        if windowless:
            handle, log_path = open_log()
            stack.enter_context(handle)
            if sys.stdout is None:
                stack.enter_context(redirect_stdout(handle))
            if sys.stderr is None:
                stack.enter_context(redirect_stderr(handle))
        try:
            return cli_main(
                argv,
                default_project=game_directory(),
                error_handler=(lambda message: show_error(message, log_path))
                if windowless
                else None,
            )
        except Exception as error:
            if not windowless:
                raise
            traceback.print_exc()
            show_error(f"Не удалось запустить игру: {error}", log_path)
            return 1
