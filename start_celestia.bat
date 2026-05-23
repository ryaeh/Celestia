@echo off
setlocal
cd /d "%~dp0"

set PY=%~dp0venv\Scripts\python.exe
if not exist "%PY%" (
    echo [FAIL] venv not found. Create: python -m venv venv
    exit /b 1
)

echo === Celestia preflight ===
"%PY%" run_celestia.py --check
if errorlevel 1 (
    echo.
    echo Fix issues above, then retry.
    pause
    exit /b 1
)

echo.
echo === Celestia interactive ===
"%PY%" run_celestia.py -i
