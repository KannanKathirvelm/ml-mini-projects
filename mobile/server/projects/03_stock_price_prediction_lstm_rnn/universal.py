"""The pooled "India universal" model: shared, torch-free helpers.

Why one model can serve every stock: the inputs are scale-free. Each window is the last
`window` log prices relative to the latest day, and the target is tomorrow's log return.
Dividing both by the stock's own daily volatility (`stock_scale`) makes a quiet large-cap and
a jumpy small-cap look alike, so one RNN and one LSTM trained on ~50 liquid NSE stocks pooled
together can be applied to ANY stock with at least `window + 1` days of history.

Splits use the same calendar cut-offs for every stock (validation = the year before the test
year, test = the last year), so no stock's test period overlaps another stock's training
period (market-wide moves would otherwise leak across stocks).

This module only needs numpy and pandas. Predictions come from a `predict_fn` that maps a
float32 array (batch, window, 1) to scaled log returns (batch,): a torch model
(`train_universal.torch_predict_fn`) or ONNX Runtime (`onnx_model.OnnxPredictor`), so the slim
server never imports torch.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
MODEL_DIR = ROOT / "models"
UNIVERSE_FILE = ROOT / "india_universe.txt"
META_FILE = MODEL_DIR / "universal_meta.json"
WINDOW = 60
SCALE_LOOKBACK = 750   # daily returns used for a stock's volatility scale (~3 years)
MIN_SCALE_DAYS = 40
BACKTEST_DAYS = 120    # live back-test length shown for a stock in the app / API

PredictFn = Callable[[np.ndarray], np.ndarray]


# ------------------------------------------------------------------ universe
def read_universe(path: Path = UNIVERSE_FILE) -> tuple[list[str], list[str]]:
    """(training symbols, held-out symbols). Lines after `[holdout]` are never trained on."""
    train, holdout, cur = [], [], None
    cur = train
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.lower() == "[holdout]":
            cur = holdout
            continue
        sym = line.upper()
        cur.append(sym if sym.endswith((".NS", ".BO")) or sym.startswith("^") else f"{sym}.NS")
    return train, holdout


# ------------------------------------------------------------------ scaling + windows
def stock_scale(log_prices: np.ndarray) -> float:
    """Std of the stock's most recent daily log returns (up to SCALE_LOOKBACK of them)."""
    r = np.diff(np.asarray(log_prices, dtype=float))[-SCALE_LOOKBACK:]
    if len(r) < MIN_SCALE_DAYS:
        raise ValueError(f"need at least {MIN_SCALE_DAYS + 1} days of prices, got {len(r) + 1}")
    s = float(np.std(r))
    return max(s, 1e-4)


def windows(log_prices: np.ndarray, window: int = WINDOW):
    """All (X_raw, y_raw, target_idx) for one stock; X_raw[i] = logp[i:i+window] - logp[i+window-1]."""
    W = np.lib.stride_tricks.sliding_window_view(log_prices[:-1], window)
    last = W[:, -1]
    return W - last[:, None], log_prices[window:] - last, np.arange(window, len(log_prices))


def split_dates(last_date: pd.Timestamp, test_days: int = 365, val_days: int = 365):
    test_start = last_date - pd.Timedelta(days=test_days)
    return test_start - pd.Timedelta(days=val_days), test_start


def stock_windows(prices: pd.Series, val_start, test_start, window: int = WINDOW, scale=None):
    """Scaled windows of one stock split by calendar date.

    scale: the stock's volatility from returns before `val_start` (training stocks), or a
    given value (held-out stocks use returns before `test_start`).
    """
    prices = prices.dropna()
    prices = prices[prices > 0]
    logp = np.log(prices.values.astype(float))
    if scale is None:
        scale = stock_scale(logp[prices.index < val_start])
    X_raw, y_raw, tidx = windows(logp, window)
    tdates = prices.index[tidx]
    X = (X_raw / scale)[..., None].astype(np.float32)
    y = (y_raw / scale).astype(np.float32)
    prev = prices.values[tidx - 1]
    actual = prices.values[tidx]
    parts = {"train": tdates < val_start,
             "val": (tdates >= val_start) & (tdates < test_start),
             "test": tdates >= test_start}
    return {k: (X[m], y[m], tdates[m], prev[m], actual[m]) for k, m in parts.items()}, scale


# ------------------------------------------------------------------ metrics
def metrics(actual, pred, prev) -> dict:
    """Price-space errors plus direction accuracy (same definition as train.metrics)."""
    actual, pred, prev = (np.asarray(a, dtype=float) for a in (actual, pred, prev))
    err = pred - actual
    moved = pred != prev
    return {
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "mae": float(np.mean(np.abs(err))),
        "mape_pct": float(np.mean(np.abs(err / actual)) * 100),
        "direction_acc_pct": (float(np.mean(np.sign(pred - prev) == np.sign(actual - prev)) * 100)
                              if moved.any() else None),
    }


def pooled_metrics(rows: list[dict]) -> dict:
    """Scale-free summary over many stocks.

    rows: per stock {"actual", "prev", "<model>": preds}. Price RMSE can't be pooled across
    stocks priced at ₹50 and ₹50,000, so we report: MAPE (pooled), RMSE of daily returns in %
    (pooled), direction accuracy (pooled), the mean per-stock RMSE ratio model/naive (< 1 means
    better than naive) and how many stocks beat naive on RMSE.
    """
    out = {}
    models = [k for k in rows[0] if k not in ("actual", "prev", "symbol")]
    a = np.concatenate([r["actual"] for r in rows])
    p0 = np.concatenate([r["prev"] for r in rows])
    true_ret = a / p0 - 1
    out["n_stocks"], out["n_days"] = len(rows), int(len(a))
    out["up_days_pct"] = float(np.mean(true_ret > 0) * 100)
    for m in ["naive_baseline", *models]:
        pred = p0 if m == "naive_baseline" else np.concatenate([r[m] for r in rows])
        ratios = []
        for r in rows:
            pr = r["prev"] if m == "naive_baseline" else r[m]
            naive = np.sqrt(np.mean((r["prev"] - r["actual"]) ** 2))
            ratios.append(np.sqrt(np.mean((pr - r["actual"]) ** 2)) / naive if naive > 0 else 1.0)
        moved = pred != p0
        out[m] = {
            "mape_pct": float(np.mean(np.abs(pred / a - 1)) * 100),
            "rmse_return_pct": float(np.sqrt(np.mean((pred / p0 - 1 - true_ret) ** 2)) * 100),
            "direction_acc_pct": (float(np.mean(np.sign(pred - p0) == np.sign(a - p0)) * 100)
                                  if moved.any() else None),
            "mean_rmse_ratio_vs_naive": float(np.mean(ratios)),
            "stocks_beating_naive_rmse": int(np.sum(np.array(ratios) < 1.0)),
        }
    return out


# ------------------------------------------------------------------ inference
def predict_prices(predict_fn: PredictFn, X: np.ndarray, prev: np.ndarray, scale: float) -> np.ndarray:
    if len(X) == 0:
        return np.zeros(0)
    return prev * np.exp(np.asarray(predict_fn(X), dtype=float) * scale)


def forecast(predict_fn: PredictFn, prices, steps: int, scale: float, window: int = WINDOW) -> list[float]:
    """Recursive multi-day forecast (same as model.forecast, but for any predict_fn)."""
    logp = list(np.log(np.asarray(prices, dtype=float))[-window:])
    out = []
    for _ in range(steps):
        x = ((np.array(logp[-window:]) - logp[-1]) / scale).astype(np.float32).reshape(1, -1, 1)
        logp.append(logp[-1] + float(np.asarray(predict_fn(x)).reshape(-1)[0]) * scale)
        out.append(float(np.exp(logp[-1])))
    return out


def backtest(predict_fns: dict[str, PredictFn], prices: pd.Series, days: int = BACKTEST_DAYS,
             window: int = WINDOW) -> dict:
    """Walk-forward check on a stock's last `days` sessions.

    The scale uses only returns before the back-test period, so it is out of sample.
    (For a stock in the training universe the most recent ~12 months were never trained on
    either, because they are the test period.)
    """
    prices = prices.dropna()
    logp = np.log(prices.values.astype(float))
    n = len(logp)
    days = int(min(days, n - window - 1 - MIN_SCALE_DAYS))
    if days < 5:
        raise ValueError(f"need at least {window + MIN_SCALE_DAYS + 6} days of prices, got {n}")
    scale = stock_scale(logp[: n - days])
    X_raw, _, tidx = windows(logp, window)
    X_raw, tidx = X_raw[-days:], tidx[-days:]
    X = (X_raw / scale)[..., None].astype(np.float32)
    prev, actual = prices.values[tidx - 1], prices.values[tidx]
    preds = {name: predict_prices(fn, X, prev, scale) for name, fn in predict_fns.items()}
    results = {"naive_baseline": metrics(actual, prev, prev)}
    results.update({name: metrics(actual, p, prev) for name, p in preds.items()})
    return {"dates": [str(d.date()) for d in prices.index[tidx]], "actual": actual.tolist(),
            "predictions": {k: v.tolist() for k, v in preds.items()}, "results": results,
            "scale": scale}


def load_meta(path: Path = META_FILE) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def info(meta: dict | None) -> dict | None:
    """Short description of the universal model for the app and the API."""
    if not meta:
        return None
    return {
        "kind": "universal", "trained_on": len(meta.get("train_symbols", [])),
        "held_out_stocks": meta.get("holdout_symbols", []),
        "trained_until": meta.get("val_start"), "data_until": meta.get("last_date"),
        "trained_at": meta.get("trained_at"),
        "note": ("One RNN and one LSTM trained on ~50 liquid NSE stocks pooled together. Inputs "
                 "are scale-free (log prices relative to the last day, divided by the stock's own "
                 "volatility), so the same model forecasts any stock. On unseen data it is about "
                 "as accurate as the naive 'tomorrow = today' guess."),
    }
