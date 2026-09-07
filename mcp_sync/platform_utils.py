"""OS detection helpers shared across the app."""
from __future__ import annotations

import os
import platform
import subprocess

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


def open_path_in_file_manager(path: str) -> None:
    """Reveal a file/folder in the OS file manager. Best-effort, never raises."""
    try:
        if IS_MAC:
            subprocess.run(["open", "-R", path], check=False)
        elif IS_LINUX:
            subprocess.run(["xdg-open", os.path.dirname(path)], check=False)
        elif IS_WINDOWS:
            subprocess.run(["explorer", "/select,", path], check=False)
    except Exception:
        pass
