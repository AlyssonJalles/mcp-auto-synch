# Removes MCP Sync's Run-at-login entry, running process, and virtual environment.
$ErrorActionPreference = "SilentlyContinue"

$VenvDir = Join-Path $env:USERPROFILE ".mcp-sync\venv"

Write-Host "[+] Stopping MCP Sync..."
if (Test-Path "$VenvDir\Scripts\python.exe") {
    # Run from ~/.mcp-sync so a clone in the current directory can't shadow
    # the installed package on sys.path.
    Push-Location (Join-Path $env:USERPROFILE ".mcp-sync")
    & "$VenvDir\Scripts\python.exe" -c "from mcp_sync import autostart; autostart.disable()"
    Pop-Location
}
Get-Process pythonw, "MCP Sync" -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq "" } | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "[+] Removing virtual environment..."
Remove-Item -Recurse -Force $VenvDir -ErrorAction SilentlyContinue

Write-Host "[OK] MCP Sync removed. Your %USERPROFILE%\.mcp-sync\settings.json was kept (delete manually for a clean slate)."
