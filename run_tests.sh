#!/usr/bin/env bash
set -euo pipefail
ROOT="$(dirname "$(realpath "$0")")"
"$ROOT/.venv/bin/python" -m pytest "$ROOT/backend/tests" -q
"$ROOT/.venv/bin/ruff" check "$ROOT/backend" "$ROOT/scripts"
npm --prefix "$ROOT/frontend" run lint
npm --prefix "$ROOT/frontend" run build
