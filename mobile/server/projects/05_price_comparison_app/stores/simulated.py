"""Simulated Indian stores built from a local seed catalog (data/catalog.json).

These exist so the comparison is meaningful offline and so price history has
something realistic to show. Nothing here talks to a real retailer.

Every number is derived from a stable hash of (store, sku, date), so:
  * the same day always gives the same prices (reproducible demos/tests), and
  * prices drift day to day: a slow seasonal wave, small daily noise and the
    occasional sale day, rather than random jumps.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import date

from config import CATALOG_PATH
from stores.base import Offer, Store


def _rng(*parts) -> random.Random:
    seed = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


def load_catalog() -> list[dict]:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


class SimulatedStore(Store):
    source = "simulated"

    def __init__(self, name: str, slug: str, price_bias: float, carry_rate: float,
                 delivery: tuple[int, int], free_ship_over: float, ship_fee: float,
                 sale_chance: float):
        self.name, self.slug = name, slug
        self.price_bias = price_bias          # store-wide markup/discount
        self.carry_rate = carry_rate          # share of the catalog it stocks
        self.delivery = delivery              # (min, max) delivery days
        self.free_ship_over, self.ship_fee = free_ship_over, ship_fee
        self.sale_chance = sale_chance        # probability of a sale on a given day
        self.catalog = load_catalog()

    def carries(self, sku: str) -> bool:
        return _rng(self.name, sku, "carry").random() < self.carry_rate

    def offer_for(self, item: dict, day: date) -> Offer:
        sku = item["sku"]
        fixed = _rng(self.name, sku)                      # per-product, never changes
        daily = _rng(self.name, sku, day.isoformat())     # changes every day

        product_bias = fixed.uniform(-0.05, 0.05)
        phase, period = fixed.uniform(0, 2 * math.pi), fixed.uniform(20, 45)
        wave = 0.035 * math.sin(2 * math.pi * day.toordinal() / period + phase)
        noise = daily.uniform(-0.01, 0.01)
        sale = 0.10 if daily.random() < self.sale_chance else 0.0

        factor = 1 + self.price_bias + product_bias + wave + noise - sale
        price = round(item["base_inr"] * factor / 10) * 10 - 1   # "Rs 1,299"-style
        shipping = 0.0 if price >= self.free_ship_over else self.ship_fee
        lo, hi = self.delivery
        return Offer(
            store=self.name,
            title=item["title"],
            price_inr=float(price),
            shipping_inr=shipping,
            delivery_days=daily.randint(lo, hi),
            rating=round(fixed.uniform(3.6, 4.8), 1),
            in_stock=daily.random() > 0.08,
            url=f"https://example.com/{self.slug}/p/{sku.lower()}",
            source=self.source,
        )

    def matches(self, item: dict, query: str) -> bool:
        haystack = f"{item['title']} {item['category']} {item['keywords']}".lower()
        return all(w in haystack for w in query.lower().split())

    def search(self, query: str, day: date | None = None) -> list[Offer]:
        day = day or date.today()
        return [self.offer_for(item, day) for item in self.catalog
                if self.carries(item["sku"]) and self.matches(item, query)]


def simulated_stores() -> list[SimulatedStore]:
    return [
        # Big marketplace: slightly cheaper, free shipping over Rs 499, 2-5 days.
        SimulatedStore("ShopKart", "shopkart", -0.02, 0.90, (2, 5), 499, 40, 0.08),
        # Value retailer: cheapest sticker price but flat fee under Rs 999, slow.
        SimulatedStore("MegaMart", "megamart", -0.04, 0.80, (4, 8), 999, 79, 0.05),
        # Quick commerce: premium price, always free and next-day.
        SimulatedStore("QuickBuy", "quickbuy", 0.03, 0.70, (1, 2), 0, 0, 0.04),
    ]
