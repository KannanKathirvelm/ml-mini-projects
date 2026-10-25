"""Project 04: multi-agent market-insight report."""
from __future__ import annotations

import math
import re
import threading
import time

from fastapi import APIRouter, HTTPException

from .. import loader
from ..settings import FINANCE_CACHE_SECONDS

router = APIRouter(prefix="/api/finance", tags=["finance"])
TICKER_RE = re.compile(r"^[A-Za-z0-9.^=&\-]{1,24}$")
SENTIMENT = {1: "positive", 0: "neutral", -1: "negative"}

_cache: dict[str, tuple[float, dict]] = {}
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def ns():
    return loader.get("finance", ["llm", "indicators", "data_tools", "agents", "pipeline"])


def _f(x, n=4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), n)


def build_report(ticker: str) -> dict:
    m = ns()
    try:
        a = m.pipeline.run_analysis(ticker)
    except m.data_tools.TickerNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    r, ind, prof = a.report, a.data["indicators"], a.data["fundamentals"]["profile"]
    stats = a.data["fundamentals"]["stats"]
    use_llm = a.mode.startswith("LLM")
    cur = prof.get("currency")
    bench = a.data.get("benchmark")
    chart = m.indicators.add_indicator_columns(a.history).iloc[-250:]
    return {
        "ticker": a.ticker,
        "company": prof.get("longName") or prof.get("shortName") or a.ticker,
        "mode": "llm" if use_llm else "offline",
        "mode_label": a.mode,
        "currency": prof.get("currency"),
        "last_close": _f(ind["last_close"], 2),
        "last_date": ind["last_date"],
        "outlook": r.get("outlook", "neutral"),
        "confidence": r.get("confidence", "low"),
        "summary": r.get("summary", ""),
        "bullish": list(r.get("bullish_points", [])),
        "bearish": list(r.get("bearish_points", [])),
        "risks": list(r.get("key_risks", [])),
        "overall": r.get("outlook_rationale", ""),
        "agents": [{"name": f.agent, "stance": f.stance, "summary": f.summary,
                    "points": [*f.bullish_points, *f.bearish_points]} for f in a.findings],
        "headlines": [{"title": n["title"], "publisher": n.get("publisher") or None,
                       "link": n.get("link") or None,
                       "sentiment": SENTIMENT[m.agents.headline_sentiment(n["title"])]}
                      for n in a.data["news"]],
        "indicators": {"rsi": _f(ind.get("rsi14"), 1), "volatility_1y": _f(ind.get("volatility_1y")),
                       "return_1m": _f(ind.get("return_1m")),
                       "max_drawdown_1y": _f(ind.get("max_drawdown_1y"))},
        "chart": [{"date": d.strftime("%Y-%m-%d"), "close": _f(row["Close"], 2),
                   "sma20": _f(row["SMA20"], 2), "sma50": _f(row["SMA50"], 2),
                   "sma200": _f(row["SMA200"], 2)} for d, row in chart.iterrows()],
        "markdown": m.pipeline.to_markdown(a),
        # India-first additions (API.md section 9)
        "normalized_ticker": a.ticker,
        "sector": prof.get("sector"),
        "industry": prof.get("industry"),
        "market_cap_display": (m.india.format_money(stats["marketCap"], cur, compact=True)
                               if stats.get("marketCap") else None),
        "as_of_ist": a.data["as_of"]["as_of_ist"],
        "display": {"last_close": m.india.format_money(ind["last_close"], cur)},
        "benchmark": None if not bench else {
            "symbol": bench["symbol"], "name": bench["name"],
            **{f"{w}_return_{p}": _f(bench.get(f"{w}_return_{p}"))
               for p in ("1m", "3m", "1y") for w in ("stock", "index")},
            "beta": _f(bench.get("beta"), 3),
            "relative_strength_1y": _f(bench.get("relative_strength_1y")),
        },
    }


@router.get("/{ticker}/report")
def report(ticker: str):
    try:
        t = ns().india.normalize_ticker(ticker[:60])
    except ValueError:
        t = ""
    if not TICKER_RE.match(t):
        raise HTTPException(404, f"No price data found for '{ticker}'.")
    with _guard:
        lock = _locks.setdefault(t, threading.Lock())
    with lock:  # concurrent requests for the same ticker share one analysis
        hit = _cache.get(t)
        if hit and time.time() - hit[0] < FINANCE_CACHE_SECONDS:
            return hit[1]
        body = build_report(t)
        _cache[t] = (time.time(), body)
        return body
