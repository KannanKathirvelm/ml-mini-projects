"""Backfill ~30 days of price history so charts aren't empty on day one.

Only the simulated stores can be backfilled honestly: their prices are a
pure function of the date, so "what did ShopKart charge 12 days ago" has a
real answer. The demo APIs return static prices and have no past data, so
they only gain history from real searches.
"""
from __future__ import annotations

from datetime import date, timedelta

import db
from stores import simulated_stores


def seed_history(days: int = 30, conn=None) -> int:
    conn = conn or db.connect()
    conn.execute("DELETE FROM offers WHERE query = '__seed__'")  # idempotent re-seed
    rows = 0
    today = date.today()
    for store in simulated_stores():
        items = [i for i in store.catalog if store.carries(i["sku"])]
        for back in range(days, 0, -1):
            day = today - timedelta(days=back)
            offers = [store.offer_for(i, day) for i in items]
            db.save_offers(conn, offers, "__seed__", seen_at=f"{day.isoformat()}T09:00:00")
            rows += len(offers)
    return rows
