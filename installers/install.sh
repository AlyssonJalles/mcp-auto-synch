#!/usr/bin/env bash
# Installs the latest released version of MCP Sync as a tray app directly
# from GitHub Releases - no git clone required.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/AlyssonJalles/mcp-auto-synch/main/installers/install.sh | bash
set -euo pipefail

REPO="AlyssonJalles/mcp-auto-synch"
VENV_DIR="$HOME/.mcp-sync/venv"
OS="$(uname -s)"

if ! command -v python3 &>/dev/null; then
    echo "[!] python3 not found. Install it and re-run this script."
    exit 1
fi

if [ "$OS" = "Linux" ]; then
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
elif [ "$OS" != "Darwin" ]; then
    echo "[!] This script supports macOS and Linux only. For Windows, use installers/install_windows.ps1."
    exit 1
fi

echo "[+] Looking up latest release of $REPO..."
WHEEL_URL="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
urls = [a['browser_download_url'] for a in data.get('assets', []) if a['name'].endswith('.whl')]
print(urls[0] if urls else '')
")"

if [ -z "$WHEEL_URL" ]; then
    echo "[!] Could not find a .whl asset on the latest GitHub release. Aborting."
    exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
TMP_WHEEL="$TMP_DIR/$(basename "$WHEEL_URL")"
echo "[+] Downloading $WHEEL_URL"
curl -fsSL "$WHEEL_URL" -o "$TMP_WHEEL"

echo "[+] Creating virtual environment at $VENV_DIR"
if [ "$OS" = "Linux" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
else
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$TMP_WHEEL"

echo "[+] Registering login item and starting the app..."
# launchctl load -w with RunAtLoad already starts the app on macOS - do not
# launch it a second time here, or you'll end up with two tray icons/processes.
"$VENV_DIR/bin/python3" - <<PYEOF
from mcp_sync import autostart
autostart.enable()
PYEOF

if [ "$OS" = "Linux" ]; then
    nohup "$VENV_DIR/bin/mcp-sync" >/tmp/mcp-sync.log 2>/tmp/mcp-sync.err &
    disown
fi

echo "[✔] Done. Look for the sync icon in the menu bar / top panel."
echo "    Logs: /tmp/mcp-sync.log and /tmp/mcp-sync.err"
echo "    To uninstall: rm -rf ~/.mcp-sync (and remove the login item/autostart entry)"
