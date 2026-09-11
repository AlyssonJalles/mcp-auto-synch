"""Checks GitHub Releases for a newer .whl and, only when explicitly told to,
downloads and installs it into this same interpreter's environment, then
restarts the process.

Uses only the stdlib (urllib) - this is the app's first network-facing code,
and staying dependency-free keeps that one exception easy to audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from . import autostart
from .platform_utils import IS_MAC, IS_WINDOWS

REPO = "AlyssonJalles/mcp-auto-synch"
RELEASES_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
REQUEST_TIMEOUT = 10
DOWNLOAD_TIMEOUT = 60
INSTALL_TIMEOUT = 180
USER_AGENT = "mcp-sync-tray-updater"


class UpdateCheckError(Exception):
    """Any GitHub-API failure: offline, timeout, rate limit, malformed
    response, or a release with no .whl asset. Callers that want silent
    background behavior can catch this one type without caring which of
    those it was."""


@dataclass
class UpdateInfo:
    version: str  # "0.0.2" - leading "v" already stripped
    wheel_url: str
    html_url: str = ""


def parse_version(v: str) -> tuple:
    """Small tuple comparator instead of `packaging.version`: `packaging` is
    not a declared dependency of this project, so it isn't guaranteed to be
    importable in every environment this app runs in. Handles the "vX.Y.Z"
    tags this repo actually uses; a non-numeric suffix on a component just
    contributes its leading digits (or 0) to the comparison."""
    v = v.strip()
    if v.startswith("v"):
        v = v[1:]
    parts = []
    for chunk in v.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(remote_version: str, local_version: str) -> bool:
    return parse_version(remote_version) > parse_version(local_version)


def fetch_latest_release_info() -> UpdateInfo:
    """Raises UpdateCheckError on any failure. Callers driving an explicit
    user action (the "Check for Updates" menu item) can catch it to show a
    specific "couldn't check" notification; background callers should use
    check_for_update() below instead, which swallows this."""
    req = urllib.request.Request(
        RELEASES_API_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        raise UpdateCheckError(str(exc)) from exc

    tag = str(data.get("tag_name") or "")
    remote_version = tag[1:] if tag.startswith("v") else tag
    if not remote_version:
        raise UpdateCheckError("release has no tag_name")

    assets = data.get("assets") or []
    wheel_url = next(
        (a.get("browser_download_url") for a in assets if isinstance(a, dict) and str(a.get("name", "")).endswith(".whl")),
        None,
    )
    if not wheel_url:
        raise UpdateCheckError("latest release has no .whl asset")

    return UpdateInfo(version=remote_version, wheel_url=wheel_url, html_url=str(data.get("html_url", "")))


def check_for_update(current_version: str) -> Optional[UpdateInfo]:
    """Silent wrapper for the periodic/startup background loop: returns
    UpdateInfo only if strictly newer, None for "no update" AND for any
    check failure alike - being offline is the common case, and the
    background loop must never turn that into a notification."""
    try:
        info = fetch_latest_release_info()
    except UpdateCheckError:
        return None
    return info if is_newer(info.version, current_version) else None


# --------------------------------------------------------------- installing


def download_wheel(url: str, dest_dir: str) -> str:
    filename = url.rsplit("/", 1)[-1] or "mcp_sync_update.whl"
    dest_path = os.path.join(dest_dir, filename)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, open(dest_path, "wb") as fh:
        fh.write(resp.read())
    return dest_path


def install_wheel(wheel_path: str) -> None:
    """Upgrades this same interpreter's environment - `sys.executable` is
    already the venv/pipx interpreter the running app was launched with, so
    there's no need to separately locate ~/.mcp-sync/venv."""
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", wheel_path],
        check=True,
        timeout=INSTALL_TIMEOUT,
    )


def _spawn_detached(cmd: list[str]) -> None:
    kwargs: dict = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kwargs)


def restart_app() -> None:
    """Never returns - always ends this process."""
    # Drop the single-instance claim first, if this build has one: the
    # successor starts while this process is still alive, and would
    # otherwise find the slot taken, decide an instance is already running,
    # and exit - leaving nothing running at all. Releasing here rather than
    # relying on process exit closes that race.
    try:
        from . import single_instance

        single_instance.release_active()
    except ImportError:
        pass

    if IS_MAC and autostart.is_enabled():
        # Rebuilds the .app bundle and does the launchctl unload/load -w
        # cycle that already restarts a KeepAlive=true LaunchAgent - reusing
        # it means the restart path can't drift from the login-item path.
        # Only safe when autostart is already on; calling it unconditionally
        # would silently re-enable autostart for someone who'd turned it off.
        autostart.enable()
    else:
        _spawn_detached([sys.executable, "-m", "mcp_sync.app"])
    os._exit(0)


def perform_update(info: UpdateInfo) -> None:
    """Download -> pip upgrade -> restart. Raises on download/install
    failure so the caller (a tray menu handler) can notify the user; on
    success this function does not return (restart_app() ends the process)."""
    with tempfile.TemporaryDirectory(prefix="mcp-sync-update-") as tmp_dir:
        wheel_path = download_wheel(info.wheel_url, tmp_dir)
        install_wheel(wheel_path)
    restart_app()
