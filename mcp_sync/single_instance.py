"""Keeps only one MCP Sync process alive per user session.

Without this, every click on the app's launcher icon (GNOME's "Show
Applications", a .desktop entry, an autostart entry that fires while the app
is already running) starts a whole new process, and each one registers its
own tray indicator - so the panel fills up with duplicate icons that all
fight over the same config files.

Two pieces, because "don't start twice" alone would make clicking the
launcher appear to do nothing at all:

* an advisory `flock` on a lock file decides who is the primary instance -
  it's held for the process's whole lifetime and released by the kernel even
  if the process is killed, so a crash can't leave a stale lock behind;
* a Unix socket next to it lets a second launch hand its "the user asked for
  the app" event to the instance that's already running (which pops its
  window open) before exiting quietly.
"""
from __future__ import annotations

import os
import socket
import threading
from typing import Callable, Optional

from .platform_utils import IS_WINDOWS, home

_DIR = os.path.join(home(), ".mcp-sync")
LOCK_PATH = os.path.join(_DIR, "instance.lock")
SOCKET_PATH = os.path.join(_DIR, "instance.sock")
_ACTIVATE = b"activate\n"


class InstanceHandle:
    """Returned to the process that won the primary role. Assign
    `on_activate` once the UI exists; until then activation requests from
    other launches are accepted and harmlessly ignored."""

    def __init__(self, lock_fd: int) -> None:
        self._lock_fd = lock_fd
        self.on_activate: Optional[Callable[[], None]] = None

    def start_activation_listener(self) -> None:
        try:
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            # A previous run that died leaves the socket file behind; nobody
            # is listening on it (that's why we got the lock), so it's ours
            # to replace.
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)
            server.bind(SOCKET_PATH)
            server.listen(8)
        except OSError:
            return  # activation is a nicety; never block startup over it

        def serve() -> None:
            while True:
                try:
                    conn, _ = server.accept()
                except OSError:
                    return
                with conn:
                    try:
                        data = conn.recv(len(_ACTIVATE))
                    except OSError:
                        continue
                if data.strip() == _ACTIVATE.strip() and self.on_activate is not None:
                    try:
                        self.on_activate()
                    except Exception:
                        pass

        threading.Thread(target=serve, daemon=True).start()


def _ask_running_instance_to_show() -> None:
    """Best-effort nudge so the already-running instance surfaces itself."""
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2)
        client.connect(SOCKET_PATH)
        client.sendall(_ACTIVATE)
        client.close()
    except OSError:
        pass


def acquire() -> Optional[InstanceHandle]:
    """Claim the single-instance slot.

    Returns a handle if this process should run the app, or None if another
    instance already owns it - in which case that instance has been asked to
    show itself and this process should exit."""
    if IS_WINDOWS:
        # flock/AF_UNIX aren't available here; the Windows build has no
        # launcher-icon path that re-runs the app, so leave it unguarded
        # rather than half-guarded.
        return InstanceHandle(-1)

    import fcntl

    try:
        os.makedirs(_DIR, exist_ok=True)
        lock_fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        return InstanceHandle(-1)  # can't lock - better to run than to refuse

    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(lock_fd)
        _ask_running_instance_to_show()
        return None

    # Kept open (and referenced by the handle) for the process's lifetime -
    # closing the descriptor would drop the lock.
    try:
        os.write(lock_fd, f"{os.getpid()}\n".encode())
    except OSError:
        pass
    return InstanceHandle(lock_fd)
