@echo off
setlocal
set "CS30_ENV=staging"
set "CS30_FIXTURE_MODE=true"
set "CS30_LOG_DIR=logs"
if not defined CS30_PORT set "CS30_PORT=8502"
set "LLM_PROVIDER=mock"
echo [CS-30] Starting the fixture-backed staging preview.
echo [CS-30] This is not the real retriever or LLM.
echo [CS-30] Staging preview port: %CS30_PORT%
call "%~dp0start_demo.cmd"
exit /b %ERRORLEVEL%
