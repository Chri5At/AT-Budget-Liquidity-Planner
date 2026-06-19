@echo off
REM Start the Budget- & Liquiditätsplanung app in DEBUG mode (auto-reload + verbose logging).
cd /d "%~dp0"
set BL_DEBUG=1
".venv\Scripts\python.exe" run.py --debug
pause
