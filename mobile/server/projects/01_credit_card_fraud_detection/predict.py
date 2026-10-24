"""Score transactions from the command line.

Single transaction:
    python predict.py --amount 950 --hour 2 --distance-home 400 --category electronics --online 1

Batch CSV (same columns as data/transactions.csv, is_fraud optional):
    python predict.py --csv my_transactions.csv
"""
import argparse
from pathlib import Path

import joblib
import pandas as pd

MODEL_PATH = Path(__file__).parent / "models" / "fraud_model.joblib"


def load():
    if not MODEL_PATH.exists():
        raise SystemExit("Model not found. Run `python train.py` first.")
    return joblib.load(MODEL_PATH)


def score(df, bundle):
    proba = bundle["model"].predict_proba(df[bundle["features"]])[:, 1]
    out = df.copy()
    out["fraud_probability"] = proba.round(4)
    out["flagged"] = (proba >= bundle["threshold"]).astype(int)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv")
    p.add_argument("--amount", type=float, default=50.0)
    p.add_argument("--hour", type=int, default=14)
    p.add_argument("--distance-home", type=float, default=5.0)
    p.add_argument("--distance-last", type=float, default=3.0)
    p.add_argument("--ratio-median", type=float, default=1.0)
    p.add_argument("--online", type=int, default=0)
    p.add_argument("--chip", type=int, default=1)
    p.add_argument("--pin", type=int, default=1)
    p.add_argument("--txn-24h", type=int, default=2)
    p.add_argument("--category", default="grocery")
    a = p.parse_args()

    bundle = load()
    if a.csv:
        result = score(pd.read_csv(a.csv), bundle)
        out = Path(a.csv).with_name(Path(a.csv).stem + "_scored.csv")
        result.to_csv(out, index=False)
        print(f"Flagged {result.flagged.sum():,} of {len(result):,} transactions -> {out}")
        return

    row = pd.DataFrame([{
        "amount": a.amount, "hour": a.hour, "distance_from_home_km": a.distance_home,
        "distance_from_last_txn_km": a.distance_last, "ratio_to_median_amount": a.ratio_median,
        "online_order": a.online, "used_chip": a.chip, "used_pin": a.pin,
        "txn_count_last_24h": a.txn_24h, "merchant_category": a.category,
    }])
    r = score(row, bundle).iloc[0]
    verdict = "FRAUD" if r.flagged else "LEGIT"
    print(f"Fraud probability: {r.fraud_probability:.2%}  ->  {verdict} (threshold {bundle['threshold']:.2%})")


if __name__ == "__main__":
    main()
