@echo off
setlocal
cd /d "%~dp0"
if not defined CS30_PYTHON (
    if exist ".venv\Scripts\python.exe" (
        set "CS30_PYTHON=%CD%\.venv\Scripts\python.exe"
    ) else (
        set "CS30_PYTHON=python"
    )
)
if not defined CS30_PORT set "CS30_PORT=8512"
set "PYTHONUTF8=1"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
echo [CS-30] V2 fixture UI: http://127.0.0.1:%CS30_PORT%
echo [CS-30] No retriever, model API or scoring batch is started.
"%CS30_PYTHON%" -m streamlit run src\cs30\ui\v2_app.py --server.address=127.0.0.1 --server.port=%CS30_PORT% --server.headless=true --theme.base=light --theme.primaryColor=#f06f54 --theme.font=sans-serif --browser.gatherUsageStats=false
exit /b %ERRORLEVEL%
