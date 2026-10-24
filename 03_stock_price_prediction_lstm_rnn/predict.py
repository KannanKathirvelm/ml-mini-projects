"""Forecast the next N trading days with trained models.

    python predict.py --ticker AAPL --days 10
"""
import argparse
import json
from pathlib import Path

import pandas as pd
import torch

from data import load_prices
from model import PriceRNN, forecast
from train import CELLS, MODEL_DIR, safe_name


def load_models(ticker):
    safe = safe_name(ticker)
    meta_path = MODEL_DIR / f"{safe}_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"No trained models for {ticker}. Run `python train.py --ticker {ticker}`.")
    meta = json.loads(meta_path.read_text())
    models = {}
    for cell in CELLS:
        m = PriceRNN(cell)
        m.load_state_dict(torch.load(MODEL_DIR / f"{safe}_{cell}.pt", weights_only=True))
        models[cell] = m.eval()
    return meta, models


def future_forecast(ticker, days, refresh=False):
    """DataFrame indexed by future business days with one column per model."""
    meta, models = load_models(ticker)
    prices = load_prices(ticker, refresh=refresh)
    dates = pd.bdate_range(prices.index[-1] + pd.Timedelta(days=1), periods=days)
    out = {cell: forecast(m, prices.values, days, meta["scale"], meta["window"]) for cell, m in models.items()}
    return prices, pd.DataFrame(out, index=dates).round(2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", default="AAPL")
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--refresh", action="store_true", help="re-download latest prices first")
    a = p.parse_args()

    prices, fc = future_forecast(a.ticker, a.days, a.refresh)
    print(f"{a.ticker} last close {prices.iloc[-1]:.2f} on {prices.index[-1].date()}\n")
    print(fc.rename(columns=str.upper).to_string())
    print("\nNote: errors compound with each day of a recursive forecast. Educational use only.")


if __name__ == "__main__":
    main()
