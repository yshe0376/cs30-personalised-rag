@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
if not defined CS30_PYTHON (
    if exist ".venv\Scripts\python.exe" (
        set "CS30_PYTHON=%CD%\.venv\Scripts\python.exe"
    ) else (
        set "CS30_PYTHON=python"
    )
)
set "PYTHONUTF8=1"
if not defined CS30_PORT set "CS30_PORT=8512"
"%CS30_PYTHON%" -m streamlit run src\cs30\ui\learning_app.py --server.address 127.0.0.1 --server.port=%CS30_PORT% --theme.base=light --theme.primaryColor=#f06f54 --browser.gatherUsageStats=false
