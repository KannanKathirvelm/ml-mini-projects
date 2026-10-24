"""Adapter for DummyJSON (https://dummyjson.com) - a free, keyless demo API.

Prices are USD, so we convert at the fixed rate. The API has no shipping
cost, so shipping is 0; delivery days are parsed from its free-text
"shippingInformation". Its search is title-based, so a few generic words
("perfume") are mapped to its category slugs as a fallback.
"""
import re

from config import USD_TO_INR
from stores.base import Offer, Store, get_json

CATEGORY_ALIASES = {
    "perfume": "fragrances", "perfumes": "fragrances", "fragrance": "fragrances",
    "laptop": "laptops", "laptops": "laptops",
    "phone": "smartphones", "smartphone": "smartphones", "mobile": "smartphones",
    "tablet": "tablets", "watch": "mens-watches",
}


def _delivery_days(text: str) -> int | None:
    text = (text or "").lower()
    if "overnight" in text:
        return 1
    m = re.search(r"(\d+)[-\s]*(\d+)?\s*(?:business\s+)?(day|week|month)", text)
    if not m:
        return None
    n = int(m.group(2) or m.group(1))
    return n * {"day": 1, "week": 7, "month": 30}[m.group(3)]


class DummyJSONStore(Store):
    name = "DummyJSON"
    source = "api"
    base_url = "https://dummyjson.com"

    def search(self, query: str) -> list[Offer]:
        data = get_json(f"{self.base_url}/products/search", {"q": query, "limit": 50})
        products = data.get("products", [])
        alias = CATEGORY_ALIASES.get(query.strip().lower())
        if not products and alias:
            products = get_json(f"{self.base_url}/products/category/{alias}").get("products", [])
        return [
            Offer(
                store=self.name,
                title=p["title"],
                price_inr=round(p["price"] * USD_TO_INR, 2),
                shipping_inr=0.0,
                delivery_days=_delivery_days(p.get("shippingInformation", "")),
                rating=round(p["rating"], 1) if p.get("rating") is not None else None,
                in_stock=p.get("availabilityStatus", "In Stock") != "Out of Stock",
                url=f"{self.base_url}/products/{p['id']}",
                source=self.source,
            )
            for p in products
        ]
