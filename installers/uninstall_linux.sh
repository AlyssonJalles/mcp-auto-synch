#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="$HOME/.mcp-sync/venv"
DESKTOP_FILE="$HOME/.config/autostart/mcp-sync.desktop"

echo "[+] Stopping MCP Sync..."
rm -f "$DESKTOP_FILE"
pkill -f "mcp_sync.app" 2>/dev/null || true
pkill -f "mcp-sync" 2>/dev/null || true

echo "[+] Removing virtual environment..."
rm -rf "$VENV_DIR"

echo "[✔] MCP Sync removed. Your ~/.mcp-sync/settings.json was kept (delete it manually if you want a clean slate)."
