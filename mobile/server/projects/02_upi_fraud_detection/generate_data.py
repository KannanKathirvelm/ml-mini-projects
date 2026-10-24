"""Generate a synthetic UPI transactions dataset (~2% fraud).

Fraud is drawn from three common UPI scam patterns:
  1. collect_scam  - fake "refund"/"cashback" collect request from a new, young payee VPA
  2. account_takeover - SIM swap / new device, night-time, high amount, many transfers fast
  3. fake_qr       - scanning a fraudulent QR code of a recently created, already-reported merchant
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

BANKS = ["okaxis", "oksbi", "okhdfcbank", "okicici", "ybl", "paytm", "ibl"]
NORMAL_NAMES = ["rahul", "priya", "amit", "sneha", "vijay", "anita", "kiran", "deepa",
                "suresh", "lakshmi", "arjun", "meena"]
MERCHANTS = ["bigbazaar", "swiggy", "zomato", "irctc", "jiomart", "dmart", "starbucks",
             "chaipoint", "medplus", "reliancefresh"]
SCAM_HANDLES = ["refund.helpdesk", "kyc.update", "cashback.reward", "support.care",
                "lottery.winner", "bank.verify", "prize.claim"]

NORMAL_REMARKS = ["dinner", "rent", "groceries", "petrol", "movie tickets", "", "", "",
                  "electricity bill", "split bill", "gift", "fees", "chai", "auto fare",
                  "refund for tickets", "cashback share", "pending dues"]
SCAM_REMARKS = ["refund processing", "kyc update fee", "cashback reward", "lottery prize claim",
                "account verification", "electricity bill pending urgent", "job registration fee"]


def _vpa(rng, n, kind):
    bank = rng.choice(BANKS, n)
    if kind == "person":
        base = rng.choice(NORMAL_NAMES, n)
        return [f"{rng.integers(6 * 10**9, 10**10)}@{k}" if rng.random() < 0.35
                else f"{b}{rng.integers(1, 99)}@{k}" for b, k in zip(base, bank)]
    if kind == "merchant":
        return [f"{m}@{k}" for m, k in zip(rng.choice(MERCHANTS, n), bank)]
    # scam VPAs: official-sounding handle, a phone number, or a normal-looking mule account
    out = []
    for k in bank:
        r = rng.random()
        if r < 0.35:
            out.append(f"{rng.choice(SCAM_HANDLES)}{rng.integers(10, 999)}@{k}")
        elif r < 0.70:
            out.append(f"{rng.integers(6 * 10**9, 10**10)}@{k}")
        else:
            out.append(f"{rng.choice(NORMAL_NAMES)}{rng.integers(1, 99)}@{k}")
    return out


def _legit(n, rng):
    p2m = rng.random(n) < 0.55
    mode = np.where(p2m, np.where(rng.random(n) < 0.7, "qr_scan", "pay"),
                    np.where(rng.random(n) < 0.08, "collect_request", "pay"))
    payee = np.where(p2m, _vpa(rng, n, "merchant"), _vpa(rng, n, "person"))
    return pd.DataFrame({
        "payee_vpa": payee,
        "amount": rng.lognormal(5.5, 1.1, n).round(2),
        "hour": np.where(rng.random(n) < 0.06, rng.integers(0, 6, n),
                         np.clip(rng.normal(14, 4.5, n).round(), 0, 23)).astype(int),
        "txn_type": np.where(p2m, "P2M", "P2P"),
        "mode": mode,
        "is_new_payee": (rng.random(n) < 0.15).astype(int),
        "payee_account_age_days": np.where(rng.random(n) < 0.06, rng.integers(1, 60, n), rng.integers(60, 3000, n)),
        "payee_fraud_reports": rng.choice([0] * 17 + [1, 1, 2], n),
        "device_changed_48h": (rng.random(n) < 0.03).astype(int),
        "sim_changed_48h": (rng.random(n) < 0.01).astype(int),
        "failed_pin_attempts_24h": rng.choice([0, 0, 0, 0, 0, 0, 1], n),
        "txns_last_1h": rng.poisson(0.6, n),
        "amount_to_avg_ratio": rng.lognormal(0, 0.7, n).round(3),
        "remark": rng.choice(NORMAL_REMARKS + SCAM_REMARKS[:1], n,
                             p=[0.98 / len(NORMAL_REMARKS)] * len(NORMAL_REMARKS) + [0.02]),
        "fraud_type": "none",
        "is_fraud": 0,
    })


def _fraud(n, rng):
    kinds = rng.choice(["collect_scam", "account_takeover", "fake_qr"], n, p=[0.45, 0.30, 0.25])
    rows = []
    for kind in kinds:
        r = {
            "payee_vpa": _vpa(rng, 1, "scam")[0],
            "amount": float(rng.lognormal(7.0, 1.1)),
            "hour": int(rng.integers(0, 24)),
            "txn_type": "P2P",
            "mode": "pay",
            "is_new_payee": int(rng.random() < 0.75),
            "payee_account_age_days": int(rng.integers(1, 400)),
            "payee_fraud_reports": int(rng.poisson(0.8)),
            "device_changed_48h": int(rng.random() < 0.08),
            "sim_changed_48h": int(rng.random() < 0.03),
            "failed_pin_attempts_24h": int(rng.choice([0, 0, 1, 2])),
            "txns_last_1h": int(rng.poisson(1.5)),
            "amount_to_avg_ratio": float(rng.lognormal(0.9, 0.8)),
            "remark": rng.choice(SCAM_REMARKS) if rng.random() < 0.5 else rng.choice(NORMAL_REMARKS),
            "fraud_type": kind,
            "is_fraud": 1,
        }
        if kind == "collect_scam":
            r["mode"] = "collect_request"
            r["amount"] = float(rng.lognormal(7.0, 1.1))
        elif kind == "account_takeover":
            # attacker controls a real-looking account, so payee signals are weaker
            r.update(device_changed_48h=int(rng.random() < 0.85), sim_changed_48h=int(rng.random() < 0.6),
                     hour=int(rng.integers(0, 6)) if rng.random() < 0.7 else int(rng.integers(0, 24)),
                     txns_last_1h=int(rng.poisson(5)), failed_pin_attempts_24h=int(rng.choice([0, 1, 2, 3, 4])),
                     amount=float(rng.lognormal(8.5, 1.0)), payee_vpa=_vpa(rng, 1, "person")[0],
                     payee_account_age_days=int(rng.integers(5, 400)), remark=rng.choice(NORMAL_REMARKS))
        else:  # fake_qr
            r.update(mode="qr_scan", txn_type="P2M", amount=float(rng.lognormal(6.5, 1.0)))
        rows.append(r)
    df = pd.DataFrame(rows)
    df["amount"] = df["amount"].round(2)
    df["amount_to_avg_ratio"] = df["amount_to_avg_ratio"].round(3)
    return df


def generate(n_rows=100_000, fraud_rate=0.02, seed=7):
    rng = np.random.default_rng(seed)
    n_fraud = int(n_rows * fraud_rate)
    df = pd.concat([_legit(n_rows - n_fraud, rng), _fraud(n_fraud, rng)])
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    df.insert(0, "txn_id", [f"UPI{100000000 + i}" for i in range(len(df))])
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--fraud-rate", type=float, default=0.02)
    args = parser.parse_args()

    out = Path(__file__).parent / "data" / "upi_transactions.csv"
    out.parent.mkdir(exist_ok=True)
    df = generate(args.rows, args.fraud_rate)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df):,} rows ({df.is_fraud.sum():,} fraud) to {out}")
    print(df[df.is_fraud == 1].fraud_type.value_counts().to_string())
