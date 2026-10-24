#!/usr/bin/env bash
# Copy the needed files from projects 01-07 into ./projects (safe to re-run),
# then (re)build the models that are not shipped as files.
#   ./prepare.sh              copy only
#   ./prepare.sh --models     copy + retrain sklearn models + pre-train stock models
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
"$PY" scripts/prepare.py
if [ "${1:-}" = "--models" ]; then
  "$PY" scripts/build_models.py --sklearn --stocks MSFT,RELIANCE.NS,TCS.NS
fi
