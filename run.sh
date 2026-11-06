#!/usr/bin/env bash
# Autonomous Outcome-First Agent Controller
# Contract: ./run.sh <SIM_URL> runs until the scenario finishes with no manual intervention.
set -euo pipefail

SIM_URL="${1:?usage: ./run.sh <SIM_URL>}"
shift || true

# Locate python executable
PYTHON_BIN="python"
if command -v "C:/Users/Anurag rajak/AppData/Local/Programs/Python/Python310/python.exe" >/dev/null 2>&1; then
    PYTHON_BIN="C:/Users/Anurag rajak/AppData/Local/Programs/Python/Python310/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" -m controller.main --url "$SIM_URL" "$@"
