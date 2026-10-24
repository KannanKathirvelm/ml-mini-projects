"""Generate a synthetic credit card transactions dataset with ~1.5% fraud.

Fraudulent transactions are drawn from shifted distributions (larger amounts,
late-night hours, far from home, fewer chip/PIN uses) that overlap with normal
ones, so the model has to learn patterns rather than a single rule.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

CATEGORIES = ["grocery", "gas", "restaurant", "electronics", "travel", "online_retail"]
LEGIT_CAT_P = [0.30, 0.20, 0.22, 0.08, 0.05, 0.15]
FRAUD_CAT_P = [0.06, 0.08, 0.06, 0.32, 0.18, 0.30]


def _make(n, fraud, rng):
    if fraud:
        amount = rng.lognormal(mean=5.2, sigma=1.0, size=n)
        hour = np.where(rng.random(n) < 0.55, rng.integers(0, 6, n), rng.integers(0, 24, n))
        dist_home = rng.lognormal(mean=4.0, sigma=1.3, size=n)
        dist_last = rng.lognormal(mean=3.5, sigma=1.4, size=n)
        ratio_median = rng.lognormal(mean=1.2, sigma=0.8, size=n)
        online = rng.random(n) < 0.70
        chip = rng.random(n) < 0.25
        pin = rng.random(n) < 0.10
        txn_24h = rng.poisson(6, n)
        cat = rng.choice(CATEGORIES, n, p=FRAUD_CAT_P)
    else:
        amount = rng.lognormal(mean=3.6, sigma=1.0, size=n)
        hour = np.clip(rng.normal(14, 4.5, n).round(), 0, 23).astype(int)
        dist_home = rng.lognormal(mean=2.0, sigma=1.1, size=n)
        dist_last = rng.lognormal(mean=1.5, sigma=1.2, size=n)
        ratio_median = rng.lognormal(mean=0.0, sigma=0.6, size=n)
        online = rng.random(n) < 0.30
        chip = rng.random(n) < 0.65
        pin = rng.random(n) < 0.45
        txn_24h = rng.poisson(3, n)
        cat = rng.choice(CATEGORIES, n, p=LEGIT_CAT_P)

    return pd.DataFrame({
        "amount": amount.round(2),
        "hour": hour,
        "distance_from_home_km": dist_home.round(2),
        "distance_from_last_txn_km": dist_last.round(2),
        "ratio_to_median_amount": ratio_median.round(3),
        "online_order": online.astype(int),
        "used_chip": chip.astype(int),
        "used_pin": pin.astype(int),
        "txn_count_last_24h": txn_24h,
        "merchant_category": cat,
        "is_fraud": int(fraud),
    })


def generate(n_rows=100_000, fraud_rate=0.015, seed=42):
    rng = np.random.default_rng(seed)
    n_fraud = int(n_rows * fraud_rate)
    df = pd.concat([_make(n_rows - n_fraud, False, rng), _make(n_fraud, True, rng)])
    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--fraud-rate", type=float, default=0.015)
    args = parser.parse_args()

    out = Path(__file__).parent / "data" / "transactions.csv"
    out.parent.mkdir(exist_ok=True)
    df = generate(args.rows, args.fraud_rate)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df):,} rows ({df.is_fraud.sum():,} fraud) to {out}")
