# 📈 Stock Price Prediction: RNN vs LSTM

Predicts the next day's closing price of any Yahoo Finance ticker with two PyTorch models, a **vanilla RNN** and an **LSTM**. Both are compared with a naive baseline, and there is a Streamlit dashboard plus a multi-day forecast.

> Educational project. Not financial advice.

## How it works

1. **Data (`data.py`)**: downloads adjusted daily closes with `yfinance` (cached in `data/`) and splits them **in time order**: 80% train, 10% validation, 10% test.
2. **Inputs**: each sample is the last 60 days written relative to the latest day, `log(price[t-k] / price[t])`. The target is tomorrow's log return. This is scale-free, so the model works at any price level.
   - *Why not feed raw prices?* The first version did, and failed badly. AAPL in the test period traded above every price seen in training, and a model trained on scaled raw prices can't predict beyond that range. RMSE was 23–35 vs 4.4 for the naive guess.
3. **Models (`model.py`)**: `PriceRNN(cell="rnn" | "lstm")`, with 2 recurrent layers, 64 hidden units, dropout, and a linear head. Both use exactly the same architecture, so the comparison is fair.
4. **Training (`train.py`)**: Adam, MSE loss, gradient clipping (the plain RNN needs it), and early stopping on validation loss.
5. **Evaluation**: RMSE, MAE, MAPE, and **direction accuracy** (did it call up/down correctly?) on the unseen test period, compared with **naive: tomorrow = today**.
6. **Forecast (`predict.py`)**: recursive. Each predicted day is fed back in to predict the next.

## Results: AAPL, test period Aug 2025 → Oct 2026 (297 days)

| Model | RMSE | MAE | MAPE | Direction acc. |
|---|---|---|---|---|
| Naive (tomorrow = today) | 4.357 | 3.090 | 1.09% | n/a |
| RNN | 4.359 | 3.096 | 1.10% | 51.9% |
| LSTM | 4.355 | 3.097 | 1.10% | 49.2% |

![test plot](models/AAPL_test_plot.png)

**How to read this:** the models track the price closely (about 1% error), but so does "tomorrow = today". Direction accuracy is around 50%, like a coin flip. Daily prices are close to a random walk, so a model that only sees past prices can't do much better. Many online tutorials show a "perfect-looking" LSTM chart without this baseline. Comparing against one is the most important skill this project teaches.

**Ideas to explore:** add volume and technical indicators (RSI, moving averages), news sentiment, or predict weekly instead of daily moves, then check whether you beat the baseline.

## India first

- **Default ticker RELIANCE.NS.** The dashboard has quick-pick buttons for popular NSE stocks, a
  searchable picker over NSE's official equity list (2,613 symbols, `data/nse_equities.csv`) and a
  free-text box that understands company names (`infosys` → `INFY.NS`, `state bank` → `SBIN.NS`,
  `nifty` → `^NSEI`; `india.py` is shared with project 04, see its README for the full rule).
- **₹ everywhere** for Indian symbols (Indian digit grouping: ₹12,34,567.80), $ for US ones.
- **Fresh data:** `data.load_prices(..., refresh="auto")` re-downloads the cached daily CSV every
  5 minutes while the exchange is open and, after the close, only when a newer session exists
  (`india.cache_is_stale`). Every chart says what the data is "as of" (IST).
- **Live quote + intraday chart** at the top of the dashboard (Yahoo, 1-minute bars). It refreshes
  itself every 45 s with `st.fragment(run_every=...)`, only while NSE is open. Yahoo's NSE feed may
  be delayed by a few minutes and is not an official exchange feed.

## India universal model (one model for every NSE stock)

Because the inputs are scale-free, one RNN and one LSTM can be trained on many stocks at once and
then applied to **any** stock, including ones they never saw. `train_universal.py` pools
50 liquid NSE stocks (`india_universe.txt`, roughly the NIFTY 50):

- each stock's windows are divided by that stock's own daily volatility (std of its last ~3 years
  of log returns before the cut-off), so a quiet large-cap and a jumpy mid-cap look alike;
- the split uses the **same calendar dates for every stock** (train < 2024-10-23 ≤ validation
  < 2025-10-23 ≤ test ≤ 2026-10-23), so no stock's test year overlaps another stock's
  training data (market-wide moves would otherwise leak);
- 8 more stocks (BERGEPAINT, DABUR, GODREJCP, HAVELLS, LUPIN, MARICO, PIDILITIND, SIEMENS)
  are **never trained on** and measure generalisation to unseen stocks.

```bash
.venv/bin/python train_universal.py              # ~8.5 min on an Apple M-series CPU
.venv/bin/python train_universal.py --refresh    # re-download prices first
.venv/bin/python export_onnx.py                  # ONNX copies for the slim server (pip install onnx onnxruntime onnxscript)
```

### Honest results (trained 2026-10-25, 116,612 training windows)

**Held-out time:** the 50 training stocks over the test year (12,400 stock-days; up days 48.2%).

| Model | MAPE | RMSE of daily return | Direction acc. | RMSE / naive (mean per stock) | Stocks beating naive |
|---|---|---|---|---|---|
| Naive (tomorrow = today) | 1.161% | 1.641% | n/a | 1.0000 | 0/50 |
| RNN | 1.164% | 1.643% | 48.6% | 1.0016 | 10/50 |
| LSTM | 1.165% | 1.643% | 48.2% | 1.0020 | 5/50 |

**Held-out stocks:** 8 stocks never seen in training, same test year (1,983 stock-days; up days 47.8%).

| Model | MAPE | RMSE of daily return | Direction acc. | RMSE / naive (mean per stock) | Stocks beating naive |
|---|---|---|---|---|---|
| Naive (tomorrow = today) | 1.145% | 1.566% | n/a | 1.0000 | 0/8 |
| RNN | 1.147% | 1.569% | 48.7% | 1.0022 | 2/8 |
| LSTM | 1.148% | 1.568% | 47.9% | 1.0017 | 0/8 |

MAPE and the RMSE of the daily return are pooled over all stock-days (price RMSE can't be pooled
across stocks priced at ₹50 and ₹50,000), "RMSE / naive" is averaged per stock (< 1 = better than
naive).

**How to read this:** pooling 50 stocks does not create an edge. Both models are about **0.2%
worse than "tomorrow = today"** on RMSE, and direction accuracy (~48–49%) is at or below what you
would get by always guessing "down" in this period (100% − up days ≈ 52%). The model learned to
predict tiny moves close to zero, which is the sensible answer for a near-random walk. It
generalises to unseen stocks exactly as well (or as badly) as to the training stocks, which is
the good news: the scale-free design really does transfer. Use it to learn, not to trade.

The dashboard and the API show the same comparison per stock: a walk-forward back-test of the
universal model on that stock's last 120 trading days next to the naive baseline.

### Per-ticker models still work

The original per-ticker training (`train.py --ticker AAPL`, the "Per-ticker model" mode in the
dashboard) is unchanged and works for any Yahoo symbol, including US tickers.

## Run it

This project uses its own virtual environment because it needs PyTorch.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python train.py --ticker AAPL            # ~1 min on CPU
```

```bash
.venv/bin/python predict.py --ticker AAPL --days 10
```

```bash
.venv/bin/python -m streamlit run app.py
```

(`python -m streamlit` instead of the `.venv/bin/streamlit` launcher, which macOS may block.)

```bash
.venv/bin/python -m pytest -q tests      # offline helpers + headless dashboard test (needs Yahoo)
```

Any Yahoo Finance symbol works: `MSFT`, `TSLA`, `RELIANCE.NS`, `TCS.NS`, `^NSEI` (Nifty 50). Use `--refresh` to re-download the latest prices, and `--device mps` to train on the Apple GPU (CPU is usually as fast for models this small).

## Project structure

```
data.py      download + cache prices (market-hours-aware refresh), scale-free windows, split
model.py     PriceRNN (RNN / LSTM), price conversion, recursive forecast
train.py     trains both models, early stopping, metrics vs baseline, saves plot
predict.py   N-day forecast CLI
app.py       Streamlit dashboard (India universal or per-ticker model, live quote, forecast)
india.py     India helpers shared with project 04 (ticker rule, NSE list, ₹, market hours, quotes)
universal.py pooled universal model: torch-free windows, scaling, metrics, forecast, back-test
train_universal.py  trains the universal RNN + LSTM on india_universe.txt
export_onnx.py      .pt -> .onnx with a parity check; onnx_model.py runs them with onnxruntime
tests/       universal helpers + a headless dashboard smoke test
models/      <TICKER>_rnn.pt, <TICKER>_lstm.pt, <TICKER>_meta.json, <TICKER>_test_plot.png,
             universal_{rnn,lstm}.{pt,onnx}, universal_meta.json (metrics + per-stock results)
```
