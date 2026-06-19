<#
.SYNOPSIS
    Start the Budget- & Liquiditätsplanung app (NiceGUI + SQLite).

.DESCRIPTION
    Ensures the local virtual environment exists and dependencies are installed,
    then launches the app. Use -Debug for auto-reload and verbose logging.

.PARAMETER Debug
    Run in debug mode: auto-reload on file changes + verbose (debug) logging.

.PARAMETER Port
    Port to listen on (default 8080).

.PARAMETER NoShow
    Do not auto-open the browser.

.PARAMETER Install
    Force (re)install of dependencies before starting.

.EXAMPLE
    .\run.ps1
    .\run.ps1 -Debug
    .\run.ps1 -Port 9000 -NoShow
#>
[CmdletBinding()]
param(
    [switch]$Debug,
    [int]$Port = 8137,
    [switch]$NoShow,
    [switch]$Install
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

# 1. Create the virtual environment if it is missing.
if (-not (Test-Path $venvPython)) {
    Write-Host '[run] .venv not found - creating virtual environment...' -ForegroundColor Yellow
    python -m venv .venv
    $Install = $true
}

# 2. Install dependencies (first run, or when -Install is passed).
$marker = Join-Path $PSScriptRoot '.venv\.deps-installed'
if ($Install -or -not (Test-Path $marker)) {
    Write-Host '[run] Installing dependencies...' -ForegroundColor Yellow
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
    New-Item -ItemType File -Path $marker -Force | Out-Null
}

# 3. Translate switches into the env vars run.py understands.
$env:BL_PORT = $Port
$env:BL_SHOW = if ($NoShow) { '0' } else { '1' }

if ($Debug) {
    $env:BL_DEBUG = '1'
    Write-Host "[run] Starting in DEBUG mode on http://localhost:$Port" -ForegroundColor Cyan
} else {
    $env:BL_DEBUG = '0'
    Write-Host "[run] Starting on http://localhost:$Port" -ForegroundColor Green
}

# 4. Launch.
& $venvPython run.py
