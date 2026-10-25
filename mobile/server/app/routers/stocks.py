"""Project 03: RNN vs LSTM stock forecasts (per-ticker models + the pooled India universal model).

Full profile: torch weights (*.pt), training at runtime. Slim profile: the same models exported
to ONNX (*.onnx) run with ONNX Runtime; no training, `POST /train` returns the universal forecast.
The forecast maths (scale-free windows, recursive forecast, back-test) is the project's own
torch-free `universal.py`, so both profiles produce the same numbers (parity tested to ~1e-5).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from .. import loader
from ..settings import SLIM

router = APIRouter(prefix="/api/stocks", tags=["stocks"])
log = logging.getLogger("server.stocks")

TICKER_RE = re.compile(r"^[A-Za-z0-9.^=&\-]{1,24}$")
CELLS = ["rnn", "lstm"]
PRICE_MEMO_S = 120  # in-memory reuse of a loaded price series; disk freshness is data.is_stale

_train_lock = threading.Lock()
_cache_lock = threading.Lock()
_predictors: dict[str, tuple[float, dict]] = {}       # model name -> (file mtime, {cell: fn})
_prices: dict[str, tuple[float, pd.Series, float]] = {}  # ticker -> (loaded at, prices, file mtime)
_backtests: dict[tuple, dict] = {}                     # (ticker, last date, model mtime) -> result


def ns():
    mods = ["data", "universal", "india"] + (["onnx_model"] if SLIM else ["train", "model", "predict"])
    return loader.get("stocks", mods)


def model_dir():
    return ns().universal.MODEL_DIR


def safe_name(t: str) -> str:
    return t.replace("^", "_")


def normalize(raw: str) -> str:
    """Free text -> Yahoo symbol, India first ('reliance' -> RELIANCE.NS); 400 if invalid."""
    if not raw or len(raw) > 60:
        raise HTTPException(400, f"'{raw}' is not a valid ticker symbol.")
    try:
        t = ns().india.normalize_ticker(raw)
    except ValueError:
        raise HTTPException(400, f"'{raw}' is not a valid ticker symbol.") from None
    if not TICKER_RE.match(t):
        raise HTTPException(400, f"'{raw}' is not a valid ticker symbol.")
    return t


def _weights(name: str, cell: str):
    return model_dir() / f"{name}_{cell}.{'onnx' if SLIM else 'pt'}"


def has_model(name: str) -> bool:
    return all(_weights(name, c).exists() for c in CELLS)


def trained() -> list[str]:
    out = []
    for p in sorted(model_dir().glob("*_meta.json")):
        if p.name == "universal_meta.json":
            continue
        try:
            t = json.loads(p.read_text())["ticker"]
        except (OSError, ValueError, KeyError):
            continue
        if has_model(safe_name(t)):
            out.append(t)
    return sorted(out)


def _torch_fn(model):
    import torch

    model.eval()

    @torch.no_grad()
    def fn(X):
        return model(torch.from_numpy(np.ascontiguousarray(X, dtype=np.float32))).numpy()
    return fn


def predictors(name: str) -> dict:
    """{'rnn': fn, 'lstm': fn} for model `name` ('universal' or a safe ticker), cached by mtime."""
    files = [_weights(name, c) for c in CELLS]
    if not all(f.exists() for f in files):
        raise FileNotFoundError(name)
    mtime = max(f.stat().st_mtime for f in files)
    with _cache_lock:
        hit = _predictors.get(name)
        if hit and hit[0] == mtime:
            return hit[1]
    if SLIM:
        fns = {c: ns().onnx_model.OnnxPredictor(f) for c, f in zip(CELLS, files)}
    else:
        import torch

        fns = {}
        for c, f in zip(CELLS, files):
            m = ns().model.PriceRNN(c)
            m.load_state_dict(torch.load(f, weights_only=True))
            fns[c] = _torch_fn(m)
    with _cache_lock:
        _predictors[name] = (mtime, fns)
    return fns


def universal_meta() -> dict | None:
    return ns().universal.load_meta(model_dir() / "universal_meta.json")


def _load_prices(t: str) -> tuple[pd.Series, float]:
    """(closes, cache file mtime). Market-hours-aware refresh of the project's CSV cache."""
    with _cache_lock:
        hit = _prices.get(t)
    if hit and time.time() - hit[0] < PRICE_MEMO_S:
        return hit[1], hit[2]
    data = ns().data
    cache = data.cache_path(t)
    try:
        prices = data.load_prices(t, refresh="auto")
    except ValueError as exc:
        raise HTTPException(404, ns().india.no_data_message(t)) from exc
    except Exception as exc:  # network trouble: fall back to whatever is cached
        if not cache.exists():
            raise HTTPException(502, f"Could not load prices for {t}: {exc}") from exc
        prices = data.load_prices(t, refresh=False)
    prices = prices[prices > 0]
    mtime = cache.stat().st_mtime if cache.exists() else time.time()
    with _cache_lock:
        _prices[t] = (time.time(), prices, mtime)
    return prices, mtime


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and x != x) else round(float(x), n)


def currency_of(t: str) -> str | None:
    if ns().india.is_indian(t):
        return "INR"
    return "USD" if "." not in t and not t.startswith("^") and "=" not in t else None


def choose_model(t: str, pref: str) -> str:
    per = (model_dir() / f"{safe_name(t)}_meta.json").exists() and has_model(safe_name(t))
    uni = has_model("universal") and universal_meta() is not None
    if pref == "per_ticker":
        if not per:
            raise HTTPException(404, f"No per-ticker model for {t}. Use model=universal"
                                     + ("" if SLIM else f" or train one with POST /api/stocks/{t}/train") + ".")
        return "per_ticker"
    if pref == "universal" or not per:
        if not uni:
            raise HTTPException(503, "The universal stock model is not available on this server.")
        return "universal"
    return "per_ticker"


def forecast_body(t: str, days: int, pref: str = "auto") -> dict:
    kind = choose_model(t, pref)
    U, india = ns().universal, ns().india
    prices, fetched = _load_prices(t)
    if kind == "per_ticker":
        meta = json.loads((model_dir() / f"{safe_name(t)}_meta.json").read_text())
        fns = predictors(safe_name(t))
        window, scale = meta["window"], meta["scale"]
        metrics, preds = meta["results"], meta["predictions"]
        test = {"dates": meta["test_dates"], "actual": preds["actual"], "rnn": preds["rnn"],
                "lstm": preds["lstm"]}
        info = {"kind": "per_ticker", "trained_on": 1, "trained_until": meta.get("last_date"),
                "note": f"RNN and LSTM trained on {t} only; metrics are its own held-out test period."}
    else:
        meta = universal_meta()
        fns = predictors("universal")
        window = meta["window"]
        if len(prices) < window + U.MIN_SCALE_DAYS + 6:
            raise HTTPException(404, f"{t} has only {len(prices)} trading days of prices; the "
                                     f"forecast needs at least {window + U.MIN_SCALE_DAYS + 6}.")
        scale = U.stock_scale(np.log(prices.values))
        key = (t, str(prices.index[-1]), len(prices), _predictors["universal"][0])
        bt = _backtests.get(key)
        if bt is None:
            bt = U.backtest(fns, prices, window=window)
            with _cache_lock:
                if len(_backtests) > 500:
                    _backtests.clear()
                _backtests[key] = bt
        metrics = bt["results"]
        test = {"dates": bt["dates"], "actual": bt["actual"], **bt["predictions"]}
        info = U.info(meta)
    dates = pd.bdate_range(prices.index[-1] + pd.Timedelta(days=1), periods=days)
    fc = {cell: U.forecast(fn, prices.values, days, scale, window) for cell, fn in fns.items()}
    hist = prices.iloc[-90:]
    cur = currency_of(t)
    last = float(prices.iloc[-1])
    as_of = india.data_as_of(t, prices.index[-1].date(), fetched)
    return {
        "ticker": t,
        "normalized_ticker": t,
        "name": india.stock_name(t),
        "currency": cur,
        "last_close": _r(last),
        "last_date": str(prices.index[-1].date()),
        "display": {"last_close": india.format_money(last, cur)},
        "as_of_ist": as_of["as_of_ist"],
        "market_open": as_of["market_open"],
        "model": kind,
        "model_info": info,
        "history": [{"date": str(d.date()), "close": _r(v)} for d, v in hist.items()],
        "forecast": [{"date": str(d.date()), "rnn": _r(fc["rnn"][i]), "lstm": _r(fc["lstm"][i])}
                     for i, d in enumerate(dates)],
        "metrics": {name: {k: _r(v, 3) for k, v in m.items()} for name, m in metrics.items()},
        "test": {k: (v if k == "dates" else [_r(x) for x in v]) for k, v in test.items()},
    }


@router.get("/tickers")
def tickers():
    meta = universal_meta() if has_model("universal") else None
    return {"trained": trained(), "universal": meta is not None,
            "universal_info": ns().universal.info(meta)}


@router.get("/{ticker}/forecast")
def forecast(ticker: str, days: int = Query(10, ge=1, le=30),
             model: str = Query("auto", pattern="^(auto|universal|per_ticker)$")):
    return forecast_body(normalize(ticker), days, model)


@router.post("/{ticker}/train")
def train(ticker: str):
    t = normalize(ticker)
    if SLIM:  # no training on the 512 MB free tier: serve the pooled model instead
        return {**forecast_body(t, 10, "universal"), "trained": False}
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
    return {**forecast_body(t, 10, "per_ticker"), "trained": True}
