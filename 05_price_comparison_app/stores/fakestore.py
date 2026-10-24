"""Adapter for Fake Store API (https://fakestoreapi.com) - free, keyless demo API.

It has no search endpoint and only ~20 products, so we download the list
once per process and filter it locally by query words. Prices are USD.
No shipping or delivery data is provided.
"""
from config import USD_TO_INR
from stores.base import Offer, Store, get_json


class FakeStoreAPIStore(Store):
    name = "FakeStoreAPI"
    source = "api"
    base_url = "https://fakestoreapi.com"

    def __init__(self):
        self._cache: list[dict] | None = None

    def _products(self) -> list[dict]:
        if self._cache is None:
            self._cache = get_json(f"{self.base_url}/products")
        return self._cache

    def search(self, query: str) -> list[Offer]:
        words = query.lower().split()
        hits = [p for p in self._products()
                if all(w in f"{p['title']} {p['category']}".lower() for w in words)]
        return [
            Offer(
                store=self.name,
                title=p["title"].strip(),
                price_inr=round(p["price"] * USD_TO_INR, 2),
                rating=(p.get("rating") or {}).get("rate"),
                url=f"{self.base_url}/products/{p['id']}",
                source=self.source,
            )
            for p in hits
        ]
