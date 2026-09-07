# Installs MCP Sync as a tray app on Windows.
# Run from PowerShell: powershell -ExecutionPolicy Bypass -File installers\install_windows.ps1

$ErrorActionPreference = "Stop"

$RepoDir = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $env:USERPROFILE ".mcp-sync\venv"

Write-Host "[+] Installing MCP Sync from: $RepoDir"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[!] python not found on PATH. Install Python 3.9+ from https://www.python.org/downloads/ (check 'Add python.exe to PATH') and re-run."
    exit 1
}

Write-Host "[+] Creating virtual environment at $VenvDir"
python -m venv $VenvDir
& "$VenvDir\Scripts\pip.exe" install --quiet --upgrade pip
& "$VenvDir\Scripts\pip.exe" install --quiet "$RepoDir[windows-notifications]"

Write-Host "[+] Registering Run-at-login and starting the app..."
& "$VenvDir\Scripts\python.exe" -c "from mcp_sync import autostart; autostart.enable()"

Start-Process -FilePath "$VenvDir\Scripts\pythonw.exe" -ArgumentList "-m", "mcp_sync.app"

Write-Host "[OK] Done. Look for the sync icon in the system tray (may be under the '^' overflow arrow)."
Write-Host "     To uninstall: installers\uninstall_windows.ps1"
