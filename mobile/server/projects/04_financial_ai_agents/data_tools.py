"""Data tools: thin wrappers around yfinance (free, no API key).

Every agent works from the same three inputs - price history, key stats and
recent headlines - so they are fetched once here and handed to the agents.
Yahoo responses are patchy (missing fields, empty news, odd tickers), so each
function returns clean Python data and never leaks a yfinance exception except
`TickerNotFound` for a symbol with no price data.
"""
import logging
import warnings
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

# Must come after the import: yfinance installs its own "default" filter for
# DeprecationWarning on import, which would otherwise win over ours.
warnings.filterwarnings("ignore", module="yfinance")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Ticker.info key -> label shown in reports. Anything missing is simply skipped.
FUNDAMENTAL_FIELDS = {
    "marketCap": "Market cap",
    "trailingPE": "P/E (trailing)",
    "forwardPE": "P/E (forward)",
    "pegRatio": "PEG ratio",
    "priceToBook": "Price / book",
    "profitMargins": "Profit margin",
    "operatingMargins": "Operating margin",
    "grossMargins": "Gross margin",
    "returnOnEquity": "Return on equity",
    "revenueGrowth": "Revenue growth (YoY)",
    "earningsGrowth": "Earnings growth (YoY)",
    "debtToEquity": "Debt / equity (%)",
    "currentRatio": "Current ratio",
    "dividendYield": "Dividend yield (%)",
    "beta": "Beta",
    "recommendationKey": "Analyst consensus",
    "targetMeanPrice": "Analyst mean target",
    "currentPrice": "Current price",
}
PROFILE_FIELDS = ["longName", "shortName", "sector", "industry", "currency", "exchange", "quoteType"]


class TickerNotFound(ValueError):
    """Raised when Yahoo returns no price history for a symbol."""


def get_price_history(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Daily OHLCV history. Two years gives the 200-day SMA room to warm up."""
    try:
        df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    except Exception as exc:  # network errors, malformed symbols
        raise TickerNotFound(f"Could not download data for '{ticker}': {exc}") from exc
    df = df.dropna(subset=["Close"]) if not df.empty else df
    if df.empty or len(df) < 30:
        raise TickerNotFound(
            f"No price data found for '{ticker}'. Check the Yahoo Finance symbol "
            "(e.g. AAPL, MSFT, RELIANCE.NS, TCS.NS)."
        )
    df.index = df.index.tz_localize(None)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def get_fundamentals(ticker: str) -> dict:
    """Company profile + key stats. Returns {} fields gracefully when Yahoo omits them."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    profile = {k: info.get(k) for k in PROFILE_FIELDS if info.get(k) is not None}
    stats = {k: info[k] for k in FUNDAMENTAL_FIELDS if info.get(k) is not None}
    return {"profile": profile, "stats": stats}


def _parse_news_item(item: dict) -> dict | None:
    """Normalise both yfinance news shapes (flat legacy and nested `content`)."""
    content = item.get("content") or item
    title = content.get("title")
    if not title:
        return None
    publisher = content.get("publisher") or (content.get("provider") or {}).get("displayName", "")
    when = content.get("providerPublishTime") or content.get("pubDate")
    if isinstance(when, (int, float)):
        when = datetime.fromtimestamp(when, tz=timezone.utc).strftime("%Y-%m-%d")
    elif isinstance(when, str):
        when = when[:10]
    link = content.get("link") or (content.get("canonicalUrl") or {}).get("url", "")
    return {"title": title.strip(), "publisher": publisher, "date": when or "", "link": link}


def _search_news(query: str, ticker: str, name_word: str, limit: int) -> list:
    """Yahoo search news, keeping only items that plausibly concern this company."""
    try:
        found = yf.Search(query, news_count=limit).news or []
    except Exception:
        return []
    return [n for n in found
            if ticker in (n.get("relatedTickers") or [])
            or (name_word and name_word in (n.get("title") or "").lower())]


def get_news(ticker: str, company_name: str | None = None, limit: int = 10) -> list[dict]:
    """Recent headlines. Ticker.news is often empty, so fall back to Yahoo search
    by symbol, then by company name (first two words, e.g. "Reliance Industries")."""
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        raw = []
    name_word = (company_name or "").split(" ")[0].lower()
    short_name = " ".join((company_name or "").split()[:2])
    for query in dict.fromkeys(q for q in (ticker, company_name, short_name) if q):
        if raw:
            break
        raw = _search_news(query, ticker, name_word, limit)
    items, seen = [], set()
    for item in raw:
        parsed = _parse_news_item(item)
        if parsed and parsed["title"] not in seen:
            seen.add(parsed["title"])
            items.append(parsed)
    return items[:limit]
