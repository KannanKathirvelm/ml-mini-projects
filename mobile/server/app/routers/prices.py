"""Project 05: price comparison, history, tracking and alerts (SQLite)."""
from __future__ import annotations

import logging
from contextlib import closing
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import loader
from ..settings import PRICES_DB_PATH

router = APIRouter(prefix="/api/prices", tags=["prices"])
log = logging.getLogger("server.prices")


def _patch_config(mods):
    """Point the project's DB at a writable path before db.py reads config."""
    cfg = mods["config"]
    PRICES_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.DATA_DIR = PRICES_DB_PATH.parent
    cfg.DB_PATH = PRICES_DB_PATH


def ns():
    return loader.get("prices", ["config", "matching", "stores", "db", "search", "history",
                                 "alerts"], before=_patch_config)


def conn():
    return closing(ns().db.connect(PRICES_DB_PATH))


def seed_if_empty() -> int:
    with conn() as c:
        if c.execute("SELECT COUNT(*) FROM offers").fetchone()[0]:
            return 0
        n = ns().history.seed_history(30, c)
        log.info("seeded %d simulated price-history rows into %s", n, PRICES_DB_PATH)
        return n


def _offer(o) -> dict:
    return {"store": o.store, "title": o.title, "price_inr": o.price_inr,
            "shipping_inr": o.shipping_inr, "total_inr": o.total_inr,
            "delivery_days": o.delivery_days, "rating": o.rating, "in_stock": bool(o.in_stock),
            "url": o.url or None, "image": getattr(o, "image", None)}


def _group(g) -> dict:
    offers = sorted(g.offers, key=lambda o: (o.total_inr, -(o.rating or 0)))
    in_stock = [o for o in offers if o.in_stock]
    return {"product": g.title, "store_count": len(g.stores),
            "best": _offer(in_stock[0]) if in_stock else None,
            "savings_inr": round(g.savings, 2),
            "offers": [_offer(o) for o in offers]}


@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=100)):
    q = q.strip()
    if not q:
        raise HTTPException(400, "Query must not be empty.")
    res = ns().search.search_all(q)
    with conn() as c:
        ns().db.save_offers(c, res.offers, q)  # every search extends price history
    return {"query": q, "stores_ok": res.stores_ok,
            "warnings": [f"{s} is unavailable right now and was skipped ({e})"
                         for s, e in res.errors.items()],
            "groups": [_group(g) for g in res.groups]}


def _keys_for(c, product: str) -> list[str]:
    """product_key of the name plus any stored title that matching.same_product accepts."""
    m = ns().matching
    keys = {m.product_key(product)}
    for row in c.execute("SELECT DISTINCT product_key, title FROM offers"):
        if row["product_key"] not in keys and m.same_product(row["title"], product):
            keys.add(row["product_key"])
    return sorted(keys)


@router.get("/history")
def history(product: str = Query(..., min_length=1), days: int = Query(30, ge=1, le=365)):
    since = (date.today() - timedelta(days=days)).isoformat()
    series: dict[str, list] = {}
    with conn() as c:
        for r in ns().db.history(c, _keys_for(c, product)):
            if r["day"] >= since:
                series.setdefault(r["store"], []).append(
                    {"date": r["day"], "price_inr": round(r["total_inr"], 2)})
    return {"product": product,
            "series": [{"store": s, "points": pts} for s, pts in sorted(series.items())]}


def _tracked_row(r) -> dict:
    best = r["last_best"]
    return {"product": r["title"], "target_inr": r["target_price"], "latest_best_inr": best,
            "latest_store": r["last_store"], "hit": best is not None and best <= r["target_price"]}


def _find_tracked(c, product: str):
    m = ns().matching
    key = m.product_key(product)
    rows = ns().db.tracked(c)
    return (next((r for r in rows if r["product_key"] == key), None)
            or next((r for r in rows if m.same_product(r["title"], product)), None))


@router.get("/tracked")
def tracked():
    with conn() as c:
        return [_tracked_row(r) for r in ns().db.tracked(c)]


class TrackBody(BaseModel):
    product: str = Field(min_length=1, max_length=200)
    target_inr: float = Field(gt=0)


@router.post("/track")
def track(body: TrackBody):
    m = ns()
    res = m.search.search_all(body.product)
    key = m.matching.product_key(body.product)
    group = (next((g for g in res.groups if key in g.keys), None)
             or next((g for g in res.groups if m.matching.same_product(g.title, body.product)), None))
    if group is None:
        raise HTTPException(404, f"'{body.product}' was not found in any store right now.")
    with conn() as c:
        m.db.save_offers(c, res.offers, body.product)
        m.db.track(c, group, body.product, body.target_inr)
        row = next(r for r in m.db.tracked(c) if r["product_key"] == m.matching.product_key(group.title))
        in_stock = [o for o in group.offers if o.in_stock]
        best = min(in_stock or group.offers, key=lambda o: o.total_inr)
        m.db.update_check(c, row["id"], best.total_inr, best.store)
        row = next(r for r in m.db.tracked(c) if r["id"] == row["id"])
        return _tracked_row(row)


@router.delete("/track")
def untrack(product: str = Query(..., min_length=1)):
    with conn() as c:
        row = _find_tracked(c, product)
        if row is None:
            return {"removed": False}
        ns().db.untrack(c, row["id"])
        return {"removed": True}


@router.post("/check-alerts")
def check_alerts():
    with conn() as c:
        return [{"product": r.title, "target_inr": r.target, "best_inr": r.best,
                 "store": r.store, "hit": bool(r.hit)} for r in ns().alerts.check_alerts(c)]
