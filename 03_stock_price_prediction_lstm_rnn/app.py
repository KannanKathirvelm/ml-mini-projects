"""Streamlit dashboard: run with `.venv/bin/python -m streamlit run app.py`.

India first: RELIANCE.NS by default, search all ~2,600 NSE stocks, ₹ prices, live quote and
intraday chart while NSE is open. Two model modes:
- India universal model: one RNN + one LSTM trained on ~50 NSE stocks pooled together; works for
  any stock without training (scale-free inputs).
- Per-ticker model: train an RNN + LSTM on one symbol (the original project; any Yahoo ticker).
"""
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import torch

import universal as U
from data import is_stale, load_prices
from india import (INDICES, POPULAR_STOCKS, data_as_of, exchange_of, fmt_ist, format_money,
                   intraday, is_indian, live_quote, market_status, normalize_ticker, nse_equities,
                   stock_name)
from model import PriceRNN
from predict import future_forecast
from train import CELLS, MODEL_DIR, run, safe_name

st.set_page_config(page_title="Stock Price Prediction", page_icon="📈", layout="wide")
st.title("📈 Stock Price Prediction: RNN vs LSTM")
st.caption("Educational project. Not financial advice. Prices: Yahoo Finance (NSE may be delayed).")

DEFAULT = "RELIANCE.NS"
MODES = ["India universal model (any NSE stock, no training)", "Per-ticker model (train on one symbol)"]


@st.cache_data(show_spinner=False)
def ticker_options() -> list[str]:
    seen, out = set(), []
    for sym, name in ([(s["symbol"], s["name"]) for s in POPULAR_STOCKS + INDICES]
                      + [(f"{r['symbol']}.NS", r["name"]) for r in nse_equities()]):
        if sym not in seen:
            seen.add(sym)
            out.append(f"{sym} — {name}")
    return out


@st.cache_resource(show_spinner=False)
def universal_models(mtime: float):
    fns = {}
    for cell in CELLS:
        m = PriceRNN(cell)
        m.load_state_dict(torch.load(MODEL_DIR / f"universal_{cell}.pt", weights_only=True))
        m.eval()

        @torch.no_grad()
        def fn(X, m=m):
            return m(torch.from_numpy(X)).numpy()
        fns[cell] = fn
    return fns


def currency_of(t: str) -> str | None:
    return "INR" if is_indian(t) else ("USD" if "." not in t and not t.startswith("^") else None)


with st.sidebar:
    mode = st.radio("Model", MODES, index=0)
    universal_mode = mode == MODES[0]
    st.markdown("**Quick picks**")
    quick = st.pills("Popular NSE stocks", [s["symbol"].removesuffix(".NS") for s in POPULAR_STOCKS[:10]],
                     label_visibility="collapsed")
    options = ticker_options()
    default_idx = next((i for i, o in enumerate(options) if o.startswith(DEFAULT + " ")), 0)
    picked = st.selectbox("Search all NSE stocks", options, index=default_idx,
                          help="Popular stocks and indices first, then every NSE equity. Type to filter.")
    typed = st.text_input("…or type any ticker / company name", "",
                          help="e.g. infosys, state bank, TCS, INFY.BO, nifty, AAPL").strip()
    raw = typed or (quick if quick else picked.split(" — ")[0])
    try:
        ticker = normalize_ticker(raw)
    except ValueError:
        ticker = DEFAULT
    if typed and ticker != typed.upper():
        st.caption(f"Resolved **{typed}** → **{ticker}**")
    days = st.slider("Forecast days", 1, 30, 10)
    if not universal_mode:
        epochs = st.slider("Max training epochs", 10, 150, 60)
        retrain = st.button("Train / retrain models", type="primary")
    else:
        retrain = False

cur = currency_of(ticker)
money = lambda x: format_money(x, cur)  # noqa: E731
st.subheader(f"{stock_name(ticker) or ticker} ({ticker})")


def live_panel(symbol: str):
    """Quote header + intraday chart; re-runs every 45 s while the exchange is open."""
    is_open = market_status(exchange=exchange_of(symbol))["is_open"]

    @st.fragment(run_every=45 if is_open else None)
    def panel():
        try:
            q = live_quote(symbol)
            bars = intraday(symbol, "1m")["bars"]
        except Exception as exc:
            st.warning(f"Live quote unavailable: {exc}")
            return
        color = "green" if (q["change"] or 0) >= 0 else "red"
        pill = ":green-badge[Market open]" if q["market_open"] else ":gray-badge[Market closed]"
        st.markdown(f"### {q['display']['price']} :{color}[{q['display']['change']}]  \n"
                    f"{pill} as of {fmt_ist(q['as_of_ist'])} · {q['source']}")
        if bars:
            fig = go.Figure(go.Scatter(x=[b["time_ist"] for b in bars], y=[b["close"] for b in bars],
                                       line=dict(width=1.5, color=color), name="1-min close"))
            fig.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10),
                              title=f"Intraday ({bars[0]['time_ist'][:10]}, IST)")
            st.plotly_chart(fig, width="stretch")
        if not q["market_open"]:
            st.caption("Market closed: showing the last session. Auto-refresh runs only during market hours.")

    panel()


live_panel(ticker)


def forecast_chart(prices: pd.Series, fc: pd.DataFrame):
    hist = prices.iloc[-90:]
    f2 = go.Figure()
    f2.add_trace(go.Scatter(x=hist.index, y=hist.values, name="History", line=dict(color="black")))
    for cell in CELLS:
        f2.add_trace(go.Scatter(x=[hist.index[-1], *fc.index], y=[hist.iloc[-1], *fc[cell]],
                                name=f"{cell.upper()} forecast", line=dict(dash="dash")))
    f2.update_layout(height=320, margin=dict(t=10, b=10), hovermode="x unified", legend=dict(orientation="h"),
                     yaxis_title=f"Close ({cur or 'price'})")
    st.plotly_chart(f2, width="stretch")
    st.dataframe(fc.rename(columns=str.upper).map(money), width="stretch")


def metric_cards(res: dict):
    cols = st.columns(3)
    for col, name, label in zip(cols, ["naive_baseline", "rnn", "lstm"], ["Naive (tomorrow = today)", "RNN", "LSTM"]):
        m = res[name]
        col.metric(label, f"MAPE {m['mape_pct']:.2f}%",
                   None if m["direction_acc_pct"] is None else f"direction {m['direction_acc_pct']:.1f}%",
                   delta_color="off")


def test_chart(dates, actual, preds: dict):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=actual, name="Actual", line=dict(color="black", width=2)))
    for cell in CELLS:
        fig.add_trace(go.Scatter(x=dates, y=preds[cell], name=cell.upper(), opacity=0.85))
    fig.update_layout(height=380, margin=dict(t=30, b=10), hovermode="x unified",
                      yaxis_title=f"Close ({cur or 'price'})", legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")


def as_of_caption(prices: pd.Series):
    cache = MODEL_DIR.parent / "data" / f"{ticker.replace('^', '_')}.csv"
    fetched = cache.stat().st_mtime if cache.exists() else 0
    a = data_as_of(ticker, prices.index[-1].date(), fetched)
    st.caption(f"Daily data as of {fmt_ist(a['as_of_ist'])}. {a['note']}"
               + ("" if not is_stale(ticker) else " (refresh pending)"))


# ------------------------------------------------------------------ universal mode
if universal_mode:
    umeta = U.load_meta()
    if not umeta or not all((MODEL_DIR / f"universal_{c}.pt").exists() for c in CELLS):
        st.info("The universal model is not trained yet. Run `python train_universal.py` (about 15 min on CPU).")
        st.stop()
    fns = universal_models((MODEL_DIR / "universal_lstm.pt").stat().st_mtime)
    try:
        prices = load_prices(ticker, refresh="auto")
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    prices = prices[prices > 0]
    if len(prices) < U.WINDOW + U.MIN_SCALE_DAYS + 6:
        st.error(f"{ticker} has only {len(prices)} trading days of history; the model needs at least "
                 f"{U.WINDOW + U.MIN_SCALE_DAYS + 6}.")
        st.stop()
    c1, c2 = st.columns(2)
    c1.metric("Last daily close", money(float(prices.iloc[-1])), str(prices.index[-1].date()), delta_color="off")
    c2.metric("Model", "India universal", f"{len(umeta['train_symbols'])} NSE stocks pooled", delta_color="off")
    as_of_caption(prices)

    bt = U.backtest(fns, prices)
    st.markdown(f"**Walk-forward check on {ticker}'s last {len(bt['dates'])} trading days** "
                f"({bt['dates'][0]} → {bt['dates'][-1]})")
    metric_cards(bt["results"])
    test_chart(pd.to_datetime(bt["dates"]), bt["actual"], bt["predictions"])

    left, right = st.columns(2)
    with left:
        st.markdown("**Back-test metrics (this stock)**")
        table = pd.DataFrame(bt["results"]).T.rename(columns={"rmse": "RMSE", "mae": "MAE", "mape_pct": "MAPE %",
                                                              "direction_acc_pct": "Direction acc %"})
        st.dataframe(table.style.format(precision=3, na_rep="n/a"), width="stretch")
        st.markdown("**Universal model evaluation (pooled)**")
        rows = []
        for key, ev in umeta["eval"].items():
            for m in ["naive_baseline", *CELLS]:
                e = ev[m]
                rows.append({"set": ev["kind"], "model": m, "MAPE %": e["mape_pct"],
                             "Direction %": e["direction_acc_pct"], "RMSE / naive": e["mean_rmse_ratio_vs_naive"],
                             "stocks beating naive": f"{e['stocks_beating_naive_rmse']}/{ev['n_stocks']}"})
        st.dataframe(pd.DataFrame(rows).style.format(precision=3, na_rep="n/a"), width="stretch", hide_index=True)
        st.caption(f"Trained on {len(umeta['train_symbols'])} stocks up to {umeta['val_start']}; test year "
                   f"{umeta['test_start']} → {umeta['last_date']}; held-out stocks: "
                   f"{', '.join(s.removesuffix('.NS') for s in umeta['holdout_symbols'])}.")
    with right:
        st.markdown(f"**Next {days} trading days forecast**")
        scale = U.stock_scale(np.log(prices.values))
        dates = pd.bdate_range(prices.index[-1] + pd.Timedelta(days=1), periods=days)
        fc = pd.DataFrame({c: U.forecast(fn, prices.values, days, scale) for c, fn in fns.items()}, index=dates)
        forecast_chart(prices, fc)

# ------------------------------------------------------------------ per-ticker mode
else:
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
        st.info(f"No per-ticker models for **{ticker}** yet. Click **Train / retrain models** in the sidebar "
                "(about 1 minute), or switch to the India universal model, which needs no training.")
        st.stop()

    meta = json.loads(meta_path.read_text())
    res = meta["results"]
    st.markdown(f"**Test period {meta['test_dates'][0]} → {meta['test_dates'][-1]}** (per-ticker model)")
    metric_cards(res)
    pred = meta["predictions"]
    test_chart(pd.to_datetime(meta["test_dates"]), pred["actual"], pred)

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
        prices, fc = future_forecast(ticker, days, refresh="auto")
        as_of_caption(prices)
        forecast_chart(prices, fc)

with st.expander("Why are the models so close to the naive baseline?"):
    st.markdown("""
Daily stock prices are close to a **random walk**: today's price already reflects most available
information, so "tomorrow = today" is a very strong baseline. A model that only sees past prices
usually matches it but rarely beats it by much, and direction accuracy near 50% is typical.

That is the real lesson of this project. Low error alone can be misleading, because even the naive
guess is only about 1% off. Always compare against a baseline before trusting a price model.
The universal model shows the same thing across ~50 NSE stocks and on stocks it never saw.
""")
