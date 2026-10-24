"""Streamlit dashboard: run with `streamlit run app.py`."""
import json

import pandas as pd
import streamlit as st

from predict import MODEL_PATH, load, score

st.set_page_config(page_title="UPI Fraud Detection", page_icon="📲", layout="wide")
st.title("📲 UPI Fraud Detection")

if not MODEL_PATH.exists():
    st.error("Model not found. Run `python train.py` first.")
    st.stop()

bundle = load()
metrics = json.loads((MODEL_PATH.parent / "metrics.json").read_text())

EXAMPLES = {
    "Normal: paying a friend": dict(vpa="priya27@oksbi", amount=450.0, hour=20, txn_type="P2P", mode="pay",
                                    new=False, age=900, reports=0, device=False, sim=False, pins=0,
                                    txns=0, ratio=0.9, remark="dinner"),
    "Scam: fake refund collect request": dict(vpa="refund.helpdesk42@ybl", amount=4999.0, hour=11, txn_type="P2P",
                                              mode="collect_request", new=True, age=4, reports=2, device=False,
                                              sim=False, pins=0, txns=1, ratio=5.0, remark="refund processing"),
    "Scam: SIM swap takeover": dict(vpa="arjun44@okicici", amount=48000.0, hour=2, txn_type="P2P", mode="pay",
                                    new=True, age=120, reports=0, device=True, sim=True, pins=3,
                                    txns=6, ratio=12.0, remark=""),
    "Scam: fake merchant QR": dict(vpa="9876543210@paytm", amount=1500.0, hour=16, txn_type="P2M",
                                   mode="qr_scan", new=True, age=10, reports=3, device=False, sim=False,
                                   pins=0, txns=0, ratio=3.0, remark=""),
}

tab_single, tab_batch, tab_model = st.tabs(["Check a transaction", "Batch CSV", "Model performance"])

with tab_single:
    ex = EXAMPLES[st.selectbox("Load an example", list(EXAMPLES))]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Payment**")
        vpa = st.text_input("Payee UPI ID (VPA)", ex["vpa"])
        amount = st.number_input("Amount (₹)", 1.0, 1_00_000.0, ex["amount"], step=50.0)
        hour = st.slider("Hour of day", 0, 23, ex["hour"])
        remark = st.text_input("Remark / note", ex["remark"])
    with c2:
        st.markdown("**Type & payee**")
        txn_type = st.radio("Transaction type", ["P2P", "P2M"], index=["P2P", "P2M"].index(ex["txn_type"]),
                            horizontal=True)
        modes = ["pay", "collect_request", "qr_scan"]
        mode = st.radio("Mode", modes, index=modes.index(ex["mode"]), horizontal=True)
        new = st.checkbox("First time paying this payee", ex["new"])
        age = st.number_input("Payee account age (days)", 0, 5000, ex["age"])
        reports = st.number_input("Fraud reports against payee", 0, 50, ex["reports"])
    with c3:
        st.markdown("**User's device & behaviour**")
        device = st.checkbox("New device in last 48h", ex["device"])
        sim = st.checkbox("SIM changed in last 48h", ex["sim"])
        pins = st.number_input("Failed PIN attempts (24h)", 0, 10, ex["pins"])
        txns = st.number_input("Transactions in last hour", 0, 50, ex["txns"])
        ratio = st.number_input("Amount ÷ user's average", 0.0, 100.0, ex["ratio"], step=0.5)

    row = pd.DataFrame([{
        "payee_vpa": vpa, "amount": amount, "hour": hour, "txn_type": txn_type, "mode": mode,
        "is_new_payee": int(new), "payee_account_age_days": age, "payee_fraud_reports": reports,
        "device_changed_48h": int(device), "sim_changed_48h": int(sim), "failed_pin_attempts_24h": pins,
        "txns_last_1h": txns, "amount_to_avg_ratio": ratio, "remark": remark,
    }])
    r = score(row, bundle).iloc[0]

    st.divider()
    m1, m2 = st.columns([1, 2])
    m1.metric("Fraud probability", f"{r.fraud_probability:.1%}")
    m1.metric("Risk level", r.risk_level)
    with m2:
        if r.risk_level == "HIGH":
            st.error("🚨 Block / ask for confirmation. This matches known UPI scam patterns.")
        elif r.risk_level == "MEDIUM":
            st.warning("⚠️ Unusual. Show the user a warning before they enter their PIN.")
        else:
            st.success("✅ Looks normal.")
        reasons = [x for x in r.reasons.split("; ") if x]
        if reasons:
            st.markdown("**Risk signals**")
            st.markdown("\n".join(f"- {x}" for x in reasons))

with tab_batch:
    st.write("Upload a CSV with the same columns as `data/upi_transactions.csv`.")
    file = st.file_uploader("UPI transactions CSV", type="csv")
    if file:
        result = score(pd.read_csv(file), bundle).sort_values("fraud_probability", ascending=False)
        counts = result.risk_level.value_counts()
        c1, c2, c3 = st.columns(3)
        c1.metric("High risk", int(counts.get("HIGH", 0)))
        c2.metric("Medium risk", int(counts.get("MEDIUM", 0)))
        c3.metric("Low risk", int(counts.get("LOW", 0)))
        st.dataframe(result, use_container_width=True)
        st.download_button("Download scored CSV", result.to_csv(index=False), "upi_scored.csv")

with tab_model:
    t = metrics["test"]
    st.subheader(f"Best model: {metrics['best_model']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fraud precision", f"{t['fraud_precision']:.1%}")
    c2.metric("Fraud recall", f"{t['fraud_recall']:.1%}")
    c3.metric("PR-AUC", f"{t['average_precision']:.3f}")
    c4.metric("ROC-AUC", f"{t['roc_auc']:.3f}")

    left, right = st.columns(2)
    with left:
        st.write("Recall by scam type (test set)")
        st.bar_chart(pd.Series(t["recall_by_fraud_type"], name="recall"))
        (tn, fp), (fn, tp) = t["confusion_matrix"]
        st.write("Confusion matrix")
        st.table(pd.DataFrame([[tn, fp], [fn, tp]], index=["Actual legit", "Actual fraud"],
                              columns=["Predicted legit", "Predicted fraud"]))
    with right:
        st.write("Most important features (permutation importance)")
        st.bar_chart(pd.Series(metrics["feature_importance"], name="importance").head(10))
