"""Server settings from environment variables (all optional)."""
import os
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]

# "full" (default): torch + ultralytics, can train stock models at runtime.
# "slim" (Render free tier, 512 MB): ONNX Runtime + OpenCV + scikit-learn only, no training,
# models load lazily on first use. torch/ultralytics imports are blocked (see app/__init__.py).
PROFILE = os.environ.get("SERVER_PROFILE", "full").strip().lower() or "full"
if PROFILE not in ("full", "slim"):
    raise ValueError(f"SERVER_PROFILE must be 'full' or 'slim', not {PROFILE!r}")
SLIM = PROFILE == "slim"

# Where scripts/prepare.py put the project copies.
PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", SERVER_DIR / "projects")).resolve()

# Writable state. Defaults to the system temp dir (/tmp in the container).
DATA_DIR = Path(os.environ.get("SERVER_DATA_DIR",
                               Path(tempfile.gettempdir()) / "ml-mini-projects")).resolve()
PRICES_DB_PATH = Path(os.environ.get("PRICES_DB_PATH", DATA_DIR / "prices.db")).resolve()

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "8")) * 1024 * 1024
MAX_IMAGE_SIDE = int(os.environ.get("MAX_IMAGE_SIDE", "1280"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "85"))

# Finance reports hit Yahoo several times; cache them briefly.
FINANCE_CACHE_SECONDS = int(os.environ.get("FINANCE_CACHE_SECONDS", "900"))
# YOLO device: unset = project default (mps on Apple Silicon, else cpu).
OBJECTS_DEVICE = os.environ.get("OBJECTS_DEVICE") or None
# Load every model at startup (default) instead of on first request.
# Slim defaults to lazy loading so the process starts small and fast (Render health check).
PRELOAD = os.environ.get("PRELOAD", "0" if SLIM else "1") not in ("0", "false", "False")
SEED_PRICE_HISTORY = os.environ.get("SEED_PRICE_HISTORY", "1") not in ("0", "false", "False")

VERSION = "1"
