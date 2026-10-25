"""India market data: popular list, NSE search, market status, near-live quotes, intraday bars.

Thin wrapper over the projects' `india.py` (the copy in project 03, which needs no torch).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Query

from . import stocks

router = APIRouter(prefix="/api/india", tags=["india"])
MAX_QUOTES = 20


def india():
    return stocks.ns().india


@router.get("/popular")
def popular():
    m = india()
    return {"stocks": [dict(s) for s in m.POPULAR_STOCKS], "indices": [dict(i) for i in m.INDICES]}


@router.get("/market-status")
def market_status():
    return india().market_status()


@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=60), limit: int = Query(10, ge=1, le=50)):
    return {"query": q, "results": india().search_nse(q, limit)}


@router.get("/stocks")
def all_stocks(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    m = india()
    rows = sorted(m.nse_equities(), key=lambda r: r["symbol"])
    return {"total": len(rows), "offset": offset, "limit": limit,
            "snapshot_date": m.nse_snapshot_date(),
            "stocks": [m._result(r) for r in rows[offset:offset + limit]]}


def _quote(raw: str) -> dict:
    t = stocks.normalize(raw)
    try:
        return india().live_quote(t)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/quote/{ticker}")
def quote(ticker: str):
    return _quote(ticker)


@router.get("/quotes")
def quotes(symbols: str = Query(..., min_length=1)):
    syms = list(dict.fromkeys(s.strip() for s in symbols.split(",") if s.strip()))
    if not syms:
        raise HTTPException(400, "Give at least one symbol, e.g. symbols=RELIANCE,TCS.")
    if len(syms) > MAX_QUOTES:
        raise HTTPException(400, f"At most {MAX_QUOTES} symbols per request (got {len(syms)}).")

    def one(s):
        try:
            return _quote(s), None
        except HTTPException as exc:
            return None, {"symbol": s, "detail": exc.detail}
        except Exception as exc:  # Yahoo hiccup on one symbol must not fail the batch
            return None, {"symbol": s, "detail": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=min(6, len(syms))) as pool:
        results = list(pool.map(one, syms))
    return {"quotes": [q for q, _ in results if q], "errors": [e for _, e in results if e]}


@router.get("/intraday/{ticker}")
def intraday(ticker: str, interval: str = Query("1m")):
    if interval not in ("1m", "5m"):
        raise HTTPException(400, "interval must be 1m or 5m.")
    t = stocks.normalize(ticker)
    try:
        return india().intraday(t, interval)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
