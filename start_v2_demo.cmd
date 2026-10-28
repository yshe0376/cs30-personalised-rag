@echo off
setlocal
cd /d "%~dp0"
if not defined CS30_PYTHON (
    if exist ".venv\Scripts\python.exe" (
        set "CS30_PYTHON=%CD%\.venv\Scripts\python.exe"
    ) else if exist "..\cs30-personalised-rag-v2-m8\.venv\Scripts\python.exe" (
        set "CS30_PYTHON=%CD%\..\cs30-personalised-rag-v2-m8\.venv\Scripts\python.exe"
    ) else if exist "..\cs30-personalised-rag\.venv\Scripts\python.exe" (
        set "CS30_PYTHON=%CD%\..\cs30-personalised-rag\.venv\Scripts\python.exe"
    ) else (
        set "CS30_PYTHON=python"
    )
)
if not defined CS30_PORT set "CS30_PORT=8512"
if not defined CS30_UI_CORPUS if exist "..\W8\v2-ui-runtime\corpus\manifest.json" set "CS30_UI_CORPUS=%CD%\..\W8\v2-ui-runtime\corpus"
echo [CS-30] V2 corpus: %CS30_UI_CORPUS%
if defined DEEPINFRA_API_KEY (echo [CS-30] DeepInfra key: configured) else (echo [CS-30] DeepInfra key: not set - the page opens in Fixture mode)
set "PYTHONUTF8=1"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
echo [CS-30] Python: %CS30_PYTHON%
"%CS30_PYTHON%" -c "import streamlit" 2>nul
if errorlevel 1 (
    echo.
    echo [CS-30] ERROR: Streamlit is not installed for this Python.
    echo [CS-30] Install it with:  "%CS30_PYTHON%" -m pip install "streamlit>=1.50,<2"
    echo.
    pause
    exit /b 1
)
echo [CS-30] V2 question-answering UI: http://127.0.0.1:%CS30_PORT%
echo [CS-30] Models are called only by user submission in team mode. No scoring batch is started.
"%CS30_PYTHON%" -m streamlit run src\cs30\ui\v2_app.py --server.address=127.0.0.1 --server.port=%CS30_PORT% --server.headless=true --theme.base=light --theme.primaryColor=#f06f54 --theme.font=sans-serif --browser.gatherUsageStats=false
set "CS30_EXIT=%ERRORLEVEL%"
if not "%CS30_EXIT%"=="0" (
    echo.
    echo [CS-30] Streamlit stopped with error code %CS30_EXIT%. See the messages above.
    pause
)
exit /b %CS30_EXIT%
