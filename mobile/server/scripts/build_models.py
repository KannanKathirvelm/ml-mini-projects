"""Build the model files that are not shipped in the repo, inside server/projects/.

    python scripts/build_models.py --sklearn              # retrain 01 + 02 (deterministic, ~1 min)
    python scripts/build_models.py --stocks MSFT,TCS.NS   # train stock models that are missing
    python scripts/build_models.py --warm-yolo            # fetch missing YOLO weights + font

Each project's own generate_data.py / train.py is run as a subprocess with the
project copy as working directory, so bare-name imports stay isolated.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
PROJECTS = Path(os.environ.get("PROJECTS_DIR", SERVER / "projects"))

SKLEARN = {
    "01_credit_card_fraud_detection": ("models/fraud_model.joblib", "data/transactions.csv"),
    "02_upi_fraud_detection": ("models/upi_fraud_model.joblib", "data/upi_transactions.csv"),
}
STOCKS = "03_stock_price_prediction_lstm_rnn"
YOLO = "07_object_detection"


def run(cmd: list[str], cwd: Path) -> None:
    t0 = time.time()
    print(f"$ ({cwd.name}) {' '.join(cmd)}", flush=True)
    subprocess.run([sys.executable, *cmd], cwd=cwd, check=True)
    print(f"  done in {time.time() - t0:.1f}s", flush=True)


def build_sklearn(force: bool, clean: bool) -> None:
    for project, (model, data) in SKLEARN.items():
        root = PROJECTS / project
        if force or not (root / model).exists():
            run(["generate_data.py"], root)
            run(["train.py"], root)
        if clean and (root / data).exists():
            (root / data).unlink()  # regenerated on demand; keeps the image small


def build_stocks(tickers: list[str], force: bool) -> None:
    root = PROJECTS / STOCKS
    for t in tickers:
        if force or not (root / "models" / f"{t.replace('^', '_')}_meta.json").exists():
            run(["train.py", "--ticker", t], root)
        else:
            print(f"  {t}: already trained")


def warm_yolo() -> None:
    code = (
        "import config\n"
        "from detector import Detector\n"
        "for m in ('yolo11n.pt', 'yolo11s.pt'):\n"
        "    d = Detector(m, device='cpu')\n"
        "    r = d.detect('samples/bus.jpg')\n"
        "    print(m, 'ok', len(r.detections), 'detections')\n"
    )
    run(["-c", code], PROJECTS / YOLO)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sklearn", action="store_true")
    p.add_argument("--stocks", default="", help="comma-separated tickers")
    p.add_argument("--warm-yolo", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--clean-data", action="store_true", help="delete generated CSVs after training")
    a = p.parse_args()
    if a.sklearn:
        build_sklearn(a.force, a.clean_data)
    if a.stocks:
        build_stocks([t.strip().upper() for t in a.stocks.split(",") if t.strip()], a.force)
    if a.warm_yolo:
        warm_yolo()


if __name__ == "__main__":
    main()
