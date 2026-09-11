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

# Windows has neither flock nor AF_UNIX, so a loopback TCP socket plays both
# roles there: binding it *is* the lock (the OS refuses a second bind), and
# the same socket carries the activation handshake. A fixed high port keeps
# the two halves able to find each other with no discovery file to go stale.
_WIN_PORT = 49517
_WIN_HOST = "127.0.0.1"

# The handle acquire() handed out, so code that ends the process from far away
# (updater.restart_app) can drop the claim without threading the handle
# through every call site.
_active: Optional["InstanceHandle"] = None


def release_active() -> None:
    """Release this process's single-instance claim, if it holds one."""
    if _active is not None:
        _active.release()


class InstanceHandle:
    """Returned to the process that won the primary role. Assign
    `on_activate` once the UI exists; until then activation requests from
    other launches are accepted and harmlessly ignored."""

    def __init__(self, lock_fd: int, server: Optional[socket.socket] = None) -> None:
        self._lock_fd = lock_fd
        # On Windows this holds the bound listening socket - it must stay
        # referenced for the process's lifetime, since closing it frees the
        # port and lets a second instance start.
        self._server = server
        self.on_activate: Optional[Callable[[], None]] = None

    def release(self) -> None:
        """Give up the single-instance claim before this process ends.

        Only the update restart needs this: it spawns the replacement and
        then exits, so without an explicit release the successor races the
        dying process for the lock. Losing that race is not harmless - the
        successor would conclude an instance is already running and exit
        too, leaving the user with no app after an update."""
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        if self._lock_fd >= 0:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = -1

    def start_activation_listener(self) -> None:
        if IS_WINDOWS:
            self._serve(self._server)
            return
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

        self._serve(server)

    def _serve(self, server: Optional[socket.socket]) -> None:
        """Accept activation pokes forever on `server`, in a daemon thread."""
        if server is None:
            return

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
        if IS_WINDOWS:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2)
            client.connect((_WIN_HOST, _WIN_PORT))
        else:
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
    global _active
    if IS_WINDOWS:
        # Binding the loopback port is the lock: the Start Menu shortcut and
        # the Run-at-login entry both re-run this entry point, and the second
        # one must hand its "user asked for the app" event to the first
        # instead of raising a duplicate tray icon.
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Deliberately NOT SO_REUSEADDR: on Windows that would let a
            # second process bind the same port and defeat the whole lock.
            server.bind((_WIN_HOST, _WIN_PORT))
            server.listen(8)
        except OSError:
            server.close()
            _ask_running_instance_to_show()
            return None
        _active = InstanceHandle(-1, server=server)
        return _active

    import fcntl

    try:
        os.makedirs(_DIR, exist_ok=True)
        lock_fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        _active = InstanceHandle(-1)  # can't lock - better to run than to refuse
        return _active

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
    _active = InstanceHandle(lock_fd)
    return _active
