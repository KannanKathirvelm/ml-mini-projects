"""Shared settings in one place so adapters, CLI and UI agree on them.

The USD->INR rate is deliberately fixed (not fetched live): the demo APIs
price in USD, and a stable rate keeps comparisons and history reproducible.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "prices.db"
CATALOG_PATH = DATA_DIR / "catalog.json"

USD_TO_INR = 83.0           # fixed, documented conversion rate
REQUEST_TIMEOUT = 8         # seconds per HTTP request
USER_AGENT = "PriceCompareDemo/1.0 (portfolio project; contact: none)"
