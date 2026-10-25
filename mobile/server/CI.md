# CI: nightly retrain of the India universal stock models

One script does everything. Run it from the **repo root** on a fresh Ubuntu runner with
Python 3.12 (e.g. `actions/setup-python@v5` with `python-version: "3.12"`):

```bash
bash mobile/server/scripts/nightly_retrain.sh
```

It exits non-zero if anything is broken (download, training, ONNX export, parity or metric
checks), so a red run means the committed models were **not** replaced by bad ones (the new
files are written to a staging folder and only moved into place after every check passes).

## What it does

1. Creates `.venv-retrain/` in the repo root (gitignored) and installs CPU-only
   torch from the PyTorch wheel index plus `onnx`, `onnxruntime`, `onnxscript`, `yfinance`,
   `pandas`, `numpy` (pinned in `mobile/server/requirements-retrain.txt`).
2. Refreshes the official NSE equity list (`python 04_financial_ai_agents/india.py --refresh`).
   If NSE blocks the runner (it sometimes does), the bundled snapshot is kept and the run continues.
3. Retrains the pooled universal RNN + LSTM on the latest daily prices of the stocks in
   `03_stock_price_prediction_lstm_rnn/india_universe.txt`
   (`python train_universal.py --refresh --out <staging>`), with a chronological split per stock
   and 8 held-out stocks that are never trained on (same calendar cut-offs for every stock:
   test = the last 12 months, validation = the 12 months before).
4. Exports both to ONNX (`python export_onnx.py`), then checks:
   - ONNX vs torch parity: random windows and real windows (max abs diff < 1e-4 on the scaled
     output) and 10-day recursive forecasts + 120-day back-tests on real prices (< 1e-5 relative),
   - metrics vs the naive "tomorrow = today" baseline on held-out time and held-out stocks:
     RMSE must be within 5% of naive and MAPE finite (the model is expected to be about equal to
     naive; this catches a broken model, not a "bad" market).
5. Copies the result into the server's project copy (`python mobile/server/scripts/prepare.py`).

## Inputs (all optional environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `PYTHON` | `python3.12` (falls back to `python3`) | Interpreter used to create the venv |
| `RETRAIN_EPOCHS` | `25` | Max epochs (early stopping on validation loss usually stops sooner) |
| `RETRAIN_START` | `2015-01-01` | First day of price history |
| `SKIP_NSE_REFRESH` | unset | `1` skips step 2 |
| `KEEP_VENV` | unset | `1` reuses an existing `.venv-retrain/` |
| `RETRAIN_DRY_RUN` | unset | `1` runs every step and check but does not install the new models |
| `RETRAIN_LIMIT` | unset | Train on only the first N stocks (quick test of the pipeline; use with `CHECK_MIN_TRAIN_STOCKS`) |
| `CHECK_MIN_TRAIN_STOCKS` | `30` | Minimum training stocks the sanity check accepts |

No secrets are needed (Yahoo Finance and the NSE list are public).

## Outputs: files that change (commit these)

```
03_stock_price_prediction_lstm_rnn/models/universal_rnn.pt
03_stock_price_prediction_lstm_rnn/models/universal_lstm.pt
03_stock_price_prediction_lstm_rnn/models/universal_rnn.onnx
03_stock_price_prediction_lstm_rnn/models/universal_lstm.onnx
03_stock_price_prediction_lstm_rnn/models/universal_meta.json
mobile/server/projects/03_stock_price_prediction_lstm_rnn/models/universal_*   (same 5 files)
04_financial_ai_agents/data/nse_equities.csv            (only if the NSE refresh succeeded)
04_financial_ai_agents/data/nse_equities_meta.json      (only if the NSE refresh succeeded)
03_stock_price_prediction_lstm_rnn/data/nse_equities.csv   + mobile/server/projects/0[34]_*/data/nse_equities*.{csv,json}
```

Suggested commit step: `git add -A 03_stock_price_prediction_lstm_rnn/models 03_stock_price_prediction_lstm_rnn/data/nse_equities* 04_financial_ai_agents/data mobile/server/projects/03_stock_price_prediction_lstm_rnn/models mobile/server/projects/0*/data/nse_equities*`
then commit only if `git diff --cached --quiet` is false. Each file is well under 1 MB,
so no LFS is needed. A push to `main` lets Render redeploy with the new models (if auto-deploy is on).

Do **not** add price CSV caches (`03_…/data/<TICKER>.csv` are gitignored); the run downloads
about 55 tickers from Yahoo each time.

## Runtime

Measured locally (Apple M-series CPU, 2026-10-25): training 505 s for 50 + 8 stocks
(116,612 training windows; RNN 10 epochs x ~10 s, LSTM 11 epochs x ~34 s, early stopping),
peak RSS ~1 GB. A quick pipeline test (`RETRAIN_LIMIT=5 RETRAIN_EPOCHS=2 CHECK_MIN_TRAIN_STOCKS=2
RETRAIN_DRY_RUN=1`) takes ~20 s after the venv exists.

On a GitHub-hosted `ubuntu-latest` runner (4 vCPU, 16 GB) expect roughly 15–30 minutes:
~2–3 min installing CPU torch and deps, ~1 min downloading prices, 10–25 min training.
Set `timeout-minutes: 60`.

Suggested schedule: `cron: "30 14 * * 1-5"` (20:00 IST, after the NSE close, Monday to Friday).
