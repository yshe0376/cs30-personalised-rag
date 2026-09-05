#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
echo "[CS-30] Starting the fixture-backed staging preview."
echo "[CS-30] This is not the real retriever or LLM."

CS30_ENV=staging \
CS30_FIXTURE_MODE=true \
CS30_LOG_DIR=logs \
LLM_PROVIDER=mock \
exec "$PROJECT_DIR/start_demo.sh"
