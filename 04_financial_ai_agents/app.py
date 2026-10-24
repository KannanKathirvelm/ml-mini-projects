"""Streamlit dashboard: run with `.venv/bin/streamlit run app.py`.

Same pipeline as the CLI; adds a price chart and one tab per agent.
"""
import plotly.graph_objects as go
import streamlit as st

import llm
from data_tools import TickerNotFound
from india import (INDICES, POPULAR_STOCKS, exchange_of, fmt_ist, format_money, intraday,
                   live_quote, market_status, normalize_ticker, nse_equities)
from indicators import add_indicator_columns
from pipeline import DISCLAIMER, benchmark_table, run_analysis, to_markdown

STANCE_ICON = {"bullish": "🟢", "neutral": "🟡", "bearish": "🔴"}

st.set_page_config(page_title="Financial AI Agents", page_icon="📊", layout="wide")
st.title("📊 Financial AI Agents: Market Insights")
st.caption(DISCLAIMER)

@st.cache_data(show_spinner=False)
def ticker_options() -> list[str]:
    """Popular stocks and indices first, then every NSE equity (selectbox search is by substring)."""
    seen, out = set(), []
    for sym, name in ([(s["symbol"], s["name"]) for s in POPULAR_STOCKS + INDICES]
                      + [(f"{r['symbol']}.NS", r["name"]) for r in nse_equities()]):
        if sym not in seen:
            seen.add(sym)
            out.append(f"{sym} — {name}")
    return out


with st.sidebar:
    typed = st.text_input("Type any ticker or company name", "",
                          help="Overrides the list below. e.g. reliance, infosys, state bank, "
                               "INFY.BO, nifty, AAPL").strip()
    picked = st.selectbox("…or search all NSE stocks", ticker_options(), index=0,
                          help="Popular Nifty 50 stocks and indices first, then ~2,600 NSE equities. "
                               "Type to filter by symbol or name.")
    raw = typed or picked.split(" — ")[0]
    try:
        ticker = normalize_ticker(raw)
    except ValueError:
        ticker = ""
    if typed and ticker != typed.upper():
        st.caption(f"Resolved **{typed}** → **{ticker}**")
    key_set = llm.llm_available()
    use_llm = st.toggle("Use Claude (LLM mode)", value=key_set, disabled=not key_set,
                        help="Needs ANTHROPIC_API_KEY in the environment.")
    model = st.text_input("Claude model", llm.MODEL, disabled=not use_llm)
    if use_llm:
        st.success(llm.mode_label(True, model))
    else:
        st.info(llm.mode_label(False))


def live_panel(symbol: str):
    """Quote header + today's intraday chart; re-runs every 45 s while the market is open."""
    is_open = market_status(exchange=exchange_of(symbol))["is_open"]

    @st.fragment(run_every=45 if is_open else None)
    def panel():
        try:
            q = live_quote(symbol)
            bars = intraday(symbol, "1m")["bars"]
        except Exception as exc:  # Yahoo hiccup: the report below still works
            st.warning(f"Live quote unavailable: {exc}")
            return
        color = "green" if (q["change"] or 0) >= 0 else "red"
        pill = ":green-badge[Market open]" if q["market_open"] else ":gray-badge[Market closed]"
        st.markdown(f"## {q['display']['price']} :{color}[{q['display']['change']}]  \n"
                    f"{pill} as of {fmt_ist(q['as_of_ist'])} · {q['source']}")
        if bars:
            fig = go.Figure(go.Scatter(x=[b["time_ist"] for b in bars], y=[b["close"] for b in bars],
                                       line=dict(width=1.5, color=color), name="1-min close"))
            fig.update_layout(height=220, margin=dict(l=10, r=10, t=30, b=10),
                              title=f"Intraday ({bars[0]['time_ist'][:10]}, IST)")
            st.plotly_chart(fig, width="stretch")
        if not q["market_open"]:
            st.caption("Market closed: showing the last session. Auto-refresh runs only during market hours.")

    panel()


@st.cache_data(ttl=900, show_spinner=False)
def analyse(ticker: str, use_llm: bool, model: str):
    return run_analysis(ticker, use_llm=use_llm, model=model)


def price_chart(history, ticker: str) -> go.Figure:
    df = add_indicator_columns(history).iloc[-252:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Close", line=dict(width=2)))
    for col, dash in (("SMA20", "dot"), ("SMA50", "dash"), ("SMA200", "solid")):
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=col, line=dict(width=1, dash=dash)))
    fig.update_layout(title=f"{ticker}: last 12 months with SMAs", height=420,
                      margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h"))
    return fig


if not ticker:
    st.stop()

try:
    with st.spinner(f"Agents analysing {ticker}..."):
        a = analyse(ticker, use_llm, model)
except TickerNotFound as exc:
    st.error(str(exc))
    st.stop()

r, ind = a.report, a.data["indicators"]
prof = a.data["fundamentals"]["profile"]
cur = prof.get("currency")
name = prof.get("longName", a.ticker)
st.subheader(f"{name} ({a.ticker})")
facts = [prof.get("sector"), prof.get("industry")]
mcap = a.data["fundamentals"]["stats"].get("marketCap")
if mcap:
    facts.append(f"Market cap {format_money(mcap, cur, compact=True)}")
st.caption(" · ".join(f for f in facts if f))
live_panel(a.ticker)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Last daily close", format_money(ind["last_close"], cur), f"{(ind['return_1m'] or 0):+.1%} 1m")
c2.metric("RSI (14)", f"{ind['rsi14']:.0f}")
c3.metric("1y volatility", f"{ind['volatility_1y']:.0%}")
c4.metric("Outlook", f"{STANCE_ICON[r['outlook']]} {r['outlook'].title()}", f"confidence: {r['confidence']}",
          delta_color="off")

st.plotly_chart(price_chart(a.history, a.ticker), width="stretch")

tabs = st.tabs(["Final report"] + [f.agent for f in a.findings])
with tabs[0]:
    st.markdown(f"**{a.mode}** | generated {a.generated} | data as of {fmt_ist(a.data['as_of']['as_of_ist'])}")
    st.caption(a.data["as_of"]["note"])
    st.markdown(f"### Summary\n{r['summary']}")
    left, right = st.columns(2)
    left.markdown("### Bullish points\n" + "\n".join(f"- {p}" for p in r["bullish_points"] or ["(none)"]))
    right.markdown("### Bearish points\n" + "\n".join(f"- {p}" for p in r["bearish_points"] or ["(none)"]))
    st.markdown("### Key risks\n" + "\n".join(f"- {p}" for p in r["key_risks"]))
    st.markdown(f"### Overall outlook: {STANCE_ICON[r['outlook']]} {r['outlook'].upper()}\n{r['outlook_rationale']}")
    bench = a.data.get("benchmark")
    st.markdown(f"### Benchmark: vs {(bench or {}).get('name', 'index')}\n" + "\n".join(benchmark_table(bench)))
    if r.get("note"):
        st.warning(r["note"])
    st.download_button("Download report (.md)", to_markdown(a), file_name=f"{a.ticker}_report.md",
                       mime="text/markdown")

for tab, f in zip(tabs[1:], a.findings):
    with tab:
        st.markdown(f"#### {STANCE_ICON[f.stance]} {f.stance.title()}  \n{f.summary}")
        st.caption(f"Source: {'Claude' if f.source == 'llm' else 'rule-based'}")
        if f.note:
            st.warning(f.note)
        left, right = st.columns(2)
        left.markdown("**Bullish**\n" + "\n".join(f"- {p}" for p in f.bullish_points or ["(none)"]))
        right.markdown("**Bearish**\n" + "\n".join(f"- {p}" for p in f.bearish_points or ["(none)"]))
        if f.agent.startswith("Technical"):
            st.dataframe({k: [v] for k, v in ind.items()}, width="stretch")
        elif f.agent.startswith("Fundamental"):
            stats = a.data["fundamentals"]["stats"]
            st.dataframe({"metric": list(stats), "value": [str(v) for v in stats.values()]}, width="stretch")
        else:
            for n in a.data["news"]:
                st.markdown(f"- {n['date']} [{n['title']}]({n['link']}) ({n['publisher']})")
