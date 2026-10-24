# 🛒 Price Comparison App

Search for a product and see prices from several stores side by side. Offers for the same product are grouped, the cheapest total (price + shipping) is highlighted, and every search is stored so you can chart price history and get alerts when a tracked product drops to your target price.

Comes with a Streamlit dashboard and a CLI.

## Which stores are real and which are simulated

| Store | Type | Data source | Notes |
|---|---|---|---|
| **DummyJSON** | Real public **demo** API | `https://dummyjson.com/products/search?q=` | Free, no key. Prices in USD, converted to INR. Delivery days come from its `shippingInformation` text. No shipping cost given, so shipping is 0. |
| **FakeStoreAPI** | Real public **demo** API | `https://fakestoreapi.com/products` | Free, no key. Only 20 products and no search endpoint, so the list is fetched once and filtered locally. USD prices. No shipping or delivery data. |
| **ShopKart** | **Simulated** | `data/catalog.json` | Marketplace: about 2% cheaper, free shipping over Rs 499 (otherwise Rs 40), 2–5 days. |
| **MegaMart** | **Simulated** | `data/catalog.json` | Value store: about 4% cheaper, free shipping over Rs 999 (otherwise Rs 79), 4–8 days. |
| **QuickBuy** | **Simulated** | `data/catalog.json` | Quick commerce: about 3% pricier, always free shipping, 1–2 days. |

The demo APIs are sample data for developers. They are not shops and their products cannot be bought. **No real retailer (Amazon, Flipkart, etc.) is scraped.** Scraping is fragile, usually against the site's terms, and runs into bot detection. A real store should be added through an official product or affiliate API (see below).

**Currency:** USD prices are converted at a fixed **Rs 83 = $1** (`config.USD_TO_INR`). The rate is fixed on purpose so comparisons and history can be reproduced.

**How the simulation works:** each simulated price comes from a stable hash of `(store, product, date)`. It is made of the base price, a store-wide bias, a per-product bias, a slow sine-wave drift (20–45 day period), ±1% daily noise and an occasional 10%-off sale day. So:
- the same day always gives the same prices (reproducible), and
- prices change realistically from day to day, which is why past days can be backfilled.

Stock (about 92% in stock), delivery days and ratings are derived the same way. Each store carries only part of the catalog (70–90%), so not every product is everywhere.

## Architecture

```
query ─▶ search.search_all ──(parallel, per-store try/except)──▶ [Store.search(query) → list[Offer]]
                │                                                  DummyJSON · FakeStoreAPI · ShopKart · MegaMart · QuickBuy
                ▼
        matching.group_offers  ── fuzzy title match + model-number check ─▶ ProductGroup (best, worst, savings)
                │
                ├─▶ db.save_offers → data/prices.db (history)      ◀── history.seed_history (30 days, simulated stores)
                └─▶ compare.py (CLI) · app.py (Streamlit) · alerts.check_alerts → check_alerts.py
```

- **`stores/base.py`**: the contract. `Offer` (store, title, price_inr, shipping_inr, delivery_days, rating, in_stock, url, `total_inr`) and the abstract `Store.search(query) -> list[Offer]`. It also holds one shared HTTP session with an 8 s timeout and a clear User-Agent.
- **`search.py`**: queries all stores in parallel. If one store raises an error (timeout, DNS, bad JSON), it is recorded and skipped, and the others carry on.
- **`matching.py`**: normalises titles (lowercase, no punctuation, filler and brand words dropped), then groups offers whose `rapidfuzz.token_sort_ratio` is at least 88 **and** whose model-number tokens (anything with a digit) are identical. So `"Apple iPhone X"` and `"iPhone X"` are grouped, but `"Galaxy S8"` and `"Galaxy S10"`, or `"iPhone 13"` and `"iPhone 13 Pro"`, are not. The best deal is the lowest in-stock total (ties go to the higher rating). Savings are measured against the priciest in-stock offer.
- **`db.py`**: SQLite tables `offers` (one row per offer per search, with timestamp) and `tracked` (product, query, target price, last check). History is keyed by a normalised `product_key`, so a group's chart covers all its title variants.
- **`history.py`**: `--seed-history` backfills 30 days for the simulated stores only. Their past prices really can be computed. The demo APIs have no history, so they only gain points from real searches.
- **`alerts.py` / `check_alerts.py`**: for each tracked product, re-runs its query, finds its group again and compares the best total with the target.

## How to add a real store

Write one adapter. Nothing else in the app changes:

1. Create `stores/mystore.py`:

    ```python
    from config import USD_TO_INR
    from stores.base import Offer, Store, get_json

    class MyStore(Store):
        name = "MyStore"
        source = "api"

        def search(self, query: str) -> list[Offer]:
            data = get_json("https://api.mystore.example/v1/products",
                            {"q": query, "api_key": "..."})  # official / affiliate API
            return [Offer(store=self.name, title=p["name"],
                          price_inr=p["price"],             # convert if not INR
                          shipping_inr=p.get("shipping", 0),
                          delivery_days=p.get("eta_days"),
                          rating=p.get("rating"),
                          in_stock=p.get("available", True),
                          url=p["url"], source=self.source)
                    for p in data["items"]]
    ```

2. Register it in `stores/__init__.py` → `all_stores()`.

That is all. Matching, best-deal logic, history, alerts, CLI and UI pick it up automatically, and if it raises an error it is shown as "unavailable" instead of crashing the search. For a real integration, use the retailer's **official product or affiliate API**. Keep API keys in environment variables (not in code), follow its rate limits and terms, and cache responses if the API has quotas.

## Run it

Create the environment and install dependencies:

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

Backfill 30 days of price history so the charts have data:

```bash
.venv/bin/python compare.py --seed-history
```

Compare prices from the CLI:

```bash
.venv/bin/python compare.py "iphone"
```

Track a product with a target total price (INR):

```bash
.venv/bin/python compare.py "iphone" --track "iPhone 13 Pro" --target 95000
```

Check tracked products. The exit code is 2 if any alert fired, which is handy for cron:

```bash
.venv/bin/python check_alerts.py
```

Open the dashboard:

```bash
.venv/bin/streamlit run app.py
```

The dashboard has three tabs:
- **Compare**: search box; per-product comparison table (store, title, price, shipping, total, delivery, rating, in stock, link); best-deal and savings callouts; sort by total, rating or delivery; filters for minimum rating, max delivery days and in stock only; a "Track this product" button.
- **Price history**: Plotly chart of the cheapest daily total per store, the lowest recorded price, a table view and a "Seed 30 days" button.
- **Tracked & alerts**: tracked products with target, last best price and status, a "Check alerts now" button, and remove.

## Sample output (real run, 2026-10-24)

```
$ python compare.py "laptop" --top 2
Search "laptop": 27 offers from 5 store(s), 8 product(s)

[1] Huawei Matebook X Pro  (4 store(s))
    store               price    ship       total days rating  stock
    MegaMart      Rs 1,08,309    Rs 0 Rs 1,08,309    8    3.8  yes <- best
    ShopKart      Rs 1,13,349    Rs 0 Rs 1,13,349    3    4.7  yes
    QuickBuy      Rs 1,16,179    Rs 0 Rs 1,16,179    1    3.9  NO
    DummyJSON     Rs 1,16,199    Rs 0 Rs 1,16,199    1   4.98  yes
    Best deal: MegaMart at Rs 1,08,309; saves Rs 7,890 vs DummyJSON

[2] New DELL XPS 13 9300 Laptop  (4 store(s))
    store               price    ship       total days rating  stock
    MegaMart      Rs 1,17,049    Rs 0 Rs 1,17,049    4    4.6  yes <- best
    ShopKart      Rs 1,23,509    Rs 0 Rs 1,23,509    4    3.7  yes
    DummyJSON     Rs 1,24,499    Rs 0 Rs 1,24,499   14   2.67  yes
    QuickBuy      Rs 1,25,459    Rs 0 Rs 1,25,459    2    4.6  yes
    Best deal: MegaMart at Rs 1,17,049; saves Rs 8,410 vs QuickBuy
```

When the stickers tie, shipping decides the winner:

```
$ python compare.py "wild stone"
[1] Wild Stone Ultra Sensual Perfume  (2 store(s))
    ShopKart           Rs 429   Rs 40      Rs 469    2    3.9  yes <- best
    MegaMart           Rs 429   Rs 79      Rs 508    6    4.0  yes
    Best deal: ShopKart at Rs 469; saves Rs 39 vs MegaMart
```

With a store down, the search carries on with the rest. This run simulated a network outage for both demo APIs:

```
Search "perfume": 15 offers from 3 store(s), 6 product(s)
  ! DummyJSON unavailable, skipped (ConnectionError: network down (simulated))
  ! FakeStoreAPI unavailable, skipped (ConnectionError: network down (simulated))
```

Alerts:

```
$ python check_alerts.py
[HIT ] iPhone 13 Pro: best Rs 85,489 at MegaMart (target Rs 95,000)
[wait] Apple MacBook Pro 14 Inch Space Grey: best Rs 1,65,999 at DummyJSON (target Rs 1,50,000)

1 of 2 tracked product(s) at or below target.
```

Prices for the simulated stores depend on the date, so your numbers will differ.

## Project structure

```
05_price_comparison_app/
├── app.py              # Streamlit dashboard (compare / history / alerts tabs)
├── compare.py          # CLI: search, --track, --seed-history
├── check_alerts.py     # re-check tracked products (cron-friendly)
├── search.py           # query all stores in parallel, isolate failures
├── matching.py         # title normalisation, fuzzy grouping, best deal & savings
├── db.py               # SQLite: offers history + tracked products
├── history.py          # 30-day backfill for simulated stores
├── alerts.py           # alert logic shared by CLI and UI
├── formatting.py       # Indian-style rupee formatting (Rs 1,23,456)
├── config.py           # paths, fixed USD->INR rate, timeout, User-Agent
├── stores/
│   ├── base.py         # Offer + Store interface + HTTP helper
│   ├── dummyjson.py    # real demo API
│   ├── fakestore.py    # real demo API
│   └── simulated.py    # ShopKart / MegaMart / QuickBuy
├── data/
│   ├── catalog.json    # seed catalog for the simulated stores (36 products)
│   └── prices.db       # created at runtime (git-ignored)
├── requirements.txt
└── .gitignore
```

## Limitations

- Title matching is a heuristic. It is strict on model numbers on purpose, so a variant listed with extra specs (for example "iPhone 15 128GB" vs "iPhone 15") stays a separate product. Two different products with very similar names and no model number could, in rare cases, be grouped together.
- Demo-API prices are static, and their "stores" are not real shops. Shipping for them is 0 because the APIs don't provide it.
- The exchange rate is fixed, not live.
