"""Download prices with yfinance and turn them into sliding-window sequences.

Why not feed raw prices? A stock that trends up spends its test period above
every price seen in training, and a model trained on scaled raw prices cannot
extrapolate there. So each window is expressed relative to its last day:

    x = log(price[t-k] / price[t])  for the last `window` days
    y = log(price[t+1] / price[t])  (tomorrow's log return)

This works at any price level. Inputs and targets are divided by the standard
deviation of training returns so values are around +-1. Splits are
chronological and the scale uses training data only (no leakage).
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", module="yfinance")  # pandas deprecation noise inside yfinance

DATA_DIR = Path(__file__).parent / "data"


def load_prices(ticker: str, start: str = "2015-01-01", refresh: bool = False) -> pd.Series:
    """Daily (split/dividend adjusted) closing prices, cached to data/<ticker>.csv."""
    DATA_DIR.mkdir(exist_ok=True)
    cache = DATA_DIR / f"{ticker.replace('^', '_')}.csv"
    if cache.exists() and not refresh:
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
    else:
        df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if df.empty:
            if cache.exists():
                print(f"Download failed, using cached {cache.name}")
                df = pd.read_csv(cache, index_col=0, parse_dates=True)
            else:
                raise ValueError(f"No data for '{ticker}'. Check the symbol (e.g. AAPL, RELIANCE.NS).")
        else:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df[["Open", "High", "Low", "Close", "Volume"]].to_csv(cache)
    return df["Close"].dropna().astype(float)


def window_input(log_prices: np.ndarray, scale: float) -> np.ndarray:
    """Model input for one window of log prices: relative to the last day, scaled."""
    return ((log_prices - log_prices[-1]) / scale).astype(np.float32)


def split_data(prices: pd.Series, window: int = 60, val_frac=0.1, test_frac=0.1):
    """Chronological train/val/test windows.

    Each split is (X, y, dates, prev_price) where prev_price is the close on
    the day before each target, needed to turn a predicted return into a price.
    """
    logp = np.log(prices.values)
    n = len(logp)
    n_test, n_val = int(n * test_frac), int(n * val_frac)
    train_end = n - n_test - n_val

    W = np.lib.stride_tricks.sliding_window_view(logp[:-1], window)  # W[i] = logp[i:i+window]
    last = W[:, -1]
    X_raw, y_raw = W - last[:, None], logp[window:] - last
    target_idx = np.arange(window, n)  # day predicted by window i

    tr = target_idx < train_end
    va = (target_idx >= train_end) & (target_idx < n - n_test)
    te = target_idx >= n - n_test
    scale = float(np.std(y_raw[tr]))
    X = (X_raw / scale)[..., None].astype(np.float32)
    y = (y_raw / scale).astype(np.float32)
    prev = prices.values[target_idx - 1]
    dates = prices.index[target_idx]

    split = lambda m: (X[m], y[m], dates[m], prev[m])
    return {"train": split(tr), "val": split(va), "test": split(te), "scale": scale}
