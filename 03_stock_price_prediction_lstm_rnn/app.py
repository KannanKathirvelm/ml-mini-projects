"""Streamlit dashboard: run with `.venv/bin/streamlit run app.py`."""
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from predict import future_forecast
from train import CELLS, MODEL_DIR, run, safe_name

st.set_page_config(page_title="Stock Price Prediction", page_icon="📈", layout="wide")
st.title("📈 Stock Price Prediction: RNN vs LSTM")
st.caption("Educational project. Not financial advice.")

with st.sidebar:
    ticker = st.text_input("Ticker", "AAPL", help="Yahoo Finance symbol, e.g. AAPL, MSFT, TSLA, RELIANCE.NS, ^NSEI").strip().upper()
    days = st.slider("Forecast days", 1, 30, 10)
    epochs = st.slider("Max training epochs", 10, 150, 60)
    retrain = st.button("Train / retrain models", type="primary")

meta_path = MODEL_DIR / f"{safe_name(ticker)}_meta.json"
if retrain:
    lines = []
    box = st.empty()

    def log(msg):
        lines.append(msg)
        box.code("\n".join(lines[-25:]))

    with st.spinner(f"Downloading {ticker} and training RNN + LSTM..."):
        try:
            run(ticker, epochs=epochs, refresh=True, log=log)
        except ValueError as e:
            st.error(str(e))
            st.stop()
    box.empty()

if not meta_path.exists():
    st.info(f"No trained models for **{ticker}** yet. Click **Train / retrain models** in the sidebar (about 1 minute).")
    st.stop()

meta = json.loads(meta_path.read_text())
res = meta["results"]

st.subheader(f"{ticker}: test period {meta['test_dates'][0]} → {meta['test_dates'][-1]}")
cols = st.columns(3)
for col, name, label in zip(cols, ["naive_baseline", "rnn", "lstm"], ["Naive (tomorrow = today)", "RNN", "LSTM"]):
    m = res[name]
    col.metric(label, f"MAPE {m['mape_pct']:.2f}%",
               None if m["direction_acc_pct"] is None else f"direction {m['direction_acc_pct']:.1f}%",
               delta_color="off")

pred = meta["predictions"]
dates = pd.to_datetime(meta["test_dates"])
fig = go.Figure()
fig.add_trace(go.Scatter(x=dates, y=pred["actual"], name="Actual", line=dict(color="black", width=2)))
for cell in CELLS:
    fig.add_trace(go.Scatter(x=dates, y=pred[cell], name=cell.upper(), opacity=0.85))
fig.update_layout(height=420, margin=dict(t=30, b=10), hovermode="x unified",
                  yaxis_title="Close price", legend=dict(orientation="h"))
st.plotly_chart(fig, width="stretch")

left, right = st.columns(2)
with left:
    st.markdown("**Test metrics**")
    table = pd.DataFrame(res).T.rename(columns={"rmse": "RMSE", "mae": "MAE", "mape_pct": "MAPE %",
                                                 "direction_acc_pct": "Direction acc %"})
    st.dataframe(table.style.format(precision=3, na_rep="n/a"), width="stretch")
    st.markdown("**Training curves (validation loss)**")
    st.line_chart(pd.DataFrame({c.upper(): pd.Series([h["val_loss"] for h in meta["history"][c]]) for c in CELLS}))
with right:
    st.markdown(f"**Next {days} trading days forecast**")
    prices, fc = future_forecast(ticker, days)
    hist = prices.iloc[-90:]
    f2 = go.Figure()
    f2.add_trace(go.Scatter(x=hist.index, y=hist.values, name="History", line=dict(color="black")))
    for cell in CELLS:
        f2.add_trace(go.Scatter(x=[hist.index[-1], *fc.index], y=[hist.iloc[-1], *fc[cell]],
                                name=f"{cell.upper()} forecast", line=dict(dash="dash")))
    f2.update_layout(height=320, margin=dict(t=10, b=10), hovermode="x unified", legend=dict(orientation="h"))
    st.plotly_chart(f2, width="stretch")
    st.dataframe(fc.rename(columns=str.upper), width="stretch")

with st.expander("Why are the models so close to the naive baseline?"):
    st.markdown("""
Daily stock prices are close to a **random walk**: today's price already reflects most available
information, so "tomorrow = today" is a very strong baseline. A model that only sees past prices
usually matches it but rarely beats it by much, and direction accuracy near 50% is typical.

That is the real lesson of this project. Low error alone can be misleading, because even the naive
guess is only about 1% off. Always compare against a baseline before trusting a price model.
""")
