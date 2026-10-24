"""Group offers for the same product across stores.

Stores title the same item differently ("Apple iPhone 13 Pro" vs
"iPhone 13 Pro"), so we compare a normalised title: lowercase, punctuation
stripped, brand/filler words dropped. Two titles match when their fuzzy
score is high AND their model-number tokens (anything containing a digit)
are identical - that last rule stops "Galaxy S8" grouping with "Galaxy S10"
or "iPhone 13" with "iPhone 13 Pro" (the "pro" makes the score too low).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from stores.base import Offer

MATCH_THRESHOLD = 88

# Words that vary between listings of the same product and carry no identity.
NOISE = {
    "apple", "samsung", "dell", "lenovo", "huawei", "asus", "hp", "oppo", "vivo",
    "realme", "new", "the", "with", "and", "for", "laptop", "smartphone",
    "mobile", "phone", "inch", "inches", "edition", "official",
}


def normalise(title: str) -> list[str]:
    words = re.sub(r"[^a-z0-9 ]+", " ", title.lower()).split()
    return [w for w in words if w not in NOISE]


def product_key(title: str) -> str:
    """Stable id for a listing title, used to link history rows and tracking."""
    return " ".join(sorted(normalise(title)))


def _model_tokens(tokens: list[str]) -> set[str]:
    return {t for t in tokens if any(c.isdigit() for c in t)}


def same_product(a: str, b: str) -> bool:
    ta, tb = normalise(a), normalise(b)
    if _model_tokens(ta) != _model_tokens(tb):
        return False
    return fuzz.token_sort_ratio(" ".join(ta), " ".join(tb)) >= MATCH_THRESHOLD


@dataclass
class ProductGroup:
    title: str
    offers: list[Offer] = field(default_factory=list)

    @property
    def keys(self) -> list[str]:
        return sorted({product_key(o.title) for o in self.offers})

    @property
    def stores(self) -> set[str]:
        return {o.store for o in self.offers}

    def _ranked(self) -> list[Offer]:
        in_stock = [o for o in self.offers if o.in_stock] or self.offers
        return sorted(in_stock, key=lambda o: (o.total_inr, -(o.rating or 0)))

    @property
    def best(self) -> Offer:
        return self._ranked()[0]

    @property
    def worst(self) -> Offer:
        return self._ranked()[-1]

    @property
    def savings(self) -> float:
        """How much the best deal saves vs the most expensive in-stock offer."""
        return round(self.worst.total_inr - self.best.total_inr, 2)


def group_offers(offers: list[Offer]) -> list[ProductGroup]:
    """Greedy clustering: each offer joins the first group it matches."""
    groups: list[ProductGroup] = []
    for offer in offers:
        for g in groups:
            if same_product(offer.title, g.title):
                g.offers.append(offer)
                break
        else:
            groups.append(ProductGroup(title=offer.title, offers=[offer]))
    # Products sold by more stores are the interesting comparisons: show first.
    groups.sort(key=lambda g: (-len(g.stores), g.best.total_inr))
    return groups
