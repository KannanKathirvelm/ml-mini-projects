# Mobile API contract (v1)

One FastAPI server exposes all 7 projects. The seven Android apps call it over HTTPS.

- Base URL: `https://ml-mini-projects.onrender.com` in production (Render free web service, slim profile; the exact host is whatever Render assigns), `https://<user>-ml-mini-projects.hf.space` on Hugging Face Spaces (port 7860), `http://10.0.2.2:7860` from the Android emulator, `http://localhost:7860` locally.
- All responses are JSON. Errors use HTTP 4xx/5xx with body `{"detail": "<human readable message>"}`.
- CORS allows all origins (Capacitor apps load from `https://localhost` / `capacitor://localhost`).
- Images in responses are base64 JPEG strings without the `data:` prefix.
- Field names are `snake_case`. Numbers are plain JSON numbers, money is INR unless stated.

## Common

`GET /health` → `{"status": "ok", "version": "1", "projects": ["credit-card", "upi", "stocks", "finance", "prices", "faces", "objects", "india"], "profile": "full"}`

`profile` is `"full"` (local torch server) or `"slim"` (Render: ONNX models, no training at runtime). The free Render service sleeps after ~15 min idle; the first request after that can take 30–60 s, so use a long timeout and show a "waking up" state.

---

## 1. Credit card fraud: `/api/credit-card`

`GET /api/credit-card/meta` →
```json
{"categories": ["grocery", "gas", "restaurant", "electronics", "travel", "online_retail"],
 "threshold": 0.313,
 "metrics": {"best_model": "random_forest", "fraud_precision": 0.896, "fraud_recall": 0.92, "average_precision": 0.96, "roc_auc": 0.997}}
```

`POST /api/credit-card/predict`, with body:
```json
{"amount": 950, "hour": 2, "distance_from_home_km": 400, "distance_from_last_txn_km": 300,
 "ratio_to_median_amount": 6, "online_order": 1, "used_chip": 0, "used_pin": 0,
 "txn_count_last_24h": 8, "merchant_category": "electronics"}
```
→ `{"fraud_probability": 0.9787, "flagged": true, "threshold": 0.313}`

## 2. UPI fraud: `/api/upi`

`GET /api/upi/meta` → `{"threshold": 0.77, "metrics": {...same keys as above..., "recall_by_fraud_type": {"account_takeover": 1.0, "collect_scam": 0.946, "fake_qr": 0.897}}}`

`GET /api/upi/examples` → list of ready-made inputs:
```json
[{"name": "Normal: paying a friend", "input": { ...predict body... }}, ...]
```
(The same 4 examples as the Streamlit app: normal, fake refund collect request, SIM swap takeover, fake merchant QR.)

`POST /api/upi/predict`, with body:
```json
{"payee_vpa": "refund.helpdesk42@ybl", "amount": 4999, "hour": 11, "txn_type": "P2P",
 "mode": "collect_request", "is_new_payee": 1, "payee_account_age_days": 4,
 "payee_fraud_reports": 2, "device_changed_48h": 0, "sim_changed_48h": 0,
 "failed_pin_attempts_24h": 0, "txns_last_1h": 1, "amount_to_avg_ratio": 5.0,
 "remark": "refund processing"}
```
`txn_type` ∈ `P2P|P2M`, `mode` ∈ `pay|collect_request|qr_scan`.
→ `{"fraud_probability": 0.999, "risk_level": "HIGH", "flagged": true, "threshold": 0.77, "reasons": ["Collect request: ...", "..."]}`
`risk_level` ∈ `LOW|MEDIUM|HIGH`.

## 3. Stock prediction (RNN vs LSTM): `/api/stocks`

`GET /api/stocks/tickers` → `{"trained": ["AAPL", "MSFT", "RELIANCE.NS", "TCS.NS"]}`

`GET /api/stocks/{ticker}/forecast?days=10` (1 ≤ days ≤ 30) →
```json
{"ticker": "AAPL", "last_close": 347.73, "last_date": "2026-10-23",
 "history": [{"date": "2026-06-01", "close": 301.2}, ...],
 "forecast": [{"date": "2026-10-26", "rnn": 347.79, "lstm": 348.11}, ...],
 "metrics": {"naive_baseline": {"rmse": 4.357, "mae": 3.09, "mape_pct": 1.09, "direction_acc_pct": null},
             "rnn": {...}, "lstm": {...}},
 "test": {"dates": ["2025-08-20", ...], "actual": [...], "rnn": [...], "lstm": [...]}}
```
`history` is the last 90 trading days. 404 with a clear `detail` if the ticker isn't trained yet.

`POST /api/stocks/{ticker}/train` trains RNN and LSTM synchronously (about 1 minute) and then returns the same body as `forecast` with `days=10`. Returns 400 for an unknown symbol.

## 4. Financial AI agents: `/api/finance`

`GET /api/finance/{ticker}/report` →
```json
{"ticker": "AAPL", "company": "Apple Inc.", "mode": "offline", "mode_label": "Offline mode (rule-based, no API key)",
 "currency": "USD", "last_close": 347.73, "last_date": "2026-10-23",
 "outlook": "neutral", "confidence": "low",
 "summary": "...", "bullish": ["..."], "bearish": ["..."], "risks": ["..."], "overall": "...",
 "agents": [{"name": "Technical Analyst", "stance": "bullish", "summary": "...", "points": ["..."]}, ...],
 "headlines": [{"title": "...", "publisher": "...", "link": "...", "sentiment": "positive"}],
 "indicators": {"rsi": 64.0, "volatility_1y": 0.24, "return_1m": 0.035, "max_drawdown_1y": -0.12},
 "chart": [{"date": "2025-10-24", "close": 250.1, "sma20": 248.0, "sma50": 245.2, "sma200": null}, ...],
 "markdown": "# Market insight: ..."}
```
`mode` ∈ `offline|llm`, `outlook`/`stance` ∈ `bullish|neutral|bearish`, `confidence` ∈ `low|medium|high`. `chart` is the last ~250 trading days. Fields the pipeline doesn't have may be `null` or empty lists, but the keys are always present. 404 for an unknown ticker.

## 5. Price comparison: `/api/prices`

`GET /api/prices/search?q=iphone` →
```json
{"query": "iphone", "stores_ok": ["DummyJSON", "FakeStore", "ShopKart", "MegaMart", "QuickBuy"], "warnings": [],
 "groups": [{"product": "iPhone 13 Pro", "store_count": 4,
             "best": { ...offer... }, "savings_inr": 14990,
             "offers": [{"store": "MegaMart", "title": "Apple iPhone 13 Pro", "price_inr": 85489, "shipping_inr": 0,
                         "total_inr": 85489, "delivery_days": 3, "rating": 4.5, "in_stock": true,
                         "url": "https://...", "image": "https://..." }]}]}
```
Groups are sorted by relevance, offers by `total_inr` ascending. `best` is the cheapest in-stock offer, or `null` if none are in stock.

`GET /api/prices/history?product=iPhone%2013%20Pro&days=30` → `{"product": "...", "series": [{"store": "MegaMart", "points": [{"date": "2026-10-01", "price_inr": 86000}]}]}`

`GET /api/prices/tracked` → `[{"product": "...", "target_inr": 95000, "latest_best_inr": 85489, "latest_store": "MegaMart", "hit": true}]`

`POST /api/prices/track`, body `{"product": "iPhone 13 Pro", "target_inr": 95000}` → the tracked item, same shape as one row above.

`DELETE /api/prices/track?product=...` → `{"removed": true}`

`POST /api/prices/check-alerts` → `[{"product": "...", "target_inr": 95000, "best_inr": 85489, "store": "MegaMart", "hit": true}]`

Note: on Hugging Face free hardware the SQLite file is wiped on restart. The server re-seeds 30 days of history at startup.

## 6. Face detection: `/api/faces`

`POST /api/faces/detect` (multipart/form-data):
- `image` (file, jpeg/png, max 8 MB)
- `detector` = `yunet` (default) | `haar` | `both`
- `blur` = `true|false` (default false)
- `threshold` = YuNet confidence 0–1 (default 0.6)

→
```json
{"results": [{"detector": "yunet", "count": 7, "time_ms": 36.8,
              "faces": [{"x": 10, "y": 20, "w": 50, "h": 60, "score": 0.9, "landmarks": [[x, y], ...]}],
              "image_base64": "<annotated jpeg>"}]}
```
`results` has one entry, or two for `both` (yunet first). `landmarks` is `null` for Haar. Large images are downscaled to a max side of 1280 before detection, and boxes refer to the downscaled image that is returned.

## 7. Object detection: `/api/objects`

`GET /api/objects/classes` → `{"classes": ["person", "bicycle", ...80 COCO names], "models": ["yolo11n.pt", "yolo11s.pt"]}`

`POST /api/objects/detect` (multipart/form-data):
- `image` (file, max 8 MB)
- `conf` (default 0.25), `iou` (default 0.7)
- `classes` = comma-separated names, empty for all
- `model` = `yolo11n.pt` (default) | `yolo11s.pt`

→
```json
{"count": 5, "time_ms": 7.6, "counts": {"person": 4, "bus": 1},
 "detections": [{"cls": "bus", "conf": 0.94, "box": [x1, y1, x2, y2]}],
 "image_base64": "<annotated jpeg>"}
```

---

## 8. India market data: `/api/india` (added in v1.1, additive)

India-first helpers shared by the stock and finance screens. Every ticker path/query parameter
in this section **and** in `/api/stocks` and `/api/finance` accepts free text and is normalised
India-first (same rule as `04_financial_ai_agents/india.py::normalize_ticker`):
`reliance` → `RELIANCE.NS`, `infosys` → `INFY.NS`, `state bank` → `SBIN.NS`, `nifty` → `^NSEI`,
`sensex` → `^BSESN`, `banknifty` → `^NSEBANK`, `tatamotors` → `TMPV.NS`, `INFY.BO` stays BSE,
`AAPL`/`MSFT` and anything with an explicit suffix or `^` stay as typed. Responses that take a
ticker echo the resolved symbol as `normalized_ticker` (or `symbol`).

Prices come from Yahoo Finance's free feed: NSE quotes may be **delayed by a few minutes** and are
not an official exchange feed. Times are IST ISO-8601 strings, e.g. `"2026-10-23T15:29:00+05:30"`.
Money is in the instrument's `currency` (`"INR"` for NSE/BSE); `display` holds ready-to-show
strings (`"₹1,452.30"`, `"+₹5.50 (+0.38%)"`, Indian digit grouping).

`GET /api/india/popular` → the 20 quick picks and the 3 headline indices:
```json
{"stocks": [{"symbol": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Energy"}, ...],
 "indices": [{"symbol": "^NSEI", "name": "NIFTY 50"}, {"symbol": "^BSESN", "name": "S&P BSE SENSEX"},
             {"symbol": "^NSEBANK", "name": "NIFTY BANK"}]}
```

`GET /api/india/market-status` →
```json
{"exchange": "NSE", "is_open": false, "now_ist": "2026-10-25T19:10:00+05:30",
 "next_open_ist": "2026-10-26T09:15:00+05:30", "next_close_ist": "2026-10-26T15:30:00+05:30",
 "note": "Exchange holidays not included"}
```
Regular session 09:15–15:30 IST, Monday–Friday. Exchange holidays are not modelled.

`GET /api/india/search?q=infos&limit=10` (`q` required, 1 ≤ `limit` ≤ 50, default 10) → searches the
bundled official NSE equity list (~2,600 symbols) by symbol prefix, then by company-name words.
No network needed.
```json
{"query": "infos", "results": [{"symbol": "INFY.NS", "nse_symbol": "INFY", "name": "Infosys Limited",
                                "isin": "INE009A01021", "series": "EQ"}]}
```
`results` is `[]` when nothing matches (not 404).

`GET /api/india/stocks?offset=0&limit=100` (0 ≤ `offset`, 1 ≤ `limit` ≤ 500) → the whole NSE list, paged,
alphabetical by symbol:
```json
{"total": 2613, "offset": 0, "limit": 100, "snapshot_date": "2026-10-24",
 "stocks": [{"symbol": "20MICRONS.NS", "nse_symbol": "20MICRONS", "name": "20 Microns Limited",
             "isin": "INE144J01027", "series": "EQ"}, ...]}
```

`GET /api/india/quote/{ticker}` (e.g. `/api/india/quote/reliance`) → near-live quote:
```json
{"symbol": "RELIANCE.NS", "name": "Reliance Industries", "price": 1452.3, "change": 5.5,
 "change_pct": 0.38, "prev_close": 1446.8, "open": 1448.0, "high": 1460.0, "low": 1440.1,
 "volume": 8123456, "currency": "INR",
 "display": {"price": "₹1,452.30", "change": "+₹5.50 (+0.38%)"},
 "as_of_ist": "2026-10-23T15:29:00+05:30", "market_open": false,
 "source": "Yahoo Finance (may be delayed)",
 "delayed_note": "Free Yahoo Finance data; NSE quotes may be delayed by a few minutes and are not an official exchange feed."}
```
Works for indices (`nifty`) and US symbols too (then `currency` is `"USD"`, `display` uses `$`).
Any numeric field may be `null` if Yahoo omits it. Cached about 15 s while the market is open,
10 min when closed. 404 `{"detail": "..."}` if Yahoo has no price for the symbol.

`GET /api/india/quotes?symbols=RELIANCE,TCS,nifty` (comma-separated, 1–20 symbols) →
```json
{"quotes": [ ...quote objects as above... ],
 "errors": [{"symbol": "ZZZZ", "detail": "No price data found for 'ZZZZ'..."}]}
```
Symbols that fail go to `errors` instead of failing the request. More than 20 → 400.

`GET /api/india/intraday/{ticker}?interval=1m` (`interval` = `1m` (default) | `5m`) → today's bars,
or the last session's when the market has not traded today:
```json
{"symbol": "RELIANCE.NS", "interval": "1m", "session_date": "2026-10-23", "market_open": false,
 "source": "Yahoo Finance (may be delayed)",
 "bars": [{"time_ist": "2026-10-23T09:15:00+05:30", "open": 1448.0, "high": 1449.5, "low": 1447.2,
           "close": 1449.1, "volume": 120345}, ...]}
```
Poll every 30–60 s while `market_open` is true; there is no point polling when it is false.
400 for another `interval`, 404 for no data.

## 9. India fields added to existing endpoints (additive)

`GET /api/stocks/{ticker}/forecast` and `POST /api/stocks/{ticker}/train` gain:
```json
{"normalized_ticker": "RELIANCE.NS", "name": "Reliance Industries", "currency": "INR",
 "display": {"last_close": "₹1,452.30"}, "as_of_ist": "2026-10-23T15:30:00+05:30",
 "market_open": false, "model": "universal",
 "model_info": {"kind": "universal", "trained_on": 50, "held_out_stocks": ["BERGEPAINT.NS", ...],
                "trained_until": "2024-10-23", "data_until": "2026-10-23",
                "trained_at": "2026-10-25T14:09:00+00:00",
                "note": "One RNN and one LSTM trained on ~50 liquid NSE stocks pooled together..."}}
```
- `ticker` keeps its old meaning (the symbol that was forecast) and now equals `normalized_ticker`.
- Optional query `model` = `auto` (default) | `universal` | `per_ticker`.
  `auto` uses `"per_ticker"` when a model trained on this exact symbol exists (AAPL, MSFT, GOOGL,
  RELIANCE.NS, TCS.NS are shipped), otherwise `"universal"`: the pooled India model, which works
  for **any** symbol with at least 106 trading days of history (inputs are scale-free), so every
  NSE stock can be forecast without training. `model=per_ticker` without such a model → 404.
- With `"universal"`, `metrics` and `test` are a live walk-forward back-test of the universal
  model on this stock's last 120 trading days (same keys as before: `naive_baseline`, `rnn`,
  `lstm`; `test.dates/actual/rnn/lstm`). With `"per_ticker"` they are that model's own held-out
  test period, as before.
- `GET /api/stocks/tickers` gains `"universal": true` (any ticker can be forecast) and
  `"universal_info"` (same object as `model_info` above, or `null`).
- `POST /api/stocks/{ticker}/train` also returns `"trained": true|false`. On the full (torch)
  server it trains a per-ticker model (about 1 minute) and returns its forecast (`"model":
  "per_ticker"`, `"trained": true`). On the slim hosted server (`SERVER_PROFILE=slim`, used on
  Render) there is no training at runtime: it immediately returns the universal forecast with
  `"model": "universal"` and `"trained": false`. Treat both as success and render the forecast.
- 404 now only happens when Yahoo has no price data for the symbol (or under 106 days of it).
- Every number in the forecast is in `currency`; use `display.last_close` for the headline price.

`GET /api/finance/{ticker}/report` gains:
```json
{"normalized_ticker": "TCS.NS", "sector": "Technology", "industry": "Information Technology Services",
 "market_cap_display": "₹11.2 lakh crore", "as_of_ist": "2026-10-23T15:30:00+05:30",
 "display": {"last_close": "₹3,050.20"},
 "benchmark": {"symbol": "^NSEI", "name": "NIFTY 50",
               "stock_return_1m": -0.021, "index_return_1m": 0.012,
               "stock_return_3m": 0.034, "index_return_3m": 0.028,
               "stock_return_1y": -0.18, "index_return_1y": 0.07,
               "beta": 0.62, "relative_strength_1y": -0.234}}
```
Returns are fractions (`0.034` = +3.4%). `benchmark` is NIFTY 50 for Indian symbols and S&P 500
(`^GSPC`) otherwise; it is `null` if the index download fails, and any of its numbers may be
`null` (e.g. `beta` with too little overlapping history). `sector`, `industry`,
`market_cap_display` may be `null`.
