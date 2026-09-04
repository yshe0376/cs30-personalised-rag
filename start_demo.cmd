@echo off
setlocal
cd /d "%~dp0"

if not defined CS30_ENV set "CS30_ENV=development"
if not defined CS30_FIXTURE_MODE set "CS30_FIXTURE_MODE=true"
if not defined CS30_LOG_DIR set "CS30_LOG_DIR=logs"
if not defined CS30_PORT set "CS30_PORT=8501"
if not defined CS30_HEADLESS set "CS30_HEADLESS=false"
if not defined LLM_PROVIDER set "LLM_PROVIDER=mock"
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\python.exe" (
    echo [CS-30] Creating the local Python environment...
    py -3.11 -m venv .venv >nul 2>nul
    if errorlevel 1 py -3 -m venv .venv >nul 2>nul
    if errorlevel 1 python -m venv .venv >nul 2>nul
    if errorlevel 1 (
        echo [CS-30] Python 3.11 or newer was not found.
        echo Install Python, then run this file again.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -c "import streamlit, pytest, ruff, cs30.config" >nul 2>nul
if errorlevel 1 (
    echo [CS-30] Installing project dependencies. This is required only on first use...
    ".venv\Scripts\python.exe" -m pip install -e ".[dev,ui]"
    if errorlevel 1 (
        echo [CS-30] Dependency installation failed. Check the internet connection.
        pause
        exit /b 1
    )
)

if not exist "%CS30_LOG_DIR%" mkdir "%CS30_LOG_DIR%"
echo [CS-30] Environment: %CS30_ENV%
echo [CS-30] Fixture mode: %CS30_FIXTURE_MODE%
echo [CS-30] Log file: %CD%\%CS30_LOG_DIR%\cs30.log
echo [CS-30] Opening http://127.0.0.1:%CS30_PORT%
echo [CS-30] Keep this window open. Press Ctrl+C to stop the demo.

".venv\Scripts\python.exe" -m streamlit run src\cs30\ui\app.py --server.port=%CS30_PORT% --server.headless=%CS30_HEADLESS% --browser.gatherUsageStats=false
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo [CS-30] The demo stopped with exit code %EXIT_CODE%.
    echo See %CS30_LOG_DIR%\cs30.log and docs\troubleshooting.md.
    pause
)
exit /b %EXIT_CODE%
