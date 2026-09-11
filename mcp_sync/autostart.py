"""Registers/unregisters the app to start automatically at login, per OS."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig

from . import __version__
from .platform_utils import IS_LINUX, IS_MAC, IS_WINDOWS, home

_LABEL = "com.mcpsync.app"
_PROC_NAME = "mcp-auto-synch"


def _launch_command() -> list[str]:
    """Command that (re)starts the tray app, using the same interpreter/venv
    that is currently running (works whether installed via pipx, a venv, or
    a frozen build)."""
    return [sys.executable, "-m", "mcp_sync.app"]


# --------------------------------------------------------------------- macOS
#
# Both the process name shown in Activity Monitor/`ps` and the icon shown
# there (and in the Force Quit Applications window) are read from the
# *executed file itself*, not anything settable at runtime from inside the
# process - `setproctitle` and `NSApplication.setApplicationIconImage_` only
# affect `ps`/`top`'s rendering and the Dock/Cmd-Tab icon respectively, not
# these two surfaces. Getting both right requires a real, if minimal, .app
# bundle: a fixed-name executable under Contents/MacOS (kernel process name),
# plus an Info.plist declaring Contents/Resources/AppIcon.icns (the icon
# LaunchServices resolves for that process). `_macos_ensure_app_bundle`
# builds this once under ~/.mcp-sync and self-heals it on every enable().


def _macos_app_bundle_dir() -> str:
    return os.path.join(home(), ".mcp-sync", "MCP Sync.app")


def _macos_applications_shortcut() -> str:
    return "/Applications/MCP Sync.app"


def _macos_ensure_applications_shortcut(bundle_dir: str) -> None:
    """Symlinks the real .app bundle into /Applications so the same icon shown
    in Activity Monitor also shows up in Launchpad/Spotlight. Best-effort:
    skipped silently if /Applications isn't writable without elevation."""
    shortcut = _macos_applications_shortcut()
    if os.path.realpath(shortcut) == os.path.realpath(bundle_dir):
        return
    try:
        if os.path.lexists(shortcut):
            if not os.path.islink(shortcut):
                return  # a real (non-symlink) app is there - don't touch it
            os.remove(shortcut)
        os.symlink(bundle_dir, shortcut)
    except OSError:
        return
    # Spotlight (Cmd+Space) indexes on its own schedule and can take a while
    # to pick up a freshly created symlink - nudge it immediately so the
    # shortcut is searchable right after install instead of after a delay.
    try:
        subprocess.run(["mdimport", shortcut], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        pass


def _macos_app_icon_source() -> str:
    return os.path.join(os.path.dirname(__file__), "assets", "logos", "_mcp_synch.png")


def _macos_ensure_named_interpreter(target: str) -> None:
    real_interpreter = os.path.realpath(sys.executable)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(target) and os.path.realpath(target) == real_interpreter:
        return
    if os.path.lexists(target):
        os.remove(target)
    try:
        os.link(real_interpreter, target)
    except OSError:
        shutil.copy2(real_interpreter, target)


def _macos_ensure_icon(resources_dir: str) -> None:
    """Builds Contents/Resources/AppIcon.icns from the app's own PNG logo via
    `sips`/`iconutil` (both ship with every macOS install). Skipped/left as-is
    if the source art is missing or those tools error out - a missing icon
    just means the bundle falls back to a generic one, not a broken app."""
    icns_path = os.path.join(resources_dir, "AppIcon.icns")
    source_png = _macos_app_icon_source()
    if not os.path.exists(source_png):
        return
    if os.path.exists(icns_path) and os.path.getmtime(icns_path) >= os.path.getmtime(source_png):
        return
    iconset_dir = icns_path + ".iconset"
    try:
        if os.path.exists(iconset_dir):
            shutil.rmtree(iconset_dir)
        os.makedirs(iconset_dir)
        for size in (16, 32, 128, 256, 512):
            subprocess.run(
                ["sips", "-z", str(size), str(size), source_png, "--out", os.path.join(iconset_dir, f"icon_{size}x{size}.png")],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            double = size * 2
            subprocess.run(
                ["sips", "-z", str(double), str(double), source_png, "--out", os.path.join(iconset_dir, f"icon_{size}x{size}@2x.png")],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", icns_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    finally:
        shutil.rmtree(iconset_dir, ignore_errors=True)


def _macos_ensure_app_bundle() -> str:
    """Builds/refreshes the .app bundle and returns its executable's path."""
    bundle_dir = _macos_app_bundle_dir()
    contents_dir = os.path.join(bundle_dir, "Contents")
    macos_dir = os.path.join(contents_dir, "MacOS")
    resources_dir = os.path.join(contents_dir, "Resources")
    os.makedirs(macos_dir, exist_ok=True)
    os.makedirs(resources_dir, exist_ok=True)

    executable = os.path.join(macos_dir, _PROC_NAME)
    _macos_ensure_named_interpreter(executable)
    _macos_ensure_icon(resources_dir)

    info_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>MCP Sync</string>
    <key>CFBundleDisplayName</key>
    <string>MCP Sync</string>
    <key>CFBundleIdentifier</key>
    <string>com.mcpsync.app.bundle</string>
    <key>CFBundleVersion</key>
    <string>{__version__}</string>
    <key>CFBundleShortVersionString</key>
    <string>{__version__}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>{_PROC_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
"""
    with open(os.path.join(contents_dir, "Info.plist"), "w", encoding="utf-8") as fh:
        fh.write(info_plist)

    # Nudges LaunchServices to pick up the (re)built bundle/icon immediately,
    # instead of waiting for its own periodic rescan.
    lsregister = (
        "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
        "LaunchServices.framework/Support/lsregister"
    )
    os.system(f'"{lsregister}" -f "{bundle_dir}" >/dev/null 2>&1')
    _macos_ensure_applications_shortcut(bundle_dir)

    return executable


def _macos_plist_path() -> str:
    return os.path.join(home(), "Library", "LaunchAgents", f"{_LABEL}.plist")


def _macos_enable() -> None:
    interpreter = _macos_ensure_app_bundle()
    cmd = [interpreter, "-m", "mcp_sync.app"]
    args_xml = "\n".join(f"        <string>{c}</string>" for c in cmd)
    # The renamed interpreter file above is no longer at its original
    # install path, so it can't find its own standard library relative to
    # itself the way it normally would - PYTHONHOME points it back at the
    # real interpreter's install prefix, and PYTHONPATH points it at this
    # venv's site-packages (where mcp_sync and its dependencies live),
    # since it won't auto-detect the venv via a co-located pyvenv.cfg either.
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONHOME</key>
        <string>{sys.base_prefix}</string>
        <key>PYTHONPATH</key>
        <string>{sysconfig.get_paths()['purelib']}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>/tmp/mcp-sync.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/mcp-sync.err</string>
</dict>
</plist>
"""
    path = _macos_plist_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(plist)
    os.system(f'launchctl unload "{path}" >/dev/null 2>&1')
    os.system(f'launchctl load -w "{path}" >/dev/null 2>&1')


def _macos_disable() -> None:
    path = _macos_plist_path()
    if os.path.exists(path):
        os.system(f'launchctl unload "{path}" >/dev/null 2>&1')
        os.remove(path)


def _macos_is_enabled() -> bool:
    return os.path.exists(_macos_plist_path())


# -------------------------------------------------------------------- Linux

def _linux_desktop_path() -> str:
    return os.path.join(home(), ".config", "autostart", "mcp-sync.desktop")


def _linux_icon_path() -> str:
    return os.path.join(home(), ".mcp-sync", "icons", "app.png")


_BRAND_ICON_ASSET = os.path.join(os.path.dirname(__file__), "assets", "logos", "_mcp_synch.png")


def _linux_ensure_icon() -> str:
    """Writes the app-icon PNG used by both .desktop entries below and
    returns its path.

    Uses the bundled MCP Synch brand logo - the same artwork the macOS build
    ships - rather than anything drawn at runtime, so the icon in GNOME's
    Activities search matches the app's real identity across platforms. The
    source art isn't square (1600x1515) while launcher icons are assumed to
    be, so it's padded to a square canvas here; scaling a non-square image
    into a square slot otherwise stretches it. Falls back to the generated
    icon, and finally to a generic themed icon name, rather than ever
    leaving Icon= pointing at a file that doesn't exist."""
    path = _linux_icon_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        return "view-refresh"

    try:
        from PIL import Image

        with Image.open(_BRAND_ICON_ASSET) as src:
            logo = src.convert("RGBA")
        side = max(logo.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2))
        canvas.save(path, "PNG")
        return path
    except Exception:
        pass

    try:
        from .tray_icon import build_app_icon

        build_app_icon().save(path, "PNG")
        return path
    except Exception:
        return "view-refresh"


def _linux_enable() -> None:
    cmd = " ".join(_launch_command())
    entry = f"""[Desktop Entry]
Type=Application
Name=MCP Sync
Comment=Keeps MCP server configuration in sync across AI coding tools
Exec={cmd}
Icon={_linux_ensure_icon()}
Terminal=false
X-GNOME-Autostart-enabled=true
"""
    path = _linux_desktop_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(entry)


def _linux_disable() -> None:
    path = _linux_desktop_path()
    if os.path.exists(path):
        os.remove(path)


def _linux_is_enabled() -> bool:
    return os.path.exists(_linux_desktop_path())


# ------------------------------------------------------- Linux app launcher
#
# Separate from the autostart entry above (which only controls whether the
# app runs automatically at login): this is what makes MCP Sync show up as
# a clickable icon in GNOME's Activities/app-grid search, regardless of the
# "Start at Login" preference. Mirrors the spirit of
# _macos_ensure_applications_shortcut - a discoverable, clickable launcher
# separate from the login-item mechanism.


def _linux_applications_desktop_path() -> str:
    return os.path.join(home(), ".local", "share", "applications", "mcp-sync.desktop")


def ensure_application_launcher() -> None:
    """Writes/refreshes the Activities-grid .desktop entry. Safe and cheap
    to call on every startup - it just overwrites the same file, so it
    self-heals if the venv path or icon ever change (e.g. after a
    reinstall)."""
    if not IS_LINUX:
        return
    cmd = " ".join(_launch_command())
    entry = f"""[Desktop Entry]
Type=Application
Name=MCP Sync
Comment=Keeps MCP server configuration in sync across AI coding tools
Exec={cmd}
Icon={_linux_ensure_icon()}
Terminal=false
Categories=Utility;
"""
    path = _linux_applications_desktop_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(entry)
    except OSError:
        pass


# ------------------------------------------------------------------ Windows

_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_WIN_VALUE_NAME = "MCPSync"


def _windows_enable() -> None:
    import winreg  # type: ignore

    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    command = f'"{pythonw}" -m mcp_sync.app'
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY)
    winreg.SetValueEx(key, _WIN_VALUE_NAME, 0, winreg.REG_SZ, command)
    winreg.CloseKey(key)


def _windows_disable() -> None:
    import winreg  # type: ignore

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, _WIN_VALUE_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass


def _windows_is_enabled() -> bool:
    import winreg  # type: ignore

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _WIN_VALUE_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False


# ------------------------------------------------------------------- public

def enable() -> None:
    try:
        if IS_MAC:
            _macos_enable()
        elif IS_LINUX:
            _linux_enable()
        elif IS_WINDOWS:
            _windows_enable()
    except Exception:
        pass


def disable() -> None:
    try:
        if IS_MAC:
            _macos_disable()
        elif IS_LINUX:
            _linux_disable()
        elif IS_WINDOWS:
            _windows_disable()
    except Exception:
        pass


def is_enabled() -> bool:
    try:
        if IS_MAC:
            return _macos_is_enabled()
        if IS_LINUX:
            return _linux_is_enabled()
        if IS_WINDOWS:
            return _windows_is_enabled()
    except Exception:
        pass
    return False
