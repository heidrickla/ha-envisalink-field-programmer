#!/bin/bash
# The four gates, one per call, run on Linux or WSL from any directory.
# Usage: tools/gates.sh tests|mypy|ruff|validate
# PYTHON names the interpreter with the test harness installed (default: python3).
set -euo pipefail
cd "$(dirname "$0")/.."
py="${PYTHON:-python3}"
case "${1:-}" in
  tests) PYTHONDONTWRITEBYTECODE=1 "$py" -m pytest tests -q -p no:cacheprovider ;;
  mypy) "$py" -m mypy custom_components/envisalink_field_programmer ;;
  ruff) "$py" -m ruff check . && "$py" -m ruff format --check . ;;
  validate) "$py" tools/validate_local.py ;;
  *) echo "usage: tools/gates.sh tests|mypy|ruff|validate" >&2; exit 2 ;;
esac
