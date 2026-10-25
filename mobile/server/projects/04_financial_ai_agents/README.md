# Financial AI Agents for Market Insights

A small multi-agent system that takes a stock ticker (e.g. `AAPL`, `MSFT`, `RELIANCE.NS`) and
writes a market-insight report: summary, bullish and bearish points, key risks and an overall
outlook. Three specialist agents analyse different kinds of data, and a lead agent combines
their findings into the final report.

It runs in two modes:

- **LLM mode:** each agent is a Claude call made with the official `anthropic` SDK.
- **Offline mode:** each agent uses deterministic rules. This is the default when no API key is set.

Both modes produce the same report structure. The CLI, the dashboard and every report show
which mode was used.

> **Not financial advice.** This is an educational project. It uses public Yahoo Finance data,
> which may be delayed or incomplete.

## India first

The project defaults to Indian markets (NSE), while still accepting US and other symbols.
All of this lives in `india.py` and needs no network unless it fetches prices.

- **Type a symbol or a company name.** `normalize_ticker` turns user input into a Yahoo symbol:
  `reliance` → `RELIANCE.NS`, `infosys` / `Infosys Ltd` → `INFY.NS`, `state bank` → `SBIN.NS`,
  `relaince industries` (typo, fuzzy match) → `RELIANCE.NS`, `bajaj-auto` → `BAJAJ-AUTO.NS`,
  `nifty` → `^NSEI`, `sensex` → `^BSESN`, `banknifty` → `^NSEBANK`, `tatamotors` → `TMPV.NS`
  (Tata Motors' passenger business after the 2025 demerger). Explicit suffixes are kept, so
  `INFY.BO` stays on BSE, and known US symbols (`AAPL`, `MSFT`, `BRK-B`) pass through unchanged.
- **NSE stock list.** `data/nse_equities.csv` is NSE's official equity list (2,613 symbols, snapshot
  2026-10-24, with ISIN and series). `search_nse("infos")` searches it by symbol prefix and by
  company-name words. `python india.py --refresh` re-downloads it from NSE (NSE sometimes blocks
  scripted downloads; the bundled snapshot is kept if it does).
- **Spot check (2026-10-25):** 10 random symbols from the list (`random.seed(7)`) all returned
  prices from Yahoo (`india.has_data`): 10/10.
- **₹ formatting with Indian digit grouping:** `format_inr(1234567.8)` → `₹12,34,567.80`,
  `format_inr_compact(1.72e13)` → `₹17.2 lakh crore`; `format_money` picks ₹ or $ from the currency.
- **Market hours:** `market_status()` says whether NSE is open (09:15–15:30 IST, Mon–Fri) with the
  next open/close in IST. Exchange holidays are not modelled.
- **Freshness:** `cache_is_stale` re-downloads daily prices every 5 minutes while the market is
  open, and after the close only when a newer session exists; `data_as_of` gives the "as of" time
  shown in every report.
- **Live quote and intraday chart:** `live_quote` and `intraday` (1-minute bars) from Yahoo,
  cached ~15–30 s while the market is open. The dashboard's quote header refreshes itself every
  45 s with `st.fragment(run_every=...)`, only during market hours.
- **Benchmark:** every report compares the stock with NIFTY 50 (Indian symbols) or the S&P 500
  (others) over 1 month, 3 months and 1 year, with beta (`indicators.benchmark_stats`).
  Indian reports also compare the P/E with the Nifty 50 P/E (live from Yahoo when available,
  otherwise a stated long-run reference of 21x, labelled as such).
- **Data gaps, stated honestly:** promoter holding and pledges, FII/DII flows and NSE corporate
  announcements are not in Yahoo's free data, so they are not assessed; Indian news coverage on
  Yahoo is sparse and the report says so when fewer than 3 headlines are found.

**Live data caveat:** Yahoo Finance's free feed is not an official exchange feed and NSE quotes may
be delayed by a few minutes. Real-time NSE data needs a licensed broker API (Zerodha Kite Connect,
Upstox, Angel SmartAPI) with your own account.

## Agent architecture

```
                 ticker
                   |
          +--------v---------+      yfinance (free, no key)
          |   Data tools     |----> price history (2y), Ticker.info key stats,
          |  data_tools.py   |      headlines (Ticker.news -> Yahoo search fallback)
          +--------+---------+
                   |  + indicators.py (SMA 20/50/200, RSI, MACD, volatility, drawdown)
     +-------------+--------------+
     |             |              |
+----v------+ +----v--------+ +---v-----------+
| Technical | | Fundamental | | News &        |   each returns a Finding:
| Analyst   | | Analyst     | | Sentiment     |   stance, summary,
|           | |             | | Analyst       |   bullish / bearish points
+----+------+ +----+--------+ +---+-----------+
     +-------------+--------------+
                   |
          +--------v---------+
          |   Lead Analyst   |  summary, bullish/bearish points, key risks,
          |                  |  outlook + confidence + rationale
          +--------+---------+
                   |
        CLI (report.py) / Streamlit (app.py) / Markdown in reports/
```

| Agent | Input | Offline (rule-based) logic |
|---|---|---|
| Technical Analyst | Indicators computed with pandas | Price vs SMA50/SMA200, SMA50 vs SMA200 cross, RSI zones, MACD vs signal, 3-month return, volatility and drawdown flags |
| Fundamental Analyst | `Ticker.info` (missing fields are skipped) | P/E, PEG, margins, ROE, revenue/earnings growth, debt/equity, analyst target upside and consensus |
| News & Sentiment Analyst | Up to 10 recent headlines | Counts positive and negative keywords in each headline, then sums them into a net score |
| Lead Analyst | All findings plus key indicators | Weighted vote (technical 40%, fundamental 40%, news 20%). Confidence is based on how many agents agree. Risks come from volatility, drawdown, valuation, leverage and beta |

The data is fetched once and the same precomputed data goes to every agent. The agents do not
use tools, which keeps the two modes interchangeable and makes it clear what each agent saw.

## Modes

### Offline mode (default, no key needed)
If `ANTHROPIC_API_KEY` is not set, every agent runs its rule-based logic and the output is
labelled `Offline mode (rule-based, no API key)`. You can also force offline mode with
`--offline`.

### LLM mode (Claude)
Set a key and the agents switch to Claude automatically:

```bash
export ANTHROPIC_API_KEY=...
```

- **Model:** `claude-opus-5-5` by default. Override it with the `FIN_AGENTS_MODEL` env var, the
  `--model` flag or the dashboard's model box.
- **Effort:** `FIN_AGENTS_EFFORT` sets the effort level (`low`, `medium`, `high`, `xhigh` or
  `max`; default `medium`).
- Each agent sends one request with a role-specific system prompt and the precomputed data. It
  asks for **structured JSON output** (`output_config.format` with a JSON schema), so Claude's
  answer fills the same `Finding` and report fields as the rules do.
- Server-side refusal fallback is enabled (`fallbacks="default"`).
- If a Claude call fails (network error, API error, refusal or truncation), that agent falls back
  to its rules and the report shows a note saying so.

## Setup

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

## Run

CLI report for one ticker:

```bash
.venv/bin/python report.py --ticker AAPL
```

Save the report as Markdown in `reports/`:

```bash
.venv/bin/python report.py --ticker RELIANCE.NS --save
```

Compare several tickers (prints each report, then a comparison table):

```bash
.venv/bin/python report.py --ticker AAPL MSFT RELIANCE.NS
```

Force offline mode or pick a model:

```bash
.venv/bin/python report.py --ticker MSFT --offline
```

```bash
.venv/bin/python report.py --ticker MSFT --model claude-opus-5-5
```

Dashboard (ticker input, price chart with SMAs, a tab per agent, final report, mode
indicator, download button):

```bash
.venv/bin/streamlit run app.py
```

Tests (offline India helpers, a headless dashboard smoke test with real Yahoo data, and checks
of the LLM request with a mocked transport, so no Claude API call is made):

```bash
.venv/bin/python -m pytest -q tests
```

## Sample output (real offline run, 2026-10-24)

```
$ .venv/bin/python report.py --ticker AAPL
[mode] Offline mode (rule-based, no API key)
# Market insight: Apple Inc. (AAPL)

*Generated 2026-10-24 20:30 | Offline mode (rule-based, no API key) | Last close 347.73 USD (2026-10-23)*

**Outlook: NEUTRAL** (confidence: low)

## Summary
Apple Inc. (AAPL) closed at 347.73 on 2026-10-23. Specialist views: technical bullish,
fundamental neutral, news bearish. Weighted outlook: neutral (score +0.20).

## Bullish points
- Price 347.73 is above the 50-day SMA (329.47).
- Price is above the 200-day SMA (294.11): long-term uptrend.
- 50-day SMA is above the 200-day SMA (golden-cross alignment).
- Strong profit margin of 28%.
- High return on equity (149%).
- Revenue growing 16% year over year.

## Bearish points
- Rich valuation at P/E 36.3; high expectations priced in.
- PEG 2.79 is high relative to expected growth.
- Analyst mean target 328.35 implies -5.6% vs current price.
...
### Technical Analyst: bullish
Technical picture is bullish (score +4.25). RSI 64, 1-year volatility 24%, max 1-year drawdown -14%, 1-year return +35.0%.
```

```
$ .venv/bin/python report.py --ticker AAPL MSFT RELIANCE.NS
...
| Ticker | Outlook | Confidence |
|---|---|---|
| AAPL | neutral | low |
| MSFT | bullish | medium |
| RELIANCE.NS | neutral | low |
```

```
$ .venv/bin/python report.py --ticker ZZZZNOTREAL
Error: No price data found for 'ZZZZNOTREAL'. Check the Yahoo Finance symbol (e.g. AAPL, MSFT, RELIANCE.NS, TCS.NS).
```

## Project structure

```
04_financial_ai_agents/
├── india.py           # India-first: ticker rule, NSE list + search, ₹, market hours, live quotes
├── data/nse_equities.csv  # NSE's official equity list (snapshot)
├── data_tools.py      # yfinance wrappers: history, key stats, news (with fallbacks)
├── indicators.py      # SMA, RSI, MACD, volatility, drawdown in plain pandas
├── llm.py             # mode detection, model config, Claude JSON call
├── agents.py          # Technical / Fundamental / News agents + Lead Analyst
├── pipeline.py        # orchestration + Markdown rendering (shared by CLI and UI)
├── report.py          # CLI
├── app.py             # Streamlit dashboard
├── tests/
│   ├── test_india.py      # normalisation, NSE search, ₹ formatting, market hours, benchmark (offline)
│   ├── test_app.py        # streamlit AppTest smoke tests (real data, offline)
│   └── test_llm_path.py   # LLM request shape + fallbacks via mocked transport
├── reports/           # saved Markdown reports (git-ignored)
├── requirements.txt
└── .gitignore
```

## Caveats

- Keyword sentiment is crude. A headline can be about the wider market rather than the
  company, and sarcasm or context is missed. LLM mode handles this better.
- Yahoo often returns no `Ticker.news` items, so the app falls back to Yahoo search. For some
  non-US tickers, only a few relevant headlines (or none) are found.
- Yahoo reports `dividendYield` and `debtToEquity` as percentages, but margins and growth as
  fractions. The code follows those conventions.
