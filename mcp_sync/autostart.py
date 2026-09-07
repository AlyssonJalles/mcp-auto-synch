"""Registers/unregisters the app to start automatically at login, per OS."""
from __future__ import annotations

import os
import sys

from .platform_utils import IS_LINUX, IS_MAC, IS_WINDOWS, home

_LABEL = "com.mcpsync.app"


def _launch_command() -> list[str]:
    """Command that (re)starts the tray app, using the same interpreter/venv
    that is currently running (works whether installed via pipx, a venv, or
    a frozen build)."""
    return [sys.executable, "-m", "mcp_sync.app"]


# --------------------------------------------------------------------- macOS

def _macos_plist_path() -> str:
    return os.path.join(home(), "Library", "LaunchAgents", f"{_LABEL}.plist")


def _macos_enable() -> None:
    cmd = _launch_command()
    args_xml = "\n".join(f"        <string>{c}</string>" for c in cmd)
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


def _linux_enable() -> None:
    cmd = " ".join(_launch_command())
    entry = f"""[Desktop Entry]
Type=Application
Name=MCP Sync
Comment=Keeps MCP server configuration in sync across AI coding tools
Exec={cmd}
Icon=view-refresh
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
