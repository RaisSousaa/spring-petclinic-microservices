#!/usr/bin/env bash
# ==============================================================================
# Script auxiliar para invocar o processador Python dentro do venv
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PY_BIN="$ROOT_DIR/.venv/bin/python3"
if [[ ! -x "$PY_BIN" ]]; then
    PY_BIN="python3"
fi

exec "$PY_BIN" "$SCRIPT_DIR/process_results.py" "$@"

