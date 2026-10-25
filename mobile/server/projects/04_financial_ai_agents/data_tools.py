"""Data tools: thin wrappers around yfinance (free, no API key).

Every agent works from the same three inputs - price history, key stats and
recent headlines - so they are fetched once here and handed to the agents.
Yahoo responses are patchy (missing fields, empty news, odd tickers), so each
function returns clean Python data and never leaks a yfinance exception except
`TickerNotFound` for a symbol with no price data.
"""
import logging
import re
import warnings
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from india import is_indian, no_data_message

# Must come after the import: yfinance installs its own "default" filter for
# DeprecationWarning on import, which would otherwise win over ours.
warnings.filterwarnings("ignore", module="yfinance")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Ticker.info key -> label shown in reports. Anything missing is simply skipped.
FUNDAMENTAL_FIELDS = {
    "marketCap": "Market cap",
    "totalRevenue": "Revenue (TTM)",
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


# Fallback when Yahoo has no live Nifty 50 P/E: the index has mostly traded at
# 18-24x trailing earnings over the last decade. Shown as a stated reference.
NIFTY_PE_REFERENCE = 21.0


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
        raise TickerNotFound(no_data_message(ticker))
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


def _related(ticker: str) -> set[str]:
    """Symbols Yahoo may tag this company with: RELIANCE.NS, RELIANCE.BO, RELIANCE."""
    base = ticker.split(".")[0]
    return {ticker, base, f"{base}.NS", f"{base}.BO"}


LEGAL_SUFFIXES = {"limited", "ltd", "ltd.", "inc", "inc.", "corporation", "corp", "corp.",
                  "company", "co", "co.", "plc", "holdings"}


def name_key(company_name: str | None) -> str:
    """'Reliance Industries Limited' -> 'reliance industries'; 'Apple Inc.' -> 'apple'.

    Two words, because one is too loose for Indian names ("Reliance" also matches
    Reliance Steel and headlines about "import reliance").
    """
    words = [w.strip(",.").lower() for w in (company_name or "").split()]
    words = [w for w in words if w and w not in LEGAL_SUFFIXES]
    return " ".join(words[:2])


def _mentions(title: str, phrase: str) -> bool:
    return bool(phrase) and re.search(rf"\b{re.escape(phrase)}\b", title.lower()) is not None


def _search_news(query: str, ticker: str, names: list[str], base: str | None, limit: int) -> list:
    """Yahoo search news, keeping only items that plausibly concern this company.

    Kept: items tagged with one of our symbols, or untagged items whose title
    names the company, or its NSE symbol in capitals (e.g. "TCS"). Items tagged only with
    *other* symbols are dropped, which stops "Reliance Steel (RS)" headlines
    leaking into a RELIANCE.NS report.
    """
    try:
        found = yf.Search(query, news_count=limit).news or []
    except Exception:
        return []
    ours = _related(ticker)
    keep = []
    for n in found:
        tags = set(n.get("relatedTickers") or [])
        title = n.get("title") or ""
        if tags & ours or (not tags and (any(_mentions(title, k) for k in names)
                                         or (base and re.search(rf"\b{re.escape(base)}\b", title)))):
            keep.append(n)
    return keep


def get_news(ticker: str, company_name: str | None = None, limit: int = 10) -> list[dict]:
    """Recent headlines. Ticker.news is often empty (almost always for NSE/BSE symbols),
    so top up from Yahoo search by symbol, symbol without the exchange suffix, full
    company name and its short name, until `limit` relevant items are found."""
    try:
        raw = list(yf.Ticker(ticker).news or [])
    except Exception:
        raw = []
    base = ticker.split(".")[0] if is_indian(ticker) and not ticker.startswith("^") else None
    short_name = name_key(company_name)
    names = [short_name]
    caps = base if base and len(base) >= 3 else None  # "TCS" yes, "Reliance" (a word) no
    for query in dict.fromkeys(q for q in (ticker, base, company_name, short_name) if q):
        if len(raw) >= limit:
            break
        raw += _search_news(query, ticker, names, caps, limit)
    items, seen = [], set()
    for item in raw:
        parsed = _parse_news_item(item)
        if parsed and parsed["title"] not in seen:
            seen.add(parsed["title"])
            items.append(parsed)
    return items[:limit]


def benchmark_for(ticker: str, currency: str | None) -> tuple[str, str]:
    """Nifty 50 for Indian symbols, S&P 500 for everything else."""
    return ("^NSEI", "NIFTY 50") if is_indian(ticker, currency) else ("^GSPC", "S&P 500")


def get_index_close(symbol: str, period: str = "2y") -> pd.Series | None:
    """Benchmark closes, or None if Yahoo fails (the report then skips the comparison)."""
    try:
        return get_price_history(symbol, period)["Close"]
    except TickerNotFound:
        return None


def get_market_pe() -> dict:
    """Nifty 50 trailing P/E: the index quote rarely carries one, so try the NIFTYBEES
    ETF (it holds the index) and fall back to a stated long-run reference."""
    for symbol, source in (("^NSEI", "Yahoo ^NSEI"), ("NIFTYBEES.NS", "Yahoo NIFTYBEES.NS (Nifty 50 ETF)")):
        try:
            pe = (yf.Ticker(symbol).info or {}).get("trailingPE")
        except Exception:
            pe = None
        if pe:
            return {"pe": float(pe), "source": source, "live": True}
    return {"pe": NIFTY_PE_REFERENCE, "source": "stated long-run reference (not live)", "live": False}
