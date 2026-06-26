<#
Build a single-file Windows .exe of the Budget and Liquiditaet planning app.

Output:  dist\BudgetLiquidity.exe  (unsigned, native desktop window)

What this produces is a *clean* app: it bundles only the Python code + NiceGUI
assets. It does NOT contain the data\ folder, so none of your local planning
data ships with it. On the target machine the app creates a fresh database in
%LOCALAPPDATA%\BudgetLiquidity\ on first launch, seeded with fictional demo data.

Usage (from anywhere):
    powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
#>
$ErrorActionPreference = "Stop"

# Project root is the parent of this script's folder.
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    throw "Virtual environment not found at $py - create it and install requirements first."
}

Write-Host "==> Installing build dependencies (pyinstaller, pywebview)..." -ForegroundColor Cyan
& $py -m pip install --disable-pip-version-check -r (Join-Path $root "requirements-packaging.txt")

Write-Host "==> Building single-file native-window executable..." -ForegroundColor Cyan
# nicegui-pack shells out to `pyinstaller` by bare name, so the venv's Scripts
# dir must be on PATH for this process.
$scripts = Join-Path $root ".venv\Scripts"
$env:Path = "$scripts;$env:Path"
# --windowed: no console window (valid because run.py uses native=True when frozen).
# --onefile:  one .exe to hand over.
# --clean/--noconfirm: reproducible, non-interactive build.
$pack = Join-Path $root ".venv\Scripts\nicegui-pack.exe"
$icon = Join-Path $root "packaging\icon.ico"
$iconArgs = @()
if (Test-Path $icon) { $iconArgs = @("--icon", $icon) }
& $pack --onefile --windowed --name "BudgetLiquidity" --clean --noconfirm @iconArgs (Join-Path $root "run.py")

$exe = Join-Path $root "dist\BudgetLiquidity.exe"
if (Test-Path $exe) {
    $sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host ""
    Write-Host "==> Done: $exe  ($sizeMb MB)" -ForegroundColor Green
    Write-Host "    Hand this single file over. Windows SmartScreen will show an" -ForegroundColor DarkGray
    Write-Host "    'unrecognized app' prompt (it is unsigned) - click 'More info' then 'Run anyway'." -ForegroundColor DarkGray
} else {
    throw "Build finished but $exe was not found - check the PyInstaller output above."
}
