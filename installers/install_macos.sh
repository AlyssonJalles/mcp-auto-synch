#!/usr/bin/env bash
# Installs MCP Sync as a menu bar app on macOS (Apple Silicon and Intel).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$HOME/.mcp-sync/venv"

echo "[+] Installing MCP Sync from: $REPO_DIR"

if ! command -v python3 &>/dev/null; then
    echo "[!] python3 not found. Install it (e.g. 'brew install python3') and re-run this script."
    exit 1
fi

echo "[+] Creating virtual environment at $VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$REPO_DIR"

echo "[+] Registering login item and starting the app..."
# launchctl load -w with RunAtLoad already starts the app - do not launch it a
# second time here, or you'll end up with two tray icons/processes.
"$VENV_DIR/bin/python3" - <<PYEOF
from mcp_sync import autostart
autostart.enable()
PYEOF

echo "[✔] Done. Look for the sync icon in the menu bar."
echo "    Logs: /tmp/mcp-sync.log and /tmp/mcp-sync.err"
echo "    To uninstall: installers/uninstall_macos.sh"
