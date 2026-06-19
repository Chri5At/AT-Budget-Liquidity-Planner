@echo off
REM Start the Budget- & Liquiditätsplanung app using the local virtual environment.
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py
pause
