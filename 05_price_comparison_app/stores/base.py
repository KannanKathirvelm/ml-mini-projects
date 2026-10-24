"""The store-adapter contract.

Every store, real API or simulated, turns a query into a list of `Offer`s
already normalised to INR. The rest of the app only ever sees `Offer`s, so
adding a store never requires touching matching, the database or the UI.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict

import requests

from config import REQUEST_TIMEOUT, USER_AGENT


@dataclass
class Offer:
    store: str
    title: str
    price_inr: float
    shipping_inr: float = 0.0
    delivery_days: int | None = None
    rating: float | None = None
    in_stock: bool = True
    url: str = ""
    source: str = "api"          # "api" (real demo API) or "simulated"

    @property
    def total_inr(self) -> float:
        return round(self.price_inr + self.shipping_inr, 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_inr"] = self.total_inr
        return d


class Store(ABC):
    name: str = "Store"
    source: str = "api"

    @abstractmethod
    def search(self, query: str) -> list[Offer]:
        """Return offers matching `query`. May raise; the caller isolates failures."""


_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


def get_json(url: str, params: dict | None = None):
    """GET with a timeout and our User-Agent; raises on HTTP/network errors."""
    resp = _session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()
