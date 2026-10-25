"""India helpers: ticker normalisation, NSE search, INR formatting, market hours, benchmark maths.

All offline: no Yahoo, no Claude API. The NSE list is the bundled data/nse_equities.csv.
"""
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

import india
from data_tools import benchmark_for
from indicators import benchmark_stats

IST = india.IST


# ------------------------------------------------------------------ normalisation
@pytest.mark.parametrize("raw,expected", [
    # NSE symbols, any case, with spaces around
    ("RELIANCE", "RELIANCE.NS"), ("reliance", "RELIANCE.NS"), ("  tcs ", "TCS.NS"),
    ("itc", "ITC.NS"), ("wipro", "WIPRO.NS"),
    # NSE symbols containing - and &
    ("bajaj-auto", "BAJAJ-AUTO.NS"), ("M&M", "M&M.NS"),
    # company names: exact, with legal suffix, prefix, multi-word
    ("infosys", "INFY.NS"), ("Infosys Ltd", "INFY.NS"), ("Infosys Limited", "INFY.NS"),
    ("state bank", "SBIN.NS"), ("hdfc bank", "HDFCBANK.NS"), ("tata consultancy", "TCS.NS"),
    # fuzzy (typo)
    ("relaince industries", "RELIANCE.NS"),
    # renamed / demerged
    ("tatamotors", "TMPV.NS"), ("Tata Motors", "TMPV.NS"), ("zomato", "ETERNAL.NS"),
    # indices
    ("nifty", "^NSEI"), ("NIFTY 50", "^NSEI"), ("nifty50", "^NSEI"), ("sensex", "^BSESN"),
    ("banknifty", "^NSEBANK"), ("^NSEI", "^NSEI"),
    # explicit suffix is kept (BSE stays BSE)
    ("INFY.BO", "INFY.BO"), ("reliance.bo", "RELIANCE.BO"), ("RELIANCE.NS", "RELIANCE.NS"),
    # US passthrough
    ("AAPL", "AAPL"), ("msft", "MSFT"), ("BRK-B", "BRK-B"), ("^GSPC", "^GSPC"), ("GC=F", "GC=F"),
    # unknown symbols are kept as typed (Yahoo decides)
    ("ZZZZNOTREAL", "ZZZZNOTREAL"),
])
def test_normalize_ticker(raw, expected):
    assert india.normalize_ticker(raw) == expected


def test_normalize_empty_raises():
    with pytest.raises(ValueError):
        india.normalize_ticker("   ")


def test_is_indian_and_exchange():
    assert india.is_indian("TCS.NS") and india.is_indian("INFY.BO") and india.is_indian("^NSEI")
    assert india.is_indian("X", currency="INR")
    assert not india.is_indian("AAPL") and not india.is_indian("^GSPC")
    assert india.exchange_of("TCS.NS") == "NSE" and india.exchange_of("AAPL") == "US"


def test_benchmark_choice():
    assert benchmark_for("TCS.NS", "INR") == ("^NSEI", "NIFTY 50")
    assert benchmark_for("AAPL", "USD") == ("^GSPC", "S&P 500")


def test_stock_name_and_no_data_message():
    assert india.stock_name("RELIANCE.NS") == "Reliance Industries"
    assert india.stock_name("^NSEI") == "NIFTY 50"
    assert india.stock_name("20MICRONS.NS") == "20 Microns Limited"
    assert india.stock_name("AAPL") is None
    assert "listed on NSE" in india.no_data_message("INFY.NS")
    assert "No price data found for 'ZZZZ'" in india.no_data_message("ZZZZ")


# ------------------------------------------------------------------ NSE list + search
def test_nse_list_loaded():
    rows = india.nse_equities()
    assert len(rows) > 2000
    assert set(rows[0]) >= {"symbol", "name", "series", "isin", "listing_date"}
    assert india.is_nse_listed("RELIANCE") and india.is_nse_listed("tcs.ns")
    assert not india.is_nse_listed("AAPL")


def test_popular_list():
    assert len(india.POPULAR_STOCKS) == 20
    syms = [s["symbol"] for s in india.POPULAR_STOCKS]
    assert syms[0] == "RELIANCE.NS" and "TMPV.NS" in syms and "TATAMOTORS.NS" not in syms
    assert all(s.endswith(".NS") and india.is_nse_listed(s) for s in syms)
    assert [i["symbol"] for i in india.INDICES] == ["^NSEI", "^BSESN", "^NSEBANK"]


def test_search_by_name_prefix():
    res = india.search_nse("infos")
    assert res[0] == {"symbol": "INFY.NS", "nse_symbol": "INFY", "name": "Infosys Limited",
                      "isin": "INE009A01021", "series": "EQ"}


def test_search_by_symbol_exact_first():
    assert india.search_nse("TCS")[0]["symbol"] == "TCS.NS"
    assert india.search_nse("reliance")[0]["symbol"] == "RELIANCE.NS"


def test_search_multiword_and_limit():
    res = india.search_nse("state bank", limit=3)
    assert len(res) <= 3 and res[0]["symbol"] == "SBIN.NS"
    assert len(india.search_nse("tata", limit=5)) == 5
    assert all(r["name"].lower().startswith("tata") or r["nse_symbol"].startswith("TATA")
               for r in india.search_nse("tata", limit=5))


def test_search_empty_and_no_match():
    assert india.search_nse("") == [] and india.search_nse("   ") == []
    assert india.search_nse("qqqqxxzz") == []


# ------------------------------------------------------------------ formatting
@pytest.mark.parametrize("x,expected", [
    (0, "₹0.00"), (999, "₹999.00"), (1000, "₹1,000.00"), (100000, "₹1,00,000.00"),
    (1234567.8, "₹12,34,567.80"), (123456789, "₹12,34,56,789.00"), (-1500.5, "-₹1,500.50"),
    (None, "n/a"),
])
def test_format_inr(x, expected):
    assert india.format_inr(x) == expected


def test_format_inr_no_decimals():
    assert india.format_inr(1234567.8, decimals=0) == "₹12,34,568"


@pytest.mark.parametrize("x,expected", [
    (1.72e13, "₹17.2 lakh crore"), (9.5e10, "₹9,500 crore"), (1e7, "₹1 crore"),
    (450000, "₹4.5 lakh"), (5000, "₹5,000.00"), (-2e7, "-₹2 crore"), (None, "n/a"),
])
def test_format_inr_compact(x, expected):
    assert india.format_inr_compact(x) == expected


def test_format_money_and_change():
    assert india.format_money(1452.3, "INR") == "₹1,452.30"
    assert india.format_money(1.72e13, "INR", compact=True) == "₹17.2 lakh crore"
    assert india.format_money(1234.5, "USD") == "$1,234.50"
    assert india.format_money(2.5e12, "USD", compact=True) == "$2.50T"
    assert india.format_money(-3.2, "USD") == "-$3.20"
    assert india.format_money(10, "EUR") == "10.00 EUR"
    assert india.format_money(None, "INR") == "n/a"
    assert india.format_change(5.5, 0.38, "INR") == "+₹5.50 (+0.38%)"
    assert india.format_change(-5.5, -0.38, "INR") == "-₹5.50 (-0.38%)"
    assert india.format_change(None, 1.0, "INR") == "n/a"


def test_fmt_ist():
    assert india.fmt_ist("2026-10-23T15:30:00+05:30") == "23 Oct 2026, 15:30 IST"
    assert india.fmt_ist("2026-10-23T10:00:00+00:00") == "23 Oct 2026, 15:30 IST"
    assert india.fmt_ist(None) == "n/a"


# ------------------------------------------------------------------ market hours (fixed clock)
def ist(*a):
    return datetime(*a, tzinfo=IST)


def test_market_open_midday():
    s = india.market_status(ist(2026, 10, 23, 11, 0))  # Friday
    assert s["exchange"] == "NSE" and s["is_open"] is True
    assert s["now_ist"] == "2026-10-23T11:00:00+05:30"
    assert s["next_close_ist"] == "2026-10-23T15:30:00+05:30"
    assert s["next_open_ist"] == "2026-10-26T09:15:00+05:30"  # Monday
    assert "holidays" in s["note"]


def test_market_before_open_and_boundaries():
    s = india.market_status(ist(2026, 10, 22, 8, 0))  # Thursday morning
    assert not s["is_open"] and s["next_open_ist"] == "2026-10-22T09:15:00+05:30"
    assert india.market_status(ist(2026, 10, 22, 9, 15))["is_open"]
    assert not india.market_status(ist(2026, 10, 22, 15, 30))["is_open"]


def test_market_closed_evening_and_weekend():
    s = india.market_status(ist(2026, 10, 23, 19, 0))  # Friday evening
    assert not s["is_open"]
    assert s["next_open_ist"] == "2026-10-26T09:15:00+05:30"
    assert s["next_close_ist"] == "2026-10-26T15:30:00+05:30"
    s = india.market_status(ist(2026, 10, 25, 12, 0))  # Sunday
    assert not s["is_open"] and s["next_open_ist"] == "2026-10-26T09:15:00+05:30"


def test_us_market_hours_in_ist():
    # 20:00 IST = 10:30 New York (EDT) on a Thursday: open
    s = india.market_status(ist(2026, 10, 22, 20, 0), exchange="US")
    assert s["is_open"] and s["next_close_ist"] == "2026-10-23T01:30:00+05:30"


def test_last_completed_session():
    assert india.last_completed_session(now=ist(2026, 10, 23, 16, 0)) == date(2026, 10, 23)
    assert india.last_completed_session(now=ist(2026, 10, 23, 12, 0)) == date(2026, 10, 22)
    assert india.last_completed_session(now=ist(2026, 10, 26, 8, 0)) == date(2026, 10, 23)


def test_cache_is_stale(monkeypatch):
    now_ts = ist(2026, 10, 23, 11, 0).timestamp()
    monkeypatch.setattr(india._time, "time", lambda: now_ts)
    open_now = ist(2026, 10, 23, 11, 0)
    # market open: refresh after 5 minutes
    assert not india.cache_is_stale("TCS.NS", date(2026, 10, 23), now_ts - 60, open_now)
    assert india.cache_is_stale("TCS.NS", date(2026, 10, 23), now_ts - 600, open_now)
    # market closed (Saturday): fresh if it has Friday's bar, stale if older (rate-limited to 30 min)
    sat = ist(2026, 10, 24, 12, 0)
    assert not india.cache_is_stale("TCS.NS", date(2026, 10, 23), now_ts - 7200, sat)
    assert india.cache_is_stale("TCS.NS", date(2026, 10, 22), now_ts - 7200, sat)
    assert not india.cache_is_stale("TCS.NS", date(2026, 10, 22), now_ts - 60, sat)


def test_data_as_of():
    closed = india.data_as_of("TCS.NS", date(2026, 10, 23), 0, ist(2026, 10, 24, 12, 0))
    assert closed["as_of_ist"] == "2026-10-23T15:30:00+05:30" and not closed["live_bar"]
    fetched = ist(2026, 10, 23, 11, 2).timestamp()
    live = india.data_as_of("TCS.NS", date(2026, 10, 23), fetched, ist(2026, 10, 23, 11, 5))
    assert live["live_bar"] and live["market_open"] and live["as_of_ist"] == "2026-10-23T11:02:00+05:30"
    us = india.data_as_of("AAPL", date(2026, 10, 23), 0, ist(2026, 10, 25, 12, 0))
    assert us["as_of_ist"] == "2026-10-24T01:30:00+05:30"  # 16:00 New York close


def test_intraday_rejects_bad_interval():
    with pytest.raises(ValueError):
        india.intraday("TCS.NS", "15m")


# ------------------------------------------------------------------ benchmark maths
def series(values, start="2024-01-01"):
    return pd.Series(np.asarray(values, dtype=float), index=pd.bdate_range(start, periods=len(values)))


def test_benchmark_stats_returns_and_beta():
    rng = np.random.default_rng(0)
    idx_ret = rng.normal(0.0005, 0.01, 400)
    stock_ret = 1.5 * idx_ret + rng.normal(0, 0.002, 400)  # beta ~1.5 by construction
    index = series(100 * np.cumprod(1 + idx_ret))
    stock = series(50 * np.cumprod(1 + stock_ret))
    b = benchmark_stats(stock, index)
    assert b["beta"] == pytest.approx(1.5, abs=0.05)
    assert b["stock_return_1m"] == pytest.approx(stock.iloc[-1] / stock.iloc[-22] - 1)
    assert b["index_return_1y"] == pytest.approx(index.iloc[-1] / index.iloc[-253] - 1)
    rs = (1 + b["stock_return_1y"]) / (1 + b["index_return_1y"]) - 1
    assert b["relative_strength_1y"] == pytest.approx(rs)


def test_benchmark_stats_aligns_dates_and_handles_short_history():
    stock = series(np.linspace(100, 110, 40))
    index = series(np.linspace(1000, 1050, 40))
    b = benchmark_stats(stock, index)
    assert b["beta"] is None  # under 60 overlapping days
    assert b["stock_return_1y"] is None and b["relative_strength_1y"] is None
    assert b["stock_return_1m"] == pytest.approx(stock.iloc[-1] / stock.iloc[-22] - 1)
    # different holidays: only common days are used
    idx2 = index.drop(index.index[[5, 10, 15]])
    assert benchmark_stats(stock, idx2)["stock_return_1m"] is not None
