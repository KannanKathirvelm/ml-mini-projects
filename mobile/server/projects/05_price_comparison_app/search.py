"""Run a query against every store, isolating failures per store.

Stores are queried in parallel; any exception (timeout, DNS, bad JSON) is
recorded as an error for that store and the others carry on.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from matching import ProductGroup, group_offers
from stores import Store, all_stores
from stores.base import Offer


@dataclass
class SearchResult:
    query: str
    offers: list[Offer]
    groups: list[ProductGroup]
    errors: dict[str, str]          # store name -> error message
    stores_ok: list[str]


def search_all(query: str, stores: list[Store] | None = None) -> SearchResult:
    stores = stores if stores is not None else all_stores()
    offers: list[Offer] = []
    errors: dict[str, str] = {}
    ok: list[str] = []

    def run(store: Store):
        return store.search(query)

    with ThreadPoolExecutor(max_workers=len(stores) or 1) as pool:
        futures = {store.name: pool.submit(run, store) for store in stores}
        for name, fut in futures.items():
            try:
                offers.extend(fut.result())
                ok.append(name)
            except Exception as exc:  # one bad store must never break the search
                errors[name] = f"{type(exc).__name__}: {exc}"[:200]

    return SearchResult(query, offers, group_offers(offers), errors, ok)
