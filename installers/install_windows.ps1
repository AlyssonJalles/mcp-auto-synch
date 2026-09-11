# Installs MCP Sync as a tray app on Windows.
# Run from PowerShell: powershell -ExecutionPolicy Bypass -File installers\install_windows.ps1
#
# Python 3.11 is installed automatically if not found on PATH.

$ErrorActionPreference = "Stop"

$RepoDir  = Split-Path -Parent $PSScriptRoot
$VenvDir  = Join-Path $env:USERPROFILE ".mcp-sync\venv"
$PythonMinMajor = 3
$PythonMinMinor = 9

# ---------------------------------------------------------------------------
# Helper: resolve the python executable to use
# ---------------------------------------------------------------------------
function Find-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        $exe = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($exe) {
            # Verify it is >= 3.9
            $ver = & $exe.Source --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                $maj = [int]$Matches[1]; $min = [int]$Matches[2]
                if ($maj -gt $PythonMinMajor -or ($maj -eq $PythonMinMajor -and $min -ge $PythonMinMinor)) {
                    return $exe.Source
                }
            }
        }
    }
    return $null
}

# ---------------------------------------------------------------------------
# Auto-install Python 3.11 if missing
# ---------------------------------------------------------------------------
function Install-Python {
    $pythonVersion = "3.11.9"
    $installerUrl  = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-amd64.exe"
    $installerPath = Join-Path $env:TEMP "python-$pythonVersion-amd64.exe"

    Write-Host "[+] Python not found. Downloading Python $pythonVersion..."
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing

    Write-Host "[+] Installing Python $pythonVersion silently (this may take a minute)..."
    $args = @(
        "/quiet",
        "InstallAllUsers=0",          # per-user install (no admin needed)
        "PrependPath=1",              # add to PATH
        "Include_pip=1",
        "Include_launcher=1",
        "Include_test=0"
    )
    $proc = Start-Process -FilePath $installerPath -ArgumentList $args -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        Write-Host "[!] Python installer exited with code $($proc.ExitCode). Please install Python 3.9+ manually from https://www.python.org/downloads/ and re-run."
        exit 1
    }

    # Reload PATH so the new python.exe is visible in the current session
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "Machine")

    Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
    Write-Host "[+] Python installed successfully."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
Write-Host "[+] Installing MCP Sync from: $RepoDir"

$PythonExe = Find-Python
if (-not $PythonExe) {
    Install-Python
    $PythonExe = Find-Python
}

if (-not $PythonExe) {
    Write-Host "[!] Could not locate a Python 3.9+ executable even after installation."
    Write-Host "    Please open a NEW PowerShell window and re-run this script,"
    Write-Host "    or install Python manually from https://www.python.org/downloads/"
    exit 1
}

Write-Host "[+] Using Python: $PythonExe"

Write-Host "[+] Creating virtual environment at $VenvDir"
& $PythonExe -m venv $VenvDir
& "$VenvDir\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$VenvDir\Scripts\python.exe" -m pip install --quiet "$RepoDir[windows-notifications]"

Write-Host "[+] Registering Run-at-login..."
& "$VenvDir\Scripts\python.exe" -c "from mcp_sync import autostart; autostart.enable()"

Write-Host "[+] Creating Start Menu shortcut and icon..."
& "$VenvDir\Scripts\python.exe" -c "from mcp_sync.win_shortcuts import setup_all; setup_all()"

Write-Host "[+] Starting MCP Synch..."
# "MCP Sync.exe" (created by autostart.enable() above) is a renamed copy of
# pythonw.exe, so the app shows up as "MCP Sync" in Task Manager instead of
# "Python".
Start-Process -FilePath "$VenvDir\Scripts\MCP Sync.exe" -ArgumentList "-m", "mcp_sync.app" `
    -WorkingDirectory (Join-Path $env:USERPROFILE ".mcp-sync")

Write-Host ""
Write-Host "[OK] MCP Synch installed successfully!"
Write-Host "     - System tray: look for the copper 'MCP' icon (may be under '^')"
Write-Host "     - Start Menu: search for 'MCP Synch'"
Write-Host "     - To uninstall: installers\uninstall_windows.ps1"
