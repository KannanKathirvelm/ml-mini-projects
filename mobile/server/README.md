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
It runs locally and as a Hugging Face Space (Docker SDK, port 7860).

The API contract is [`../API.md`](../API.md) (paths, params, JSON shapes, error format
`{"detail": "..."}`). Interactive docs: `/docs` on a running server.

| Project | Endpoints |
|---|---|
| health | `GET /health` |
| 01 credit card fraud | `GET /api/credit-card/meta`, `POST /api/credit-card/predict` |
| 02 UPI fraud | `GET /api/upi/meta`, `GET /api/upi/examples`, `POST /api/upi/predict` |
| 03 stocks (RNN vs LSTM) | `GET /api/stocks/tickers`, `GET /api/stocks/{ticker}/forecast?days=10`, `POST /api/stocks/{ticker}/train` |
| 04 financial AI agents | `GET /api/finance/{ticker}/report` |
| 05 price comparison | `GET /api/prices/search?q=`, `GET /api/prices/history?product=&days=30`, `GET /api/prices/tracked`, `POST /api/prices/track`, `DELETE /api/prices/track?product=`, `POST /api/prices/check-alerts` |
| 06 face detection | `POST /api/faces/detect` (multipart: `image`, `detector`, `blur`, `threshold`) |
| 07 object detection | `GET /api/objects/classes`, `POST /api/objects/detect` (multipart: `image`, `conf`, `iou`, `classes`, `model`) |

## Layout

```
app/                FastAPI code (main.py, loader.py, routers/)
projects/           copies of the needed files from 01_… to 07_… (made by prepare.sh)
scripts/prepare.py  the copy step (manifest of what is copied)
scripts/build_models.py  retrain 01/02, train missing stock models, pre-fetch YOLO assets
tests/              pytest suite (TestClient) covering every endpoint + the loader
Dockerfile, requirements.txt
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
Run the tests with `.venv/bin/python -m pytest` (`RUN_TRAIN=1` adds a real ~30 s training run).
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

**Stocks:** AAPL, MSFT, RELIANCE.NS and TCS.NS models are shipped in `projects/03_…/models`
(trained locally). `POST /api/stocks/{ticker}/train` still works at runtime and writes into the
container (lost on restart).

## Deploy to Hugging Face Spaces

1. On huggingface.co: **New Space** → name it `ml-mini-projects` → SDK **Docker** → template
   *Blank* → hardware *CPU basic (free)*.
2. Make sure `projects/` is populated (`./prepare.sh --models`). Then either:

   **Option A, git** (needs `git lfs install` once; `.gitattributes` routes `*.pt`, `*.onnx`,
   images through LFS because HF rejects plain files over 10 MB):
   ```bash
   cd "/Users/kannan-moni/Desktop/My new project /mobile/server"
   git init -b main
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
| `STOCK_PRICE_MAX_AGE_HOURS` | `12` | Refresh a stock's cached prices from Yahoo when older than this. |
| `PRELOAD` | `1` | Load all models at startup (`0` = load on first request). |
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
