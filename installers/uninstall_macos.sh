#!/usr/bin/env bash
# Removes MCP Sync's login item, running process, and virtual environment.
set -euo pipefail

VENV_DIR="$HOME/.mcp-sync/venv"
BIN_DIR="$HOME/.mcp-sync/bin"
APP_BUNDLE="$HOME/.mcp-sync/MCP Sync.app"
PLIST="$HOME/Library/LaunchAgents/com.mcpsync.app.plist"

echo "[+] Stopping MCP Sync..."
if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" >/dev/null 2>&1 || true
    rm -f "$PLIST"
fi
pkill -f "mcp_sync.app" 2>/dev/null || true
pkill -f "mcp-sync" 2>/dev/null || true

echo "[+] Removing virtual environment..."
rm -rf "$VENV_DIR" "$BIN_DIR" "$APP_BUNDLE"

echo "[✔] MCP Sync removed. Your ~/.mcp-sync/settings.json was kept (delete it manually if you want a clean slate)."
