"""Best-effort cross-platform desktop notifications (no hard dependency)."""
from __future__ import annotations

import subprocess

from .platform_utils import IS_LINUX, IS_MAC, IS_WINDOWS


def notify(title: str, message: str) -> None:
    """Show a desktop notification. Silently does nothing if it fails."""
    try:
        if IS_MAC:
            script = (
                f'display notification "{_escape_osascript(message)}" '
                f'with title "{_escape_osascript(title)}"'
            )
            subprocess.run(["osascript", "-e", script], check=False, timeout=5)
        elif IS_LINUX:
            subprocess.run(["notify-send", title, message], check=False, timeout=5)
        elif IS_WINDOWS:
            _notify_windows(title, message)
    except Exception:
        pass


def _escape_osascript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _notify_windows(title: str, message: str) -> None:
    try:
        from win10toast import ToastNotifier  # type: ignore

        ToastNotifier().show_toast(title, message, duration=5, threaded=True)
        return
    except Exception:
        pass
    try:
        # PowerShell BurntToast-free fallback using the WinRT toast API via ctypes/COM
        # is heavy; fall back to a simple balloon-tip-less message box replacement:
        # a transient console-free notification via msg.exe is not reliable, so we
        # just no-op if win10toast isn't available. Documented in README as optional
        # dependency for Windows notifications.
        pass
    except Exception:
        pass
