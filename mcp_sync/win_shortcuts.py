"""Windows Start Menu and Program Files shortcuts for MCP Synch.

Generates a proper multi-resolution .ico from the bundled PNG logo and
creates .lnk shortcuts so the app appears in the Start Menu and in
C:\\Program Files (x86)\\MCP Synch\\.

No extra dependencies beyond Pillow (already required) and subprocess.
"""
from __future__ import annotations

import os
import subprocess

_LOGO_PNG = os.path.join(os.path.dirname(__file__), "assets", "logos", "_mcp_synch.png")
_ICO_PATH = os.path.join(os.path.expanduser("~"), ".mcp-sync", "mcp_synch.ico")
_APP_NAME = "MCP Synch"
_PROG_FILES_DIR = r"C:\Program Files (x86)\MCP Synch"
_START_MENU_DIR = os.path.join(
    os.environ.get("APPDATA", ""),
    r"Microsoft\Windows\Start Menu\Programs",
)


def generate_ico(out_path: str = _ICO_PATH) -> str:
    """Convert the bundled PNG logo to a multi-resolution Windows .ico file."""
    from PIL import Image

    src = Image.open(_LOGO_PNG).convert("RGBA")
    sizes = [256, 128, 64, 48, 32, 16]
    frames = [src.resize((s, s), Image.LANCZOS) for s in sizes]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    frames[0].save(
        out_path, format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    return out_path


def _create_lnk(lnk_path: str, ico_path: str) -> None:
    """Create a .lnk via a PowerShell WScript.Shell one-liner."""
    from .autostart import ensure_named_executable

    # Points at the "MCP Sync.exe" copy of pythonw.exe (not pythonw.exe
    # itself) so double-clicking the shortcut also shows up as "MCP Sync" in
    # Task Manager, not "Python".
    target = ensure_named_executable().replace("\\", "\\\\")
    icon = ico_path.replace("\\", "\\\\")
    lnk = lnk_path.replace("\\", "\\\\")
    wd = os.path.join(os.path.expanduser("~"), ".mcp-sync").replace("\\", "\\\\")
    desc = "MCP Synch - synchronizes MCP server configs across AI tools"

    ps = (
        f'$ws = New-Object -ComObject WScript.Shell; '
        f'$sc = $ws.CreateShortcut("{lnk}"); '
        f'$sc.TargetPath = "{target}"; '
        f'$sc.Arguments = "-m mcp_sync.app"; '
        f'$sc.IconLocation = "{icon},0"; '
        f'$sc.Description = "{desc}"; '
        f'$sc.WorkingDirectory = "{wd}"; '
        f'$sc.WindowStyle = 7; '
        f'$sc.Save()'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        check=True, capture_output=True,
    )


def setup_start_menu(ico_path: str | None = None) -> None:
    """Create Start Menu → Programs → MCP Synch.lnk (no admin needed)."""
    ico = ico_path or generate_ico()
    os.makedirs(_START_MENU_DIR, exist_ok=True)
    lnk = os.path.join(_START_MENU_DIR, f"{_APP_NAME}.lnk")
    _create_lnk(lnk, ico)
    print(f"[+] Start Menu shortcut: {lnk}")


def setup_prog_files(ico_path: str | None = None) -> None:
    """Create C:\\Program Files (x86)\\MCP Synch\\MCP Synch.lnk (needs admin)."""
    ico = ico_path or generate_ico()
    try:
        os.makedirs(_PROG_FILES_DIR, exist_ok=True)
    except PermissionError:
        print(
            f"[!] Skipping {_PROG_FILES_DIR} — needs Administrator rights.\n"
            "    Re-run the installer from an elevated PowerShell to enable."
        )
        return
    lnk = os.path.join(_PROG_FILES_DIR, f"{_APP_NAME}.lnk")
    _create_lnk(lnk, ico)
    print(f"[+] Program Files shortcut: {lnk}")


def setup_all() -> None:
    """Generate the .ico and create both shortcuts."""
    print("[+] Generating Windows icon (.ico)…")
    ico = generate_ico()
    print(f"    → {ico}")
    setup_start_menu(ico)
    setup_prog_files(ico)


if __name__ == "__main__":
    setup_all()
