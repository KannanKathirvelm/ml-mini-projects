"""India-first helpers: ticker normalisation, NSE stock list + search, INR formatting,
market hours, near-live quotes and cache freshness.

Ticker rule (`normalize_ticker`), applied to the upper-cased input:
1. Index aliases: NIFTY / NIFTY50 / NIFTY 50 -> ^NSEI, SENSEX -> ^BSESN, BANKNIFTY -> ^NSEBANK.
   Renamed symbols: TATAMOTORS -> TMPV.NS (no data since the 2025 demerger), ZOMATO -> ETERNAL.NS.
2. A symbol in NSE's official equity list (data/nse_equities.csv, ~2,600 names) -> <SYMBOL>.NS,
   including ones with "-" or "&" such as BAJAJ-AUTO and M&M.
3. Anything with an explicit suffix or prefix (INFY.BO, AAPL.MX, ^GSPC, BRK-B, GC=F) is kept.
4. A known US symbol (KNOWN_US) is kept.
5. A company name is resolved against the NSE list: exact name, then name prefix
   ("state bank" -> SBIN.NS), then whole-word contains, then fuzzy (difflib, cutoff 0.8).
   Popular stocks win ties, then EQ series, then the shortest name.
6. Anything else is kept as typed (other US/foreign symbols); Yahoo then decides if it exists.
No network is needed to normalise. India-first means a symbol listed on both NSE and a US
exchange resolves to NSE unless it is in KNOWN_US.

Live data: Yahoo Finance's free feed. NSE quotes may be delayed by a few minutes and it is
not an official exchange feed; real-time data needs a licensed broker API (Kite Connect,
Upstox, SmartAPI) with the user's own account.
"""
import csv
import difflib
import json
import re
import threading
import time as _time
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
DATA_DIR = Path(__file__).parent / "data"
NSE_LIST = DATA_DIR / "nse_equities.csv"
NSE_LIST_META = DATA_DIR / "nse_equities_meta.json"
NSE_LIST_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_SNAPSHOT_DATE = "2026-10-24"  # date of the bundled snapshot (overridden by the meta file)
SOURCE = "Yahoo Finance (may be delayed)"
DELAYED_NOTE = ("Free Yahoo Finance data; NSE quotes may be delayed by a few minutes and are "
                "not an official exchange feed.")

# Checked against yfinance on 2026-10-24: every symbol below returned recent prices.
# TATAMOTORS.NS returns nothing since the demerger, so TMPV.NS is listed instead.
POPULAR_STOCKS = [
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Energy"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "sector": "IT"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "sector": "Banking"},
    {"symbol": "ICICIBANK.NS", "name": "ICICI Bank", "sector": "Banking"},
    {"symbol": "INFY.NS", "name": "Infosys", "sector": "IT"},
    {"symbol": "SBIN.NS", "name": "State Bank of India", "sector": "Banking"},
    {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel", "sector": "Telecom"},
    {"symbol": "ITC.NS", "name": "ITC", "sector": "FMCG"},
    {"symbol": "LT.NS", "name": "Larsen & Toubro", "sector": "Construction"},
    {"symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever", "sector": "FMCG"},
    {"symbol": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank", "sector": "Banking"},
    {"symbol": "AXISBANK.NS", "name": "Axis Bank", "sector": "Banking"},
    {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance", "sector": "Financial Services"},
    {"symbol": "MARUTI.NS", "name": "Maruti Suzuki India", "sector": "Automobile"},
    {"symbol": "SUNPHARMA.NS", "name": "Sun Pharmaceutical", "sector": "Pharma"},
    {"symbol": "TMPV.NS", "name": "Tata Motors Passenger Vehicles", "sector": "Automobile"},
    {"symbol": "ASIANPAINT.NS", "name": "Asian Paints", "sector": "Consumer Durables"},
    {"symbol": "WIPRO.NS", "name": "Wipro", "sector": "IT"},
    {"symbol": "HCLTECH.NS", "name": "HCL Technologies", "sector": "IT"},
    {"symbol": "TITAN.NS", "name": "Titan Company", "sector": "Consumer Durables"},
]
INDICES = [
    {"symbol": "^NSEI", "name": "NIFTY 50"},
    {"symbol": "^BSESN", "name": "S&P BSE SENSEX"},
    {"symbol": "^NSEBANK", "name": "NIFTY BANK"},
]
ALIASES = {"NIFTY": "^NSEI", "NIFTY50": "^NSEI", "NIFTY 50": "^NSEI", "SENSEX": "^BSESN",
           "BANKNIFTY": "^NSEBANK", "NIFTYBANK": "^NSEBANK", "NIFTY BANK": "^NSEBANK",
           "TATAMOTORS": "TMPV.NS", "TATA MOTORS": "TMPV.NS", "ZOMATO": "ETERNAL.NS"}
POPULAR_BARE = {s["symbol"].removesuffix(".NS") for s in POPULAR_STOCKS}
KNOWN_US = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "NVDA", "NFLX", "AMD", "INTC",
    "IBM", "ORCL", "CRM", "ADBE", "JPM", "BAC", "GS", "V", "MA", "KO", "PEP", "WMT", "DIS",
    "NKE", "MCD", "XOM", "CVX", "PFE", "JNJ", "UBER", "SPY", "QQQ", "BRK-B",
}
INDIAN_INDICES = {i["symbol"] for i in INDICES}
LEGAL_WORDS = {"limited", "ltd", "inc", "corporation", "corp", "company", "co", "plc", "the"}


# ------------------------------------------------------------------ NSE equity list
@lru_cache(maxsize=1)
def nse_equities() -> list[dict]:
    """NSE's official equity list (symbol, name, series, isin, listing_date)."""
    if not NSE_LIST.exists():
        return []
    with NSE_LIST.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _by_symbol() -> dict[str, dict]:
    return {r["symbol"]: r for r in nse_equities()}


def _clean_name(name: str) -> str:
    """'Infosys Limited' -> 'infosys'; '& ' and punctuation are dropped."""
    words = re.sub(r"[^a-z0-9& ]", " ", name.lower()).split()
    return " ".join(w for w in words if w not in LEGAL_WORDS)


@lru_cache(maxsize=1)
def _names() -> list[tuple[str, dict]]:
    return [(_clean_name(r["name"]), r) for r in nse_equities()]


def nse_snapshot_date() -> str:
    try:
        return json.loads(NSE_LIST_META.read_text())["snapshot_date"]
    except (OSError, ValueError, KeyError):
        return NSE_SNAPSHOT_DATE


def is_nse_listed(symbol: str) -> bool:
    return symbol.upper().removesuffix(".NS") in _by_symbol()


def _rank(r: dict, name: str) -> tuple:
    return (r["symbol"] not in POPULAR_BARE, r["series"] != "EQ", len(name), r["symbol"])


def _result(r: dict) -> dict:
    return {"symbol": f"{r['symbol']}.NS", "nse_symbol": r["symbol"], "name": r["name"],
            "isin": r["isin"], "series": r["series"]}


def resolve_name(query: str) -> str | None:
    """Company name -> NSE symbol (bare), or None. Exact, prefix, contains, then fuzzy."""
    q = _clean_name(query)
    if len(q) < 3:
        return None
    names = _names()
    for test in (lambda n: n == q, lambda n: n.startswith(q),
                 lambda n: re.search(rf"\b{re.escape(q)}\b", n) is not None):
        hits = [(n, r) for n, r in names if test(n)]
        if hits:
            return min(hits, key=lambda h: _rank(h[1], h[0]))[1]["symbol"]
    close = difflib.get_close_matches(q, [n for n, _ in names], n=1, cutoff=0.8)
    if close:
        return next(r for n, r in names if n == close[0])["symbol"]
    return None


def search_nse(query: str, limit: int = 10) -> list[dict]:
    """Symbol-prefix matches first, then names whose words start with every query word."""
    q = (query or "").strip()
    if not q:
        return []
    qu, words = q.upper(), _clean_name(q).split()
    sym_hits = [r for r in nse_equities() if r["symbol"].startswith(qu)]
    sym_hits.sort(key=lambda r: (r["symbol"] != qu, *_rank(r, r["name"])))
    name_hits = []
    if words:
        for n, r in _names():
            nw = n.split()
            if all(any(w.startswith(x) for w in nw) for x in words):
                name_hits.append((n, r))
        name_hits.sort(key=lambda h: _rank(h[1], h[0]))
    out, seen = [], set()
    for r in [*sym_hits, *(r for _, r in name_hits)]:
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            out.append(_result(r))
        if len(out) >= limit:
            break
    return out


def refresh_nse_list(timeout: float = 20) -> tuple[bool, str]:
    """Re-download NSE's EQUITY_L.csv into data/; keeps the bundled snapshot on any failure.

    NSE rejects requests without a browser-like User-Agent, and may block them anyway.
    """
    import io
    import urllib.request

    req = urllib.request.Request(NSE_LIST_URL, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
        "Accept": "text/csv,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8-sig")
        rows = [{k.strip(): (v or "").strip() for k, v in r.items()}
                for r in csv.DictReader(io.StringIO(text))]
        out = [{"symbol": r["SYMBOL"], "name": r["NAME OF COMPANY"], "series": r["SERIES"],
                "isin": r["ISIN NUMBER"],
                "listing_date": datetime.strptime(r["DATE OF LISTING"], "%d-%b-%Y").date().isoformat()}
               for r in rows if r.get("SYMBOL")]
        if len(out) < 1000:
            raise ValueError(f"only {len(out)} rows")
    except Exception as exc:
        return False, f"NSE download failed ({exc}); kept snapshot from {nse_snapshot_date()}."
    DATA_DIR.mkdir(exist_ok=True)
    with NSE_LIST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    NSE_LIST_META.write_text(json.dumps({"snapshot_date": date.today().isoformat(),
                                         "source": NSE_LIST_URL, "rows": len(out)}))
    for fn in (nse_equities, _by_symbol, _names):
        fn.cache_clear()
    return True, f"Saved {len(out)} NSE equities."


# ------------------------------------------------------------------ tickers
def normalize_ticker(raw: str) -> str:
    """User input -> Yahoo symbol, India first. See the module docstring for the rule."""
    t = " ".join((raw or "").split()).upper()
    if not t:
        raise ValueError("Empty ticker.")
    if t in ALIASES:
        return ALIASES[t]
    if t in _by_symbol() or t in POPULAR_BARE:
        return f"{t}.NS"
    if "." in t or t.startswith("^") or "=" in t or "-" in t:
        return t
    if t in KNOWN_US:
        return t
    sym = resolve_name(t)
    return f"{sym}.NS" if sym else t


def is_indian(symbol: str, currency: str | None = None) -> bool:
    s = symbol.upper()
    return s.endswith((".NS", ".BO")) or s in INDIAN_INDICES or currency == "INR"


def stock_name(symbol: str) -> str | None:
    for s in POPULAR_STOCKS + INDICES:
        if s["symbol"] == symbol:
            return s["name"]
    r = _by_symbol().get(symbol.removesuffix(".NS")) if symbol.endswith(".NS") else None
    return r["name"] if r else None


def no_data_message(symbol: str) -> str:
    """Clear message for a symbol Yahoo has no prices for."""
    if symbol.endswith(".NS") and is_nse_listed(symbol):
        return (f"{symbol.removesuffix('.NS')} is listed on NSE but Yahoo Finance has no price "
                "data for it (it may be suspended, an SME listing or newly listed).")
    return (f"No price data found for '{symbol}'. Check the symbol or company name "
            "(e.g. RELIANCE, TCS, Infosys, AAPL, ^NSEI).")


@lru_cache(maxsize=256)
def has_data(symbol: str) -> bool:
    """Does Yahoo return recent prices for `symbol`? Cached."""
    try:
        return not _yf().Ticker(symbol).history(period="1mo").dropna(subset=["Close"]).empty
    except Exception:
        return False


def _yf():
    """yfinance, imported lazily with its warnings and logging silenced."""
    import logging
    import warnings

    import yfinance as yf

    warnings.filterwarnings("ignore", module="yfinance")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    return yf


# ------------------------------------------------------------------ INR formatting
def _group_indian(n: int) -> str:
    """1234567 -> '12,34,567' (last three digits, then pairs)."""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    pairs = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([head, *pairs, tail])


def format_inr(x: float | None, decimals: int = 2) -> str:
    """1234567.8 -> '₹12,34,567.80' (Indian digit grouping)."""
    if x is None:
        return "n/a"
    sign = "-" if x < 0 else ""
    whole, frac = f"{abs(x):.{decimals}f}".partition(".")[::2]
    return f"{sign}₹{_group_indian(int(whole))}" + (f".{frac}" if decimals else "")


def format_inr_compact(x: float | None) -> str:
    """Large INR amounts in words: '₹17.2 lakh crore', '₹9,500 crore', '₹4.5 lakh'."""
    if x is None:
        return "n/a"
    sign, v = ("-" if x < 0 else ""), abs(x)
    if v >= 1e12:
        return f"{sign}₹{v / 1e12:,.1f} lakh crore"
    if v >= 1e7:
        return f"{sign}₹{_group_indian(round(v / 1e7))} crore"
    if v >= 1e5:
        return f"{sign}₹{v / 1e5:.1f} lakh"
    return sign + format_inr(v)


def format_money(x: float | None, currency: str | None, compact: bool = False) -> str:
    """₹ (Indian grouping) for INR, $ for USD, number plus currency code otherwise."""
    if x is None:
        return "n/a"
    if currency == "INR":
        return format_inr_compact(x) if compact else format_inr(x)
    prefix, suffix = ("$", "") if currency == "USD" else ("", f" {currency}" if currency else "")
    if compact:
        for div, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
            if abs(x) >= div:
                return f"{prefix}{x / div:,.2f}{unit}{suffix}"
    sign = "-" if x < 0 else ""
    return f"{sign}{prefix}{abs(x):,.2f}{suffix}"


def format_change(change: float | None, pct: float | None, currency: str | None) -> str:
    """'+₹5.50 (+0.46%)'."""
    if change is None or pct is None:
        return "n/a"
    sign = "+" if change >= 0 else "-"
    return f"{sign}{format_money(abs(change), currency)} ({pct:+.2f}%)"


# ------------------------------------------------------------------ market hours
# Regular sessions only. Exchange holidays are NOT accounted for.
EXCHANGES = {
    "NSE": (IST, time(9, 15), time(15, 30)),
    "US": (ZoneInfo("America/New_York"), time(9, 30), time(16, 0)),
}


def exchange_of(symbol: str) -> str:
    return "NSE" if is_indian(symbol) else "US"


def _next_weekday(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def market_status(now: datetime | None = None, exchange: str = "NSE") -> dict:
    """Open/closed plus the next open and close, as IST ISO timestamps."""
    tz, t_open, t_close = EXCHANGES[exchange]
    now = (now or datetime.now(IST)).astimezone(tz)
    today_open = datetime.combine(now.date(), t_open, tz)
    today_close = datetime.combine(now.date(), t_close, tz)
    weekday = now.weekday() < 5
    is_open = weekday and today_open <= now < today_close
    if is_open:
        next_open = datetime.combine(_next_weekday(now.date()), t_open, tz)
        next_close = today_close
    elif weekday and now < today_open:
        next_open, next_close = today_open, today_close
    else:
        day = _next_weekday(now.date())
        next_open, next_close = datetime.combine(day, t_open, tz), datetime.combine(day, t_close, tz)
    iso = lambda d: d.astimezone(IST).replace(microsecond=0).isoformat()
    return {"exchange": exchange, "is_open": is_open, "now_ist": iso(now),
            "next_open_ist": iso(next_open), "next_close_ist": iso(next_close),
            "note": "Exchange holidays not included"}


def last_completed_session(exchange: str = "NSE", now: datetime | None = None) -> date:
    """Date of the latest weekday session that has closed (holidays ignored)."""
    tz, _, t_close = EXCHANGES[exchange]
    now = (now or datetime.now(IST)).astimezone(tz)
    d = now.date()
    if d.weekday() < 5 and now.time() >= t_close:
        return d
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def cache_is_stale(symbol: str, last_bar: date, fetched_at: float, now: datetime | None = None) -> bool:
    """Should a cached daily-price file be re-downloaded?

    Market open: yes if fetched more than 5 minutes ago (today's bar is still forming).
    Market closed: yes if the last bar is older than the latest completed session,
    but at most every 30 minutes, so an exchange holiday does not cause a download
    on every request.
    """
    ex = exchange_of(symbol)
    age = _time.time() - fetched_at
    if market_status(now, ex)["is_open"]:
        return age > 300
    return last_bar < last_completed_session(ex, now) and age > 1800


def data_as_of(symbol: str, last_bar: date, fetched_at: float, now: datetime | None = None) -> dict:
    """'As of' for daily data: the fetch time when today's bar is live, else that day's close."""
    ex = exchange_of(symbol)
    tz, _, t_close = EXCHANGES[ex]
    status = market_status(now, ex)
    today = (now or datetime.now(IST)).astimezone(tz).date()
    live = status["is_open"] and last_bar == today
    when = (datetime.fromtimestamp(fetched_at, IST) if live
            else datetime.combine(last_bar, t_close, tz).astimezone(IST))
    note = ("Market is open: the latest daily bar is today's live, still-forming price."
            if live else "Based on daily closes up to the last completed session.")
    return {"as_of_ist": when.replace(microsecond=0).isoformat(), "live_bar": live,
            "market_open": status["is_open"], "note": note}


def fmt_ist(iso: str | None) -> str:
    """'2026-10-23T15:30:00+05:30' -> '23 Oct 2026, 15:30 IST'."""
    if not iso:
        return "n/a"
    return datetime.fromisoformat(iso).astimezone(IST).strftime("%d %b %Y, %H:%M IST")


# ------------------------------------------------------------------ live quotes
_qcache: dict[tuple, tuple[float, dict]] = {}
_qlock = threading.Lock()


def _cached(key: tuple, symbol: str, open_ttl: float, closed_ttl: float, fetch):
    """Short TTL while the symbol's market is open, long when closed."""
    with _qlock:
        hit = _qcache.get(key)
    is_open = market_status(exchange=exchange_of(symbol))["is_open"]
    ttl = open_ttl if is_open else closed_ttl
    if hit and _time.time() - hit[0] < ttl:
        return hit[1]
    value = fetch(is_open)
    with _qlock:
        _qcache[key] = (_time.time(), value)
    return value


def _num(x, n=2):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if x != x else round(x, n)


def live_quote(symbol: str) -> dict:
    """Near-live quote from Yahoo. Raises ValueError if Yahoo has no price for `symbol`.

    Cached ~15 s during market hours and ~10 min when the market is closed.
    """
    def fetch(is_open: bool) -> dict:
        t = _yf().Ticker(symbol)
        try:
            fi = t.fast_info
            price, prev = _num(fi.last_price), _num(fi.previous_close)
            o, hi, lo = _num(fi.open), _num(fi.day_high), _num(fi.day_low)
            vol, cur = fi.last_volume, fi.currency
        except Exception:
            price = None
        if price is None:
            raise ValueError(no_data_message(symbol))
        try:
            bars = t.history(period="1d", interval="1m")
            last = bars.index[-1].to_pydatetime().astimezone(IST) if len(bars) else None
        except Exception:
            last = None
        change = None if prev is None else round(price - prev, 2)
        pct = None if not prev else round((price - prev) / prev * 100, 2)
        return {
            "symbol": symbol, "name": stock_name(symbol), "price": price, "change": change,
            "change_pct": pct, "prev_close": prev, "open": o, "high": hi, "low": lo,
            "volume": None if vol is None else int(vol), "currency": cur,
            "display": {"price": format_money(price, cur), "change": format_change(change, pct, cur)},
            "as_of_ist": last.replace(microsecond=0).isoformat() if last else None,
            "market_open": is_open, "source": SOURCE, "delayed_note": DELAYED_NOTE,
        }

    return _cached(("quote", symbol), symbol, 15, 600, fetch)


def intraday(symbol: str, interval: str = "1m") -> dict:
    """Today's bars, or the last session's when the market has not traded today."""
    if interval not in ("1m", "5m"):
        raise ValueError("interval must be 1m or 5m")

    def fetch(is_open: bool) -> dict:
        t = _yf().Ticker(symbol)
        df = t.history(period="1d", interval=interval)
        if df.empty:
            df = t.history(period="5d", interval=interval)
        if df.empty:
            raise ValueError(no_data_message(symbol))
        tz = EXCHANGES[exchange_of(symbol)][0]  # group by the exchange's own calendar day
        idx = df.index.tz_convert(tz) if df.index.tz is not None else df.index.tz_localize(tz)
        df = df.set_axis(idx)
        session = df.index[-1].date()
        df = df[df.index.date == session]
        bars = [{"time_ist": ts.astimezone(IST).replace(microsecond=0).isoformat(), "open": _num(r.Open),
                 "high": _num(r.High), "low": _num(r.Low), "close": _num(r.Close),
                 "volume": int(r.Volume) if r.Volume == r.Volume else None}
                for ts, r in df.iterrows()]
        return {"symbol": symbol, "interval": interval, "session_date": session.isoformat(),
                "bars": bars, "market_open": is_open, "source": SOURCE}

    return _cached(("intraday", symbol, interval), symbol, 30, 600, fetch)


if __name__ == "__main__":
    import sys

    if "--refresh" in sys.argv:
        ok, msg = refresh_nse_list()
        print(msg)
        sys.exit(0 if ok else 1)
    print(f"{len(nse_equities())} NSE equities (snapshot {nse_snapshot_date()}). "
          "Run `python india.py --refresh` to re-download.")
