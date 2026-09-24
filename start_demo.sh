#!/usr/bin/env bash
set -euo pipefail
ROOT="$(dirname "$(realpath "$0")")"
exec python3 "$ROOT/scripts/start.py"
