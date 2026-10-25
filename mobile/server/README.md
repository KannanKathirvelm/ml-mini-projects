---
title: ML Mini Projects API
emoji: 🧪
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: One FastAPI backend for 7 ML mini projects
---

# ML mini projects API

One FastAPI server that exposes the 7 ML mini projects (fraud detection, stock RNN/LSTM,
financial agents, price comparison, face detection, object detection) to the mobile apps.
It runs locally (full profile, PyTorch) and on **Render's free tier** (slim profile: ONNX Runtime,
no torch), and can still be built as a Hugging Face Space (Docker SDK, port 7860).

The API contract is [`../API.md`](../API.md) (paths, params, JSON shapes, error format
`{"detail": "..."}`). Interactive docs: `/docs` on a running server.

| Project | Endpoints |
|---|---|
| health | `GET /health` |
| 01 credit card fraud | `GET /api/credit-card/meta`, `POST /api/credit-card/predict` |
| 02 UPI fraud | `GET /api/upi/meta`, `GET /api/upi/examples`, `POST /api/upi/predict` |
| 03 stocks (RNN vs LSTM) | `GET /api/stocks/tickers`, `GET /api/stocks/{ticker}/forecast?days=10&model=auto`, `POST /api/stocks/{ticker}/train` |
| 04 financial AI agents | `GET /api/finance/{ticker}/report` |
| 05 price comparison | `GET /api/prices/search?q=`, `GET /api/prices/history?product=&days=30`, `GET /api/prices/tracked`, `POST /api/prices/track`, `DELETE /api/prices/track?product=`, `POST /api/prices/check-alerts` |
| 06 face detection | `POST /api/faces/detect` (multipart: `image`, `detector`, `blur`, `threshold`) |
| 07 object detection | `GET /api/objects/classes`, `POST /api/objects/detect` (multipart: `image`, `conf`, `iou`, `classes`, `model`) |
| India market data | `GET /api/india/popular`, `/market-status`, `/search?q=`, `/stocks?offset=&limit=`, `/quote/{ticker}`, `/quotes?symbols=`, `/intraday/{ticker}?interval=1m` |

## India first

Every ticker in `/api/stocks`, `/api/finance` and `/api/india` is free text, normalised India
first by the projects' `india.py` (`reliance` → `RELIANCE.NS`, `infosys` → `INFY.NS`, `nifty` →
`^NSEI`; US symbols pass through). Responses carry `normalized_ticker`, `currency`, ₹/$ `display`
strings and an IST `as_of_ist` (API.md sections 8 and 9).

- **Stocks:** besides the per-ticker models (AAPL, MSFT, GOOGL, RELIANCE.NS, TCS.NS), a pooled
  **India universal** RNN + LSTM (trained on 50 NSE stocks, project 03 `train_universal.py`)
  forecasts **any** stock with ≥ 106 trading days, no training needed (`"model": "universal"`).
  Its metrics in the response are a live walk-forward back-test on that stock's last 120 days.
  Honest evaluation (test year Oct 2025 → Oct 2026): RMSE about 0.2% *worse* than the naive
  "tomorrow = today" baseline, both on the 50 training stocks and on 8 stocks it never saw;
  direction accuracy ~48–49%. Details: `03_stock_price_prediction_lstm_rnn/README.md`.
- **Finance:** reports add a NIFTY 50 (or S&P 500) benchmark with 1m/3m/1y returns and beta,
  sector, industry and a ₹ lakh-crore market cap.
- **Quotes/intraday:** Yahoo's free feed (NSE may be delayed a few minutes; not an official feed),
  cached ~15 s while NSE is open and ~10 min when it is closed.

## Profiles: full (local) and slim (Render)

`SERVER_PROFILE=full` (default) is the original server: PyTorch for the stock models (and
runtime training), Ultralytics for YOLO11. `SERVER_PROFILE=slim` runs the **same API** with no
torch and no ultralytics (any import of them raises `ImportError`, see `app/__init__.py`):

| Project | Slim implementation | Parity with full |
|---|---|---|
| 03 stocks | universal + per-ticker RNN/LSTM exported to ONNX (`projects/03_…/models/*.onnx`, 54–206 KB each), forecast/back-test maths in numpy (`universal.py`) + onnxruntime | max scaled-output diff 6e-7; 10-day forecasts within 1e-8 relative; API numbers identical to 2 dp (`tests/test_india.py`) |
| 07 objects | YOLO11n/s exported to ONNX (opset 17, dynamic H/W; 10.6 MB / 37.9 MB) + `app/yolo_onnx.py`: ultralytics-style rectangular letterbox, decode, class-aware NMS, same drawing palette | `bus.jpg`, `zidane.jpg` at 3 settings: same classes and counts, boxes within 0.0003 px, confidences equal, annotated images pixel-identical |
| 06 faces | OpenCV only (YuNet ONNX + Haar), unchanged | same code |
| 01/02 fraud | scikit-learn 1.9.1 (the version that wrote the shipped pickles) | same pickles |
| 04/05/india | yfinance, pandas, requests, rapidfuzz, anthropic (LLM mode only with a key) | same code |

`POST /api/stocks/{ticker}/train` on slim returns the universal forecast with
`"model": "universal", "trained": false` instead of training. Models load lazily on first use
(`PRELOAD=0` is the slim default) and only one YOLO session is kept in memory at a time.

**Memory (measured 2026-10-25, macOS, Python 3.12, fresh venv from `requirements-render.txt`,
`tests/slim_smoke.py --url` against uvicorn on port 7870, every endpoint incl. both YOLO models,
3 rounds):** ~100–130 MB RSS after startup, peak RSS 451–498 MB, peak *physical footprint*
345–367 MB. macOS RSS also counts ~185 MB of shared-library code pages (`__TEXT`), so the
physical-footprint number is the closer estimate of what a Linux container is charged; expect
roughly 350–450 MB on Render's 512 MB instance with all features exercised. Biggest items:
scikit-learn + the random-forest pickle (~115 MB), pandas/yfinance (~60 MB), the YOLO11s session
(~70–90 MB). If the instance is ever killed for memory, avoid `yolo11s.pt` (the n model is the
default).

## Deploy to Render (free)

`render.yaml` at the repo root is a Render Blueprint for one **free** web service:

- name `ml-mini-projects`, `runtime: python`, `plan: free`, `rootDir: mobile/server`
- build: `pip install --no-cache-dir -r requirements-render.txt && python scripts/build_models.py --sklearn-if-broken --clean-data`
  (keeps the shipped 01/02 pickles if they load with the installed scikit-learn, otherwise retrains them, ~30 s)
- start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
- health check `/health`; env `PYTHON_VERSION=3.12.4`, `SERVER_PROFILE=slim`, `PRELOAD=0`,
  `SERVER_DATA_DIR=/tmp/ml-mini-projects`, `PRICES_DB_PATH=/tmp/ml-mini-projects/prices.db`,
  `OMP_NUM_THREADS=1`, `MALLOC_ARENA_MAX=2`
- no database, disk or paid add-on.

Steps: Render dashboard → **New → Blueprint** → connect the GitHub repo
`KannanKathirvelm/ml-mini-projects` → apply. The URL is `https://ml-mini-projects.onrender.com`
(or with a suffix if the name is taken). Optional: add `ANTHROPIC_API_KEY` as a secret env var in
the dashboard for LLM-mode finance reports.

Free-tier behaviour: the service **sleeps after ~15 min idle** and the next request waits
~30–60 s while it boots (apps should use a long timeout and show "waking up"); the disk is
ephemeral (price-tracking DB and price caches reset on every restart/deploy; 30 days of demo
price history are re-seeded); 0.1 CPU, so YOLO11s takes a few seconds per image. Everything the
slim server needs is in git: ONNX files (largest 37.9 MB), the 01/02 pickles (12 MB + 0.5 MB),
the NSE list, the universal and per-ticker stock models. Nothing uses Git LFS (see
`.gitattributes`), because Render must receive the real files.

Nightly retraining of the universal model (GitHub Actions): see [`CI.md`](CI.md).

## Layout

```
app/                FastAPI code (main.py, loader.py, routers/)
projects/           copies of the needed files from 01_… to 07_… (made by prepare.sh)
scripts/prepare.py  the copy step (manifest of what is copied)
scripts/build_models.py  retrain 01/02 (or only if broken), train missing stock models, pre-fetch YOLO
scripts/export_yolo_onnx.py  YOLO11 .pt -> .onnx + parity check vs ultralytics
scripts/nightly_retrain.sh, check_universal.py  nightly universal-model retrain (CI.md)
app/yolo_onnx.py    torch-free YOLO11 inference for the slim profile
tests/              pytest suite (TestClient): every endpoint, the loader, India endpoints,
                    ONNX parity (stocks + YOLO) and a slim-profile subprocess run
Dockerfile, requirements.txt (full), requirements-render.txt (slim), requirements-retrain.txt
```

**How the 7 projects coexist:** they import their own modules by bare name and reuse names
(`predict`, `train`, `data`, `config`, …). `app/loader.py` imports each project with its folder
first on `sys.path`, then moves every module that lives in that folder out of `sys.modules`
before the next project loads (and stashes/restores any same-named entries). The project code
itself is unchanged. `tests/test_loader.py` loads all 7 side by side and calls each.

## Run locally

```bash
cd "/Users/kannan-moni/Desktop/My new project /mobile/server"
scripts/setup_venv.sh          # creates .venv with the pinned versions (CPU torch, OpenCV 4)
./prepare.sh --models          # copy project files, retrain 01/02, pre-train stock models
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 7860
```

Binding `0.0.0.0` lets the Android emulator reach it at `http://10.0.2.2:7860`.
Run the tests with `.venv/bin/python -m pytest` (`RUN_TRAIN=1` adds a real ~30 s training run;
the ONNX parity tests need `pip install onnx onnxruntime onnxscript` in the full venv).
Try the slim profile locally: `SERVER_PROFILE=slim .venv/bin/uvicorn app.main:app --port 7870`
(torch stays installed but is blocked), or `SERVER_PROFILE=slim .venv/bin/python tests/slim_smoke.py`.
Finance, the two demo store APIs and stock price refreshes need internet access.

## Docker

```bash
docker build -t ml-mini-projects-api .
docker run --rm -p 7860:7860 ml-mini-projects-api
curl http://localhost:7860/health
```

The image: Python 3.12 slim, CPU-only torch from the PyTorch wheel index,
`opencv-python-headless` 4.x (OpenCV 5 removed `CascadeClassifier`, which the Haar detector
needs), runs as uid 1000, and writes only to `$HOME` and `/tmp`. Ultralytics settings, font
and weights live in `$YOLO_CONFIG_DIR=/home/user/.config/Ultralytics` and the project's
`weights/` folder, all pre-fetched at build time.

**scikit-learn models:** the 01/02 pickles are *retrained at image build time* with the pinned
scikit-learn (`scripts/build_models.py --sklearn`, deterministic seeds, about 30 s). A pickle is
only guaranteed to load in the scikit-learn version that wrote it, so this keeps the model and
the library in lockstep whenever a version is bumped, and it keeps the 12 MB pickle out of the
Space repo. Metrics differ slightly from the original 1.8.0 run; `/meta` reports the retrained
numbers.

**Stocks:** AAPL, MSFT, GOOGL, RELIANCE.NS and TCS.NS per-ticker models and the India
universal model are shipped in `projects/03_…/models` (trained locally, `.pt` + `.onnx`). `POST /api/stocks/{ticker}/train` still works at runtime and writes into the
container (lost on restart).

## Deploy to Hugging Face Spaces

1. On huggingface.co: **New Space** → name it `ml-mini-projects` → SDK **Docker** → template
   *Blank* → hardware *CPU basic (free)*.
2. Make sure `projects/` is populated (`./prepare.sh --models`). Then either:

   **Option A, git** (needs `git lfs install` once, because HF rejects plain files over 10 MB;
   this repo's `.gitattributes` deliberately does *not* use LFS, so add the rules in the Space repo):
   ```bash
   cd "/Users/kannan-moni/Desktop/My new project /mobile/server"
   git init -b main
   git lfs track "*.pt" "*.onnx" "*.joblib" "*.png" "*.jpg"
   git remote add origin https://huggingface.co/spaces/<user>/ml-mini-projects
   git add . && git commit -m "ML mini projects API"
   git push -u origin main          # use an HF access token with write scope as the password
   ```

   **Option B, Python** (no git needed; large files are handled automatically):
   ```python
   from huggingface_hub import HfApi
   HfApi().upload_folder(
       folder_path="/Users/kannan-moni/Desktop/My new project /mobile/server",
       repo_id="<user>/ml-mini-projects", repo_type="space",
       ignore_patterns=[".venv/*", "**/__pycache__/*", ".pytest_cache/*", "var/*", "*.db",
                        "projects/07_object_detection/.ultralytics/*",
                        "projects/0[12]_*/models/*", "projects/0[12]_*/data/*"],
   )
   ```
   (run `huggingface-cli login` first).
3. The Space builds the Dockerfile (several minutes) and serves at
   `https://<user>-ml-mini-projects.hf.space`. Check `/health`.
4. Optional: **Settings → Variables and secrets → New secret** `ANTHROPIC_API_KEY`. With it the
   finance agents switch to LLM mode (`"mode": "llm"`); without it they run rule-based offline.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | unset | Enables Claude (LLM mode) for `/api/finance`. Set as an HF **secret**. |
| `FIN_AGENTS_MODEL`, `FIN_AGENTS_EFFORT` | project defaults | Model / effort for LLM mode (project 04). |
| `PRICES_DB_PATH` | `$SERVER_DATA_DIR/prices.db` | SQLite file for price history and tracking. |
| `SERVER_DATA_DIR` | system temp dir (`/tmp/ml-mini-projects` in Docker) | Writable state. |
| `PROJECTS_DIR` | `./projects` | Where the project copies live. |
| `OBJECTS_DEVICE` | auto (`mps` on Apple Silicon, else `cpu`); `cpu` in Docker | YOLO device. |
| `FINANCE_CACHE_SECONDS` | `900` | Per-ticker cache of finance reports. |
| (stock price freshness) | market-hours aware | Cached daily prices refresh every 5 min while the exchange is open, otherwise when a newer session has closed (`india.cache_is_stale`). |
| `SERVER_PROFILE` | `full` | `slim` = no torch/ultralytics: ONNX models, no runtime training (Render). |
| `PRELOAD` | `1` (`0` on slim) | Load all models at startup (`0` = load on first request). |
| `SEED_PRICE_HISTORY` | `1` | Seed 30 days of simulated history when the DB is empty. |
| `MAX_UPLOAD_MB`, `MAX_IMAGE_SIDE`, `JPEG_QUALITY` | `8`, `1280`, `85` | Upload limit (413 above it), downscale size, output JPEG quality. |

## Free-tier caveats

- **Storage is ephemeral.** The SQLite DB (tracked products, search history) and any stock model
  trained at runtime are wiped when the Space restarts or rebuilds. On startup the server re-seeds
  30 days of simulated price history.
- **Cold starts.** Free Spaces sleep after ~48 h without traffic; the first request then waits
  for the container to boot and load the models (roughly 10–30 s), so the apps should use
  generous timeouts and show a "waking up" state.
- **CPU only, 2 vCPU.** YOLO11s and stock training are noticeably slower than on a laptop GPU;
  `POST /api/stocks/{ticker}/train` can take 1–2 minutes and blocks other training calls.
- **Network-dependent endpoints.** Finance reports, the DummyJSON/FakeStore stores and stock
  price refreshes call public APIs (Yahoo Finance etc.) that can rate-limit shared HF IPs; the
  price search reports failing stores in `warnings` instead of failing.
- Data in projects 1, 2 and 5 is synthetic/demo data; projects 3 and 4 are educational, not
  financial advice.
