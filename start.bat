@echo off
REM Celestia — double-click to start the desktop shell
REM Starts the Python API server and opens the Tauri window.

cd /d "%~dp0"

REM Prefer the project venv so all pip-installed deps (pynput, mem0, …) are available.
REM Fall back to the system Python if the venv has not been created yet.
if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
) else (
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo [error] Python not found. Install Python 3.11+ or run: python -m venv venv
        pause
        exit /b 1
    )
    echo [celestia] venv not found — using system Python. Run "pip install -r requirements.txt" if deps are missing.
    set PYTHON=python
)

echo [celestia] Starting shell...
%PYTHON% run_celestia.py --shell

REM If the above exits non-zero, show the error before closing
if %errorlevel% neq 0 (
    echo.
    echo [error] Celestia exited with code %errorlevel%.
    echo Common fixes:
    echo   - Run: pip install -r requirements.txt
    echo   - Run: cd shell ^&^& npm install
    echo   - Make sure Ollama is running: ollama serve
    pause
)
