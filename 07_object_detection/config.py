"""Project-wide paths and setup.

Ultralytics keeps a global settings file and drops datasets, runs and weights
in your home directory by default. Pointing YOLO_CONFIG_DIR at the project
(before ultralytics is imported) keeps everything inside this folder, so
deleting the folder removes every artifact. Import this module first.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / "samples"
OUTPUTS_DIR = ROOT / "outputs"
WEIGHTS_DIR = ROOT / "weights"
DATASETS_DIR = ROOT / "datasets"
RUNS_DIR = ROOT / "runs"

os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".ultralytics"))
os.environ.setdefault("YOLO_OFFLINE", "False")

from ultralytics import settings  # noqa: E402  (must come after the env var)

settings.update(
    {
        "datasets_dir": str(DATASETS_DIR),
        "runs_dir": str(RUNS_DIR),
        "weights_dir": str(WEIGHTS_DIR),
        "sync": False,  # no anonymous usage analytics
    }
)

# YOLO11 detection checkpoints, smallest/fastest first.
MODEL_SIZES = {
    "nano": "yolo11n.pt",
    "small": "yolo11s.pt",
    "medium": "yolo11m.pt",
}
DEFAULT_MODEL = MODEL_SIZES["nano"]


def pick_device(requested: str | None = None) -> str:
    """Return the requested device, else Apple 'mps' when available, else 'cpu'."""
    if requested:
        return requested
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def weights_path(model: str) -> str:
    """Bare names like 'yolo11n.pt' resolve into weights/ so downloads land there."""
    p = Path(model)
    if p.parent == Path(".") and not p.exists():
        WEIGHTS_DIR.mkdir(exist_ok=True)
        return str(WEIGHTS_DIR / p.name)
    return str(p)
