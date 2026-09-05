#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_DIR"

: "${CS30_ENV:=development}"
: "${CS30_FIXTURE_MODE:=true}"
: "${CS30_LOG_DIR:=logs}"
: "${CS30_PORT:=8501}"
: "${CS30_HEADLESS:=false}"
: "${LLM_PROVIDER:=mock}"
export CS30_ENV CS30_FIXTURE_MODE CS30_LOG_DIR CS30_PORT CS30_HEADLESS LLM_PROVIDER
export PYTHONUTF8=1

if [ ! -x ".venv/bin/python" ]; then
    echo "[CS-30] Creating the local Python environment..."
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv .venv
    elif command -v python >/dev/null 2>&1; then
        python -m venv .venv
    else
        echo "[CS-30] Python 3.11 or newer was not found."
        exit 1
    fi
fi

if ! .venv/bin/python -c "import streamlit, pytest, ruff, cs30.config" >/dev/null 2>&1; then
    echo "[CS-30] Installing project dependencies. This is required only on first use..."
    .venv/bin/python -m pip install -e ".[dev,ui]"
fi

mkdir -p "$CS30_LOG_DIR"
echo "[CS-30] Environment: $CS30_ENV"
echo "[CS-30] Fixture mode: $CS30_FIXTURE_MODE"
echo "[CS-30] Log file: $PROJECT_DIR/$CS30_LOG_DIR/cs30.log"
echo "[CS-30] Opening http://127.0.0.1:$CS30_PORT"
echo "[CS-30] Press Ctrl+C to stop the demo."

exec .venv/bin/python -m streamlit run src/cs30/ui/app.py \
    --server.port="$CS30_PORT" \
    --server.headless="$CS30_HEADLESS" \
    --browser.gatherUsageStats=false
