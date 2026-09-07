#!/usr/bin/env bash
# Installs MCP Sync as a tray app on Ubuntu / other Linux desktops
# (requires a GNOME/KDE/XFCE session with a systray, e.g. the
# 'appindicator-support' GNOME extension enabled - on by default on Ubuntu).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$HOME/.mcp-sync/venv"

echo "[+] Installing MCP Sync from: $REPO_DIR"

if ! command -v python3 &>/dev/null; then
    echo "[!] python3 not found. Install it (e.g. 'sudo apt install python3 python3-venv') and re-run."
    exit 1
fi

if ! python3 -c "import ensurepip" &>/dev/null; then
    echo "[!] python3-venv missing. Install with: sudo apt install python3-venv"
    exit 1
fi

# pystray needs a GTK/AppIndicator backend on Linux.
if ! python3 -c "import gi; gi.require_version('AppIndicator3', '0.1')" &>/dev/null && \
   ! python3 -c "import gi; gi.require_version('AyatanaAppIndicator3', '0.1')" &>/dev/null; then
    echo "[i] Tray icon backend not detected. If the icon doesn't appear, run:"
    echo "    sudo apt install -y python3-gi gir1.2-gtk-3.0 gir1.2-ayatana-appindicator3-0.1"
    echo "    (older Ubuntu releases: gir1.2-appindicator3-0.1)"
fi

echo "[+] Creating virtual environment at $VENV_DIR"
python3 -m venv --system-site-packages "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$REPO_DIR"

echo "[+] Registering autostart entry and starting the app..."
"$VENV_DIR/bin/python3" - <<PYEOF
from mcp_sync import autostart
autostart.enable()
PYEOF

nohup "$VENV_DIR/bin/mcp-sync" >/tmp/mcp-sync.log 2>/tmp/mcp-sync.err &
disown

echo "[✔] Done. Look for the sync icon in the top panel."
echo "    Logs: /tmp/mcp-sync.log and /tmp/mcp-sync.err"
echo "    To uninstall: installers/uninstall_linux.sh"
