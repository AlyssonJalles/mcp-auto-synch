"""OS detection helpers shared across the app."""
from __future__ import annotations

import os
import platform
import subprocess
from urllib.parse import quote

IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"


def home() -> str:
    return os.path.expanduser("~")


def expand(path: str) -> str:
    """Expand ~ and %ENV% / $ENV style variables in a config path template."""
    path = os.path.expandvars(path)
    path = os.path.expanduser(path)
    return path


def _linux_reveal(path: str) -> None:
    """Reveal (ideally *select*) a file in the Linux file manager.

    Tries the freedesktop org.freedesktop.FileManager1 ShowItems D-Bus call
    first, which highlights the file itself the way macOS's `open -R` does;
    plain `xdg-open` can only open the containing folder, leaving the user to
    find the file. Falls back to that when the D-Bus interface isn't
    available (no `gdbus`, or no file manager registered on the bus)."""
    uri = "file://" + quote(os.path.abspath(path))
    try:
        result = subprocess.run(
            [
                "gdbus", "call", "--session",
                "--dest", "org.freedesktop.FileManager1",
                "--object-path", "/org/freedesktop/FileManager1",
                "--method", "org.freedesktop.FileManager1.ShowItems",
                "[%r]" % uri, "",
            ],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return
    except Exception:
        pass
    folder = os.path.dirname(path) or "."
    subprocess.run(["xdg-open", folder], check=False, timeout=5)


def open_path_in_file_manager(path: str) -> None:
    """Reveal a file/folder in the OS file manager. Best-effort, never raises."""
    try:
        if IS_MAC:
            subprocess.run(["open", "-R", path], check=False)
        elif IS_LINUX:
            _linux_reveal(path)
        elif IS_WINDOWS:
            subprocess.run(["explorer", "/select,", path], check=False)
    except Exception:
        pass
