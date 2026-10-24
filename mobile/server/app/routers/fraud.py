"""Projects 01 (credit card fraud) and 02 (UPI fraud)."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import loader

cc_router = APIRouter(prefix="/api/credit-card", tags=["credit-card"])
upi_router = APIRouter(prefix="/api/upi", tags=["upi"])


# ---------------------------------------------------------------- credit card
@lru_cache(maxsize=1)
def cc():
    ns = loader.get("credit-card", ["predict", "generate_data"])
    bundle = ns.predict.load()
    metrics = json.loads((ns.__root__ / "models" / "metrics.json").read_text())
    return ns, bundle, metrics


class CardTxn(BaseModel):
    amount: float = Field(ge=0)
    hour: int = Field(ge=0, le=23)
    distance_from_home_km: float = Field(ge=0)
    distance_from_last_txn_km: float = Field(ge=0)
    ratio_to_median_amount: float = Field(ge=0)
    online_order: int = Field(ge=0, le=1)
    used_chip: int = Field(ge=0, le=1)
    used_pin: int = Field(ge=0, le=1)
    txn_count_last_24h: int = Field(ge=0)
    merchant_category: str


def _summary(metrics: dict) -> dict:
    t = metrics["test"]
    return {
        "best_model": metrics["best_model"],
        "fraud_precision": round(t["fraud_precision"], 3),
        "fraud_recall": round(t["fraud_recall"], 3),
        "average_precision": round(t["average_precision"], 3),
        "roc_auc": round(t["roc_auc"], 3),
    }


@cc_router.get("/meta")
def cc_meta():
    ns, bundle, metrics = cc()
    return {"categories": list(ns.generate_data.CATEGORIES),
            "threshold": round(bundle["threshold"], 3),
            "metrics": _summary(metrics)}


@cc_router.post("/predict")
def cc_predict(txn: CardTxn):
    ns, bundle, _ = cc()
    if txn.merchant_category not in ns.generate_data.CATEGORIES:
        raise HTTPException(422, f"merchant_category must be one of {ns.generate_data.CATEGORIES}")
    r = ns.predict.score(pd.DataFrame([txn.model_dump()]), bundle).iloc[0]
    return {"fraud_probability": float(r.fraud_probability), "flagged": bool(r.flagged),
            "threshold": round(bundle["threshold"], 3)}


# ------------------------------------------------------------------------ UPI
# The same 4 examples as 02_upi_fraud_detection/app.py (EXAMPLES), in API field names.
UPI_EXAMPLES = [
    ("Normal: paying a friend", dict(
        payee_vpa="priya27@oksbi", amount=450.0, hour=20, txn_type="P2P", mode="pay",
        is_new_payee=0, payee_account_age_days=900, payee_fraud_reports=0, device_changed_48h=0,
        sim_changed_48h=0, failed_pin_attempts_24h=0, txns_last_1h=0, amount_to_avg_ratio=0.9,
        remark="dinner")),
    ("Scam: fake refund collect request", dict(
        payee_vpa="refund.helpdesk42@ybl", amount=4999.0, hour=11, txn_type="P2P",
        mode="collect_request", is_new_payee=1, payee_account_age_days=4, payee_fraud_reports=2,
        device_changed_48h=0, sim_changed_48h=0, failed_pin_attempts_24h=0, txns_last_1h=1,
        amount_to_avg_ratio=5.0, remark="refund processing")),
    ("Scam: SIM swap takeover", dict(
        payee_vpa="arjun44@okicici", amount=48000.0, hour=2, txn_type="P2P", mode="pay",
        is_new_payee=1, payee_account_age_days=120, payee_fraud_reports=0, device_changed_48h=1,
        sim_changed_48h=1, failed_pin_attempts_24h=3, txns_last_1h=6, amount_to_avg_ratio=12.0,
        remark="")),
    ("Scam: fake merchant QR", dict(
        payee_vpa="9876543210@paytm", amount=1500.0, hour=16, txn_type="P2M", mode="qr_scan",
        is_new_payee=1, payee_account_age_days=10, payee_fraud_reports=3, device_changed_48h=0,
        sim_changed_48h=0, failed_pin_attempts_24h=0, txns_last_1h=0, amount_to_avg_ratio=3.0,
        remark="")),
]


@lru_cache(maxsize=1)
def upi():
    ns = loader.get("upi", ["predict", "features"])
    bundle = ns.predict.load()
    metrics = json.loads((ns.__root__ / "models" / "metrics.json").read_text())
    return ns, bundle, metrics


class UpiTxn(BaseModel):
    payee_vpa: str = Field(min_length=1)
    amount: float = Field(ge=0)
    hour: int = Field(ge=0, le=23)
    txn_type: Literal["P2P", "P2M"]
    mode: Literal["pay", "collect_request", "qr_scan"]
    is_new_payee: int = Field(ge=0, le=1)
    payee_account_age_days: int = Field(ge=0)
    payee_fraud_reports: int = Field(ge=0)
    device_changed_48h: int = Field(ge=0, le=1)
    sim_changed_48h: int = Field(ge=0, le=1)
    failed_pin_attempts_24h: int = Field(ge=0)
    txns_last_1h: int = Field(ge=0)
    amount_to_avg_ratio: float = Field(ge=0)
    remark: str = ""


@upi_router.get("/meta")
def upi_meta():
    _, bundle, metrics = upi()
    m = _summary(metrics)
    m["recall_by_fraud_type"] = {k: round(v, 3) for k, v in
                                 metrics["test"].get("recall_by_fraud_type", {}).items()}
    return {"threshold": round(bundle["threshold"], 3), "metrics": m}


@upi_router.get("/examples")
def upi_examples():
    return [{"name": name, "input": inp} for name, inp in UPI_EXAMPLES]


@upi_router.post("/predict")
def upi_predict(txn: UpiTxn):
    ns, bundle, _ = upi()
    raw = pd.DataFrame([txn.model_dump()])
    r = ns.predict.score(raw, bundle).iloc[0]
    # reasons straight from features.risk_signals (score() joins them with "; ")
    reasons = ns.features.risk_signals(ns.features.build_features(raw).iloc[0])
    return {"fraud_probability": float(r.fraud_probability), "risk_level": r.risk_level,
            "flagged": bool(r.flagged), "threshold": round(bundle["threshold"], 3),
            "reasons": reasons}
