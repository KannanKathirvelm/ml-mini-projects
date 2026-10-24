"""Score UPI transactions from the command line.

Single transaction:
    python predict.py --vpa refund.helpdesk42@ybl --amount 4999 --mode collect_request --remark "refund processing" --new-payee 1 --payee-age 3

Batch CSV (same columns as data/upi_transactions.csv):
    python predict.py --csv my_upi.csv
"""
import argparse
from pathlib import Path

import joblib
import pandas as pd

from features import build_features, risk_signals

MODEL_PATH = Path(__file__).parent / "models" / "upi_fraud_model.joblib"


def load():
    if not MODEL_PATH.exists():
        raise SystemExit("Model not found. Run `python train.py` first.")
    return joblib.load(MODEL_PATH)


def risk_level(p, threshold):
    if p >= threshold:
        return "HIGH"
    return "MEDIUM" if p >= threshold / 3 else "LOW"


def score(raw: pd.DataFrame, bundle) -> pd.DataFrame:
    df = build_features(raw)
    proba = bundle["model"].predict_proba(df[bundle["features"]])[:, 1]
    out = raw.copy()
    out["fraud_probability"] = proba.round(4)
    out["risk_level"] = [risk_level(p, bundle["threshold"]) for p in proba]
    out["flagged"] = (proba >= bundle["threshold"]).astype(int)
    out["reasons"] = ["; ".join(risk_signals(r)) for _, r in df.iterrows()]
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv")
    p.add_argument("--vpa", default="rahul12@okaxis")
    p.add_argument("--amount", type=float, default=250.0)
    p.add_argument("--hour", type=int, default=14)
    p.add_argument("--txn-type", default="P2P", choices=["P2P", "P2M"])
    p.add_argument("--mode", default="pay", choices=["pay", "collect_request", "qr_scan"])
    p.add_argument("--new-payee", type=int, default=0)
    p.add_argument("--payee-age", type=int, default=500, help="payee account age in days")
    p.add_argument("--payee-reports", type=int, default=0)
    p.add_argument("--device-changed", type=int, default=0)
    p.add_argument("--sim-changed", type=int, default=0)
    p.add_argument("--failed-pins", type=int, default=0)
    p.add_argument("--txns-1h", type=int, default=0)
    p.add_argument("--avg-ratio", type=float, default=1.0)
    p.add_argument("--remark", default="")
    a = p.parse_args()

    bundle = load()
    if a.csv:
        result = score(pd.read_csv(a.csv), bundle)
        out = Path(a.csv).with_name(Path(a.csv).stem + "_scored.csv")
        result.to_csv(out, index=False)
        print(f"Flagged {result.flagged.sum():,} of {len(result):,} transactions -> {out}")
        return

    row = pd.DataFrame([{
        "payee_vpa": a.vpa, "amount": a.amount, "hour": a.hour, "txn_type": a.txn_type,
        "mode": a.mode, "is_new_payee": a.new_payee, "payee_account_age_days": a.payee_age,
        "payee_fraud_reports": a.payee_reports, "device_changed_48h": a.device_changed,
        "sim_changed_48h": a.sim_changed, "failed_pin_attempts_24h": a.failed_pins,
        "txns_last_1h": a.txns_1h, "amount_to_avg_ratio": a.avg_ratio, "remark": a.remark,
    }])
    r = score(row, bundle).iloc[0]
    print(f"Fraud probability: {r.fraud_probability:.2%}  ->  {r.risk_level} risk")
    for reason in filter(None, r.reasons.split("; ")):
        print(f"  - {reason}")


if __name__ == "__main__":
    main()
