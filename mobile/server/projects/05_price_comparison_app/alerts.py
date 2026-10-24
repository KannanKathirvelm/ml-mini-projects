"""Re-check tracked products and report which have hit their target price.

Shared by check_alerts.py (cron-friendly CLI) and the Streamlit alerts tab.
"""
from __future__ import annotations

from dataclasses import dataclass

import db
from matching import same_product
from search import search_all


@dataclass
class AlertResult:
    title: str
    target: float
    best: float | None
    store: str | None
    hit: bool
    note: str = ""


def check_alerts(conn=None, stores=None) -> list[AlertResult]:
    conn = conn or db.connect()
    results = []
    cache: dict[str, object] = {}
    for row in db.tracked(conn):
        res = cache.get(row["query"]) or search_all(row["query"], stores)
        if row["query"] not in cache:
            db.save_offers(conn, res.offers, row["query"])  # re-checks extend history
            cache[row["query"]] = res
        group = next((g for g in res.groups if row["product_key"] in g.keys), None) \
            or next((g for g in res.groups if same_product(g.title, row["title"])), None)
        if group is None:
            db.update_check(conn, row["id"], None, None)
            results.append(AlertResult(row["title"], row["target_price"], None, None,
                                       False, "not found in any store right now"))
            continue
        best = group.best
        db.update_check(conn, row["id"], best.total_inr, best.store)
        results.append(AlertResult(row["title"], row["target_price"], best.total_inr,
                                   best.store, best.total_inr <= row["target_price"]))
    return results
