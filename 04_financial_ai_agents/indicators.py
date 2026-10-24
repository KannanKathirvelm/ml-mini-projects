"""Technical indicators computed by hand with pandas.

Doing the maths ourselves (instead of a TA library) keeps the dependency list
short and makes every number in the report traceable to a few lines of code.
Both the rule-based and the LLM Technical Analyst consume `compute_indicators`.
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI: exponential smoothing with alpha = 1/period."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def drawdown(close: pd.Series) -> pd.Series:
    """Fractional distance below the running peak (0 at a new high, negative below)."""
    return close / close.cummax() - 1


def add_indicator_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Price frame + SMA columns, used by the dashboard chart."""
    out = df.copy()
    for w in (20, 50, 200):
        out[f"SMA{w}"] = sma(out["Close"], w)
    return out


def _ret(close: pd.Series, days: int) -> float | None:
    return float(close.iloc[-1] / close.iloc[-days - 1] - 1) if len(close) > days else None


def _num(x) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def compute_indicators(df: pd.DataFrame) -> dict:
    """Snapshot of the latest technical state as plain floats (JSON-friendly)."""
    close = df["Close"]
    last_year = close.iloc[-TRADING_DAYS:]
    rets = close.pct_change().dropna()
    m = macd(close)
    return {
        "last_close": float(close.iloc[-1]),
        "last_date": close.index[-1].strftime("%Y-%m-%d"),
        "sma20": _num(sma(close, 20).iloc[-1]),
        "sma50": _num(sma(close, 50).iloc[-1]),
        "sma200": _num(sma(close, 200).iloc[-1]),
        "rsi14": float(rsi(close).iloc[-1]),
        "macd": float(m["macd"].iloc[-1]),
        "macd_signal": float(m["signal"].iloc[-1]),
        "macd_hist": float(m["hist"].iloc[-1]),
        "macd_hist_prev": float(m["hist"].iloc[-2]),
        "volatility_20d": float(rets.iloc[-20:].std() * np.sqrt(TRADING_DAYS)),
        "volatility_1y": float(rets.iloc[-TRADING_DAYS:].std() * np.sqrt(TRADING_DAYS)),
        "max_drawdown_1y": float(drawdown(last_year).min()),
        "drawdown_from_52w_high": float(close.iloc[-1] / last_year.max() - 1),
        "high_52w": float(last_year.max()),
        "low_52w": float(last_year.min()),
        "return_1m": _ret(close, 21),
        "return_3m": _ret(close, 63),
        "return_6m": _ret(close, 126),
        "return_1y": _ret(close, TRADING_DAYS),
    }


def benchmark_stats(stock: pd.Series, index: pd.Series) -> dict:
    """Stock vs index: returns over 1m/3m/1y, beta and relative strength.

    Beta is cov(stock, index) / var(index) on about one year of daily returns,
    using only days both traded (NSE and US holidays differ). Relative strength
    is (1 + stock 1y return) / (1 + index 1y return) - 1: > 0 means the stock
    beat the index over the year.
    """
    both = pd.concat([stock, index], axis=1, join="inner").dropna()
    both.columns = ["stock", "index"]
    out = {}
    for label, days in (("1m", 21), ("3m", 63), ("1y", TRADING_DAYS)):
        out[f"stock_return_{label}"] = _ret(both["stock"], days)
        out[f"index_return_{label}"] = _ret(both["index"], days)
    rets = both.pct_change().dropna().iloc[-TRADING_DAYS:]
    var = rets["index"].var()
    out["beta"] = float(rets["stock"].cov(rets["index"]) / var) if len(rets) > 60 and var > 0 else None
    s, i = out["stock_return_1y"], out["index_return_1y"]
    out["relative_strength_1y"] = (1 + s) / (1 + i) - 1 if s is not None and i is not None else None
    return out
