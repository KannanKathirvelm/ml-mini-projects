"""Project 03: RNN vs LSTM stock forecasts."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from .. import loader

router = APIRouter(prefix="/api/stocks", tags=["stocks"])
log = logging.getLogger("server.stocks")

TICKER_RE = re.compile(r"^[A-Za-z0-9.^=\-]{1,20}$")
PRICE_MAX_AGE_S = float(os.environ.get("STOCK_PRICE_MAX_AGE_HOURS", "12")) * 3600

_train_lock = threading.Lock()
_cache_lock = threading.Lock()
_models: dict[str, tuple[float, dict, dict]] = {}   # ticker -> (meta mtime, meta, models)
_prices: dict[str, tuple[float, pd.Series]] = {}    # ticker -> (loaded at, prices)


def ns():
    return loader.get("stocks", ["train", "data", "model", "predict"])


def _norm(ticker: str) -> str:
    t = ticker.strip().upper()
    if not TICKER_RE.match(t):
        raise HTTPException(400, f"'{ticker}' is not a valid ticker symbol.")
    return t


def _meta_path(t: str):
    return ns().train.MODEL_DIR / f"{ns().train.safe_name(t)}_meta.json"


def trained() -> list[str]:
    out = []
    for p in sorted(ns().train.MODEL_DIR.glob("*_meta.json")):
        try:
            out.append(json.loads(p.read_text())["ticker"])
        except (OSError, ValueError, KeyError):
            continue
    return sorted(out)


def _load_models(t: str):
    path = _meta_path(t)
    if not path.exists():
        raise HTTPException(404, f"No trained model for {t} yet. Train it first with "
                                 f"POST /api/stocks/{t}/train.")
    mtime = path.stat().st_mtime
    with _cache_lock:
        hit = _models.get(t)
        if hit and hit[0] == mtime:
            return hit[1], hit[2]
    meta, models = ns().predict.load_models(t)
    with _cache_lock:
        _models[t] = (mtime, meta, models)
    return meta, models


def _load_prices(t: str) -> pd.Series:
    """Cached closes; refreshes the project's CSV cache when it is older than 12 h."""
    with _cache_lock:
        hit = _prices.get(t)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    data = ns().data
    cache = data.DATA_DIR / f"{t.replace('^', '_')}.csv"
    stale = not cache.exists() or time.time() - cache.stat().st_mtime > PRICE_MAX_AGE_S
    try:
        prices = data.load_prices(t, refresh=stale)
    except Exception as exc:  # network trouble: fall back to whatever is cached
        if not cache.exists():
            raise HTTPException(502, f"Could not load prices for {t}: {exc}") from exc
        prices = data.load_prices(t, refresh=False)
    with _cache_lock:
        _prices[t] = (time.time(), prices)
    return prices


def _r(x, n=2):
    return None if x is None else round(float(x), n)


def forecast_body(t: str, days: int) -> dict:
    meta, models = _load_models(t)
    prices = _load_prices(t)
    dates = pd.bdate_range(prices.index[-1] + pd.Timedelta(days=1), periods=days)
    fc = {cell: ns().model.forecast(m, prices.values, days, meta["scale"], meta["window"])
          for cell, m in models.items()}
    hist = prices.iloc[-90:]
    preds = meta["predictions"]
    return {
        "ticker": t,
        "last_close": _r(prices.iloc[-1]),
        "last_date": str(prices.index[-1].date()),
        "history": [{"date": str(d.date()), "close": _r(v)} for d, v in hist.items()],
        "forecast": [{"date": str(d.date()), "rnn": _r(fc["rnn"][i]), "lstm": _r(fc["lstm"][i])}
                     for i, d in enumerate(dates)],
        "metrics": {name: {k: _r(v, 3) for k, v in m.items()} for name, m in meta["results"].items()},
        "test": {
            "dates": meta["test_dates"],
            "actual": [_r(v) for v in preds["actual"]],
            "rnn": [_r(v) for v in preds["rnn"]],
            "lstm": [_r(v) for v in preds["lstm"]],
        },
    }


@router.get("/tickers")
def tickers():
    return {"trained": trained()}


@router.get("/{ticker}/forecast")
def forecast(ticker: str, days: int = Query(10, ge=1, le=30)):
    return forecast_body(_norm(ticker), days)


@router.post("/{ticker}/train")
def train(ticker: str):
    t = _norm(ticker)
    with _train_lock:  # one training run at a time; others wait
        t0 = time.perf_counter()
        try:
            ns().train.run(t, refresh=True, log=lambda *a: log.info(" ".join(map(str, a)).strip()))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (IndexError, KeyError) as exc:
            raise HTTPException(400, f"Not enough price history to train {t}.") from exc
        log.info("trained %s in %.1fs", t, time.perf_counter() - t0)
    with _cache_lock:
        _prices.pop(t, None)
    return forecast_body(t, 10)
