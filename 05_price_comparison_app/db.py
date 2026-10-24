"""SQLite persistence: every search's offers (price history) and tracked products.

History rows are keyed by `product_key` (a normalised title), so one product
seen under slightly different titles at different stores still forms one
history: a group's chart simply selects all of its keys.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from config import DB_PATH, DATA_DIR
from matching import ProductGroup, product_key
from stores.base import Offer

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY,
    seen_at TEXT NOT NULL,
    query TEXT,
    product_key TEXT NOT NULL,
    store TEXT NOT NULL,
    title TEXT NOT NULL,
    price_inr REAL, shipping_inr REAL, total_inr REAL,
    delivery_days INTEGER, rating REAL, in_stock INTEGER, url TEXT, source TEXT
);
CREATE INDEX IF NOT EXISTS idx_offers_key ON offers(product_key, seen_at);
CREATE TABLE IF NOT EXISTS tracked (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    product_key TEXT NOT NULL UNIQUE,
    query TEXT NOT NULL,
    target_price REAL NOT NULL,
    created_at TEXT NOT NULL,
    last_checked TEXT, last_best REAL, last_store TEXT
);
"""


def connect(path=DB_PATH) -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_offers(conn, offers: list[Offer], query: str, seen_at: str | None = None):
    seen_at = seen_at or datetime.now().isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO offers (seen_at, query, product_key, store, title, price_inr, "
        "shipping_inr, total_inr, delivery_days, rating, in_stock, url, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(seen_at, query, product_key(o.title), o.store, o.title, o.price_inr,
          o.shipping_inr, o.total_inr, o.delivery_days, o.rating, int(o.in_stock),
          o.url, o.source) for o in offers],
    )
    conn.commit()


def history(conn, keys: list[str]) -> list[sqlite3.Row]:
    """Cheapest total per store per day for the given product keys."""
    marks = ",".join("?" * len(keys))
    return conn.execute(
        f"SELECT substr(seen_at, 1, 10) AS day, store, MIN(total_inr) AS total_inr "
        f"FROM offers WHERE product_key IN ({marks}) GROUP BY day, store ORDER BY day",
        keys,
    ).fetchall()


def track(conn, group: ProductGroup, query: str, target_price: float):
    conn.execute(
        "INSERT INTO tracked (title, product_key, query, target_price, created_at) "
        "VALUES (?,?,?,?,?) ON CONFLICT(product_key) DO UPDATE SET "
        "target_price=excluded.target_price, query=excluded.query",
        (group.title, product_key(group.title), query, target_price,
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def tracked(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM tracked ORDER BY created_at").fetchall()


def untrack(conn, tracked_id: int):
    conn.execute("DELETE FROM tracked WHERE id = ?", (tracked_id,))
    conn.commit()


def update_check(conn, tracked_id: int, best: float | None, store: str | None):
    conn.execute(
        "UPDATE tracked SET last_checked=?, last_best=?, last_store=? WHERE id=?",
        (datetime.now().isoformat(timespec="seconds"), best, store, tracked_id),
    )
    conn.commit()
