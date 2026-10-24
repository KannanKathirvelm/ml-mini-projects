"""Feature engineering and human-readable risk signals for UPI transactions.

The raw payee VPA and remark are text, so we turn them into simple flags the
model can use. The same helpers produce the "why was this flagged" reasons.
"""
import re

import numpy as np
import pandas as pd

SCAM_WORDS = ["refund", "kyc", "cashback", "lottery", "prize", "reward", "verify",
              "verification", "urgent", "pending", "registration fee", "claim"]
SUSPICIOUS_HANDLE_WORDS = ["refund", "kyc", "support", "helpdesk", "care", "reward",
                           "cashback", "lottery", "prize", "verify", "winner"]

CATEGORICAL = ["txn_type", "mode"]
NUMERIC = ["amount_log", "hour", "is_night", "is_new_payee", "payee_account_age_days",
           "payee_fraud_reports", "device_changed_48h", "sim_changed_48h",
           "failed_pin_attempts_24h", "txns_last_1h", "amount_to_avg_ratio",
           "remark_scam_words", "vpa_suspicious_words", "vpa_mostly_digits"]
FEATURES = CATEGORICAL + NUMERIC
RAW_COLUMNS = ["payee_vpa", "amount", "hour", "txn_type", "mode", "is_new_payee",
               "payee_account_age_days", "payee_fraud_reports", "device_changed_48h",
               "sim_changed_48h", "failed_pin_attempts_24h", "txns_last_1h",
               "amount_to_avg_ratio", "remark"]


def _count_words(text, words):
    text = str(text).lower()
    return sum(w in text for w in words)


def _mostly_digits(vpa):
    handle = str(vpa).split("@")[0]
    return int(len(re.sub(r"\D", "", handle)) >= 8)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["remark"] = out["remark"].fillna("")
    out["amount_log"] = np.log1p(out["amount"])
    out["is_night"] = out["hour"].between(0, 5).astype(int)
    out["remark_scam_words"] = out["remark"].map(lambda t: _count_words(t, SCAM_WORDS))
    out["vpa_suspicious_words"] = out["payee_vpa"].map(
        lambda v: _count_words(str(v).split("@")[0], SUSPICIOUS_HANDLE_WORDS))
    out["vpa_mostly_digits"] = out["payee_vpa"].map(_mostly_digits)
    return out


def risk_signals(row) -> list[str]:
    """Plain-English reasons a single transaction looks risky."""
    reasons = []
    if row["mode"] == "collect_request":
        reasons.append("Collect request: approving it sends money OUT. Real refunds never need your PIN")
    if row["remark_scam_words"]:
        reasons.append(f"Remark '{row['remark']}' uses common scam words")
    if row["vpa_suspicious_words"]:
        reasons.append(f"Payee VPA '{row['payee_vpa']}' imitates an official/support handle")
    # phone-number VPAs are normal, so only call it out for a new, young payee
    if row["vpa_mostly_digits"] and row["is_new_payee"] and row["payee_account_age_days"] < 90:
        reasons.append("Unknown payee identified only by a number VPA")
    if row["is_new_payee"] and row["payee_account_age_days"] < 30:
        reasons.append(f"First payment to an account only {int(row['payee_account_age_days'])} days old")
    if row["payee_fraud_reports"] > 0:
        reasons.append(f"Payee has {int(row['payee_fraud_reports'])} prior fraud report(s)")
    if row["sim_changed_48h"]:
        reasons.append("SIM changed in the last 48h (possible SIM swap)")
    if row["device_changed_48h"]:
        reasons.append("UPI app logged in on a new device in the last 48h")
    if row["failed_pin_attempts_24h"] >= 2:
        reasons.append(f"{int(row['failed_pin_attempts_24h'])} failed PIN attempts in 24h")
    if row["txns_last_1h"] >= 4:
        reasons.append(f"{int(row['txns_last_1h'])} transactions in the last hour")
    if row["amount_to_avg_ratio"] >= 4:
        reasons.append(f"Amount is {row['amount_to_avg_ratio']:.1f}x the user's average")
    if row["is_night"]:
        reasons.append(f"Made at night ({int(row['hour']):02d}:00)")
    return reasons
