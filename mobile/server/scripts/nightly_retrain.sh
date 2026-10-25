#!/usr/bin/env bash
# Nightly retrain of the pooled "India universal" RNN + LSTM (see mobile/server/CI.md).
#
#   bash mobile/server/scripts/nightly_retrain.sh        # from anywhere; fresh Ubuntu + Python 3.12
#
# 1. venv with CPU torch + onnx tooling   2. refresh the NSE equity list (best effort)
# 3. retrain on the latest prices into a staging folder   4. export ONNX + parity check
# 5. metric sanity check vs the naive baseline   6. only then copy the models into place
# Exits non-zero on any failure; the committed models are left untouched in that case.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
P03="03_stock_price_prediction_lstm_rnn"
P04="04_financial_ai_agents"
VENV="$ROOT/.venv-retrain"
EPOCHS="${RETRAIN_EPOCHS:-25}"
START="${RETRAIN_START:-2015-01-01}"
LIMIT_ARGS=()
[ -n "${RETRAIN_LIMIT:-}" ] && LIMIT_ARGS=(--limit "$RETRAIN_LIMIT")   # quick test runs only
PY="${PYTHON:-python3.12}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
t0=$(date +%s)
step() { echo; echo "=== [$(( $(date +%s) - t0 ))s] $*"; }

step "Python environment ($("$PY" --version))"
if [ "${KEEP_VENV:-}" != "1" ] || [ ! -x "$VENV/bin/python" ]; then
  rm -rf "$VENV"
  "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install --no-cache-dir -q --upgrade pip
  "$VENV/bin/pip" install --no-cache-dir -q torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
  "$VENV/bin/pip" install --no-cache-dir -q -r mobile/server/requirements-retrain.txt
fi
VPY="$VENV/bin/python"
"$VPY" -c "import torch, onnxruntime, yfinance; print('torch', torch.__version__, '| onnxruntime', onnxruntime.__version__, '| yfinance', yfinance.__version__)"

step "Refresh the NSE equity list"
if [ "${SKIP_NSE_REFRESH:-}" = "1" ]; then
  echo "skipped (SKIP_NSE_REFRESH=1)"
else
  # NSE sometimes blocks cloud IPs; india.py keeps the bundled snapshot in that case.
  (cd "$P04" && "$VPY" india.py --refresh) || echo "NSE refresh failed; keeping the bundled snapshot"
  cp "$P04/data/nse_equities.csv" "$P03/data/nse_equities.csv"
  [ -f "$P04/data/nse_equities_meta.json" ] && cp "$P04/data/nse_equities_meta.json" "$P03/data/"
fi
"$VPY" -c "import csv,sys; n=sum(1 for _ in csv.DictReader(open('$P03/data/nse_equities.csv'))); print(n, 'NSE equities'); sys.exit(n < 1000)"

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/universal-XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

step "Train universal RNN + LSTM (latest prices, max $EPOCHS epochs) -> $STAGE"
(cd "$P03" && "$VPY" -u train_universal.py --refresh --epochs "$EPOCHS" --start "$START" --out "$STAGE" ${LIMIT_ARGS[@]+"${LIMIT_ARGS[@]}"})

step "Export to ONNX + parity on random windows"
(cd "$P03" && "$VPY" export_onnx.py --dir "$STAGE" --only universal)

step "Sanity checks (metrics vs naive, ONNX vs torch on real prices)"
"$VPY" mobile/server/scripts/check_universal.py "$STAGE"

if [ "${RETRAIN_DRY_RUN:-}" = "1" ]; then
  step "Dry run (RETRAIN_DRY_RUN=1): all checks passed, models NOT installed"
  exit 0
fi

step "Install the new models"
for f in universal_rnn.pt universal_lstm.pt universal_rnn.onnx universal_lstm.onnx universal_meta.json; do
  cp "$STAGE/$f" "$P03/models/$f"
done
"$VPY" mobile/server/scripts/prepare.py
ls -la "$P03/models"/universal_* "mobile/server/projects/$P03/models"/universal_*

step "Done in $(( $(date +%s) - t0 ))s"
git status --short -- "$P03/models" "$P03/data" "$P04/data" "mobile/server/projects" || true
