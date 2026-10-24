"""Streamlit dashboard: run with `streamlit run app.py`."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from generate_data import CATEGORIES
from predict import MODEL_PATH, load, score

st.set_page_config(page_title="Credit Card Fraud Detection", page_icon="💳", layout="wide")
st.title("💳 Credit Card Fraud Detection")

if not MODEL_PATH.exists():
    st.error("Model not found. Run `python train.py` first.")
    st.stop()

bundle = load()
metrics = json.loads((MODEL_PATH.parent / "metrics.json").read_text())

tab_single, tab_batch, tab_model = st.tabs(["Check a transaction", "Batch CSV", "Model performance"])

with tab_single:
    c1, c2, c3 = st.columns(3)
    with c1:
        amount = st.number_input("Amount ($)", 0.0, 50_000.0, 45.0, step=5.0)
        hour = st.slider("Hour of day", 0, 23, 14)
        category = st.selectbox("Merchant category", CATEGORIES)
    with c2:
        dist_home = st.number_input("Distance from home (km)", 0.0, 20_000.0, 5.0)
        dist_last = st.number_input("Distance from last transaction (km)", 0.0, 20_000.0, 3.0)
        ratio = st.number_input("Amount / customer's median amount", 0.0, 100.0, 1.0, step=0.1)
    with c3:
        online = st.checkbox("Online order")
        chip = st.checkbox("Chip used", value=True)
        pin = st.checkbox("PIN used", value=True)
        txn_24h = st.number_input("Transactions in last 24h", 0, 100, 2)

    row = pd.DataFrame([{
        "amount": amount, "hour": hour, "distance_from_home_km": dist_home,
        "distance_from_last_txn_km": dist_last, "ratio_to_median_amount": ratio,
        "online_order": int(online), "used_chip": int(chip), "used_pin": int(pin),
        "txn_count_last_24h": txn_24h, "merchant_category": category,
    }])
    r = score(row, bundle).iloc[0]
    st.metric("Fraud probability", f"{r.fraud_probability:.1%}")
    st.progress(float(r.fraud_probability))
    if r.flagged:
        st.error(f"🚨 Flagged as likely FRAUD (threshold {bundle['threshold']:.1%})")
    else:
        st.success(f"✅ Looks legitimate (threshold {bundle['threshold']:.1%})")

with tab_batch:
    st.write("Upload a CSV with the same columns as `data/transactions.csv`.")
    file = st.file_uploader("Transactions CSV", type="csv")
    if file:
        result = score(pd.read_csv(file), bundle).sort_values("fraud_probability", ascending=False)
        st.write(f"Flagged **{result.flagged.sum():,}** of {len(result):,} transactions")
        st.dataframe(result, use_container_width=True)
        st.download_button("Download scored CSV", result.to_csv(index=False), "scored.csv")

with tab_model:
    t = metrics["test"]
    st.subheader(f"Best model: {metrics['best_model']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fraud precision", f"{t['fraud_precision']:.1%}")
    c2.metric("Fraud recall", f"{t['fraud_recall']:.1%}")
    c3.metric("PR-AUC", f"{t['average_precision']:.3f}")
    c4.metric("ROC-AUC", f"{t['roc_auc']:.3f}")
    (tn, fp), (fn, tp) = t["confusion_matrix"]
    st.write("Confusion matrix (test set)")
    st.table(pd.DataFrame([[tn, fp], [fn, tp]], index=["Actual legit", "Actual fraud"],
                          columns=["Predicted legit", "Predicted fraud"]))
    st.write("Validation comparison")
    st.table(pd.DataFrame(metrics["validation"]).T)
