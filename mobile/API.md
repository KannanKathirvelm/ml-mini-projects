# Mobile API contract (v1)

One FastAPI server exposes all 7 projects. The seven Android apps call it over HTTPS.

- Base URL: `https://<user>-ml-mini-projects.hf.space` in production (Hugging Face Spaces, port 7860), `http://10.0.2.2:7860` from the Android emulator, `http://localhost:7860` locally.
- All responses are JSON. Errors use HTTP 4xx/5xx with body `{"detail": "<human readable message>"}`.
- CORS allows all origins (Capacitor apps load from `https://localhost` / `capacitor://localhost`).
- Images in responses are base64 JPEG strings without the `data:` prefix.
- Field names are `snake_case`. Numbers are plain JSON numbers, money is INR unless stated.

## Common

`GET /health` → `{"status": "ok", "version": "1", "projects": ["credit-card", "upi", "stocks", "finance", "prices", "faces", "objects"]}`

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
