"""Sanity checks for freshly trained universal stock models (used by nightly_retrain.sh).

    python mobile/server/scripts/check_universal.py <models folder>

Fails (exit 1) if:
- the meta file is missing pieces, or fewer than 30 training / 3 held-out stocks were used,
- any metric is not finite,
- RNN or LSTM is more than 5% worse than the naive baseline (mean per-stock RMSE ratio) on
  held-out time or held-out stocks: the models are expected to be about equal to naive, so this
  only catches a broken model,
- ONNX Runtime and torch disagree: 10-day recursive forecasts on real price series must match
  to 1e-5 relative, and single-step outputs to 1e-4 absolute (scaled units).
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
P03 = ROOT / "03_stock_price_prediction_lstm_rnn"
sys.path.insert(0, str(P03))

import numpy as np  # noqa: E402
import torch  # noqa: E402

import universal as U  # noqa: E402
from data import load_prices  # noqa: E402
from model import PriceRNN  # noqa: E402
from onnx_model import OnnxPredictor  # noqa: E402

MAX_RATIO = 1.05


def main(folder: Path) -> int:
    errors = []
    meta = json.loads((folder / "universal_meta.json").read_text())
    min_train = int(os.environ.get("CHECK_MIN_TRAIN_STOCKS", "30"))
    if len(meta["train_symbols"]) < min_train:
        errors.append(f"only {len(meta['train_symbols'])} training stocks")
    if len(meta["holdout_symbols"]) < min(3, min_train):
        errors.append(f"only {len(meta['holdout_symbols'])} held-out stocks")
    for key, ev in meta["eval"].items():
        for cell in ["naive_baseline", *meta["cells"]]:
            e = ev[cell]
            for k in ("mape_pct", "rmse_return_pct", "mean_rmse_ratio_vs_naive"):
                if not math.isfinite(e[k]):
                    errors.append(f"{key}/{cell}/{k} is not finite")
            if cell != "naive_baseline" and e["mean_rmse_ratio_vs_naive"] > MAX_RATIO:
                errors.append(f"{key}/{cell}: RMSE {e['mean_rmse_ratio_vs_naive']:.3f}x naive (> {MAX_RATIO})")
        print(f"{key}: " + ", ".join(
            f"{c} MAPE {ev[c]['mape_pct']:.3f}% RMSE/naive {ev[c]['mean_rmse_ratio_vs_naive']:.4f}"
            for c in ["naive_baseline", *meta["cells"]]))

    worst_rel, worst_abs = 0.0, 0.0
    for cell in meta["cells"]:
        m = PriceRNN(cell)
        m.load_state_dict(torch.load(folder / f"universal_{cell}.pt", weights_only=True))
        m.eval()

        @torch.no_grad()
        def tfn(X, m=m):
            return m(torch.from_numpy(X)).numpy()

        ofn = OnnxPredictor(folder / f"universal_{cell}.onnx")
        for sym in (meta["train_symbols"][:3] + meta["holdout_symbols"][:2]):
            prices = load_prices(sym)
            scale = U.stock_scale(np.log(prices.values))
            a = np.array(U.forecast(tfn, prices.values, 10, scale))
            b = np.array(U.forecast(ofn, prices.values, 10, scale))
            worst_rel = max(worst_rel, float(np.max(np.abs(a - b) / np.abs(a))))
            bt_t = U.backtest({"x": tfn}, prices)["predictions"]["x"]
            bt_o = U.backtest({"x": ofn}, prices)["predictions"]["x"]
            worst_rel = max(worst_rel, float(np.max(np.abs(np.array(bt_t) - bt_o) / np.array(bt_t))))
            X = U.stock_windows(prices, *U.split_dates(prices.index[-1]))[0]["test"][0]
            worst_abs = max(worst_abs, float(np.max(np.abs(tfn(X) - ofn(X)))))
    print(f"ONNX vs torch: max relative price diff {worst_rel:.2e}, max abs scaled diff {worst_abs:.2e}")
    if worst_rel > 1e-5:
        errors.append(f"ONNX/torch forecast mismatch {worst_rel:.2e} > 1e-5")
    if worst_abs > 1e-4:
        errors.append(f"ONNX/torch output mismatch {worst_abs:.2e} > 1e-4")
    for e in errors:
        print("FAIL:", e)
    print("OK" if not errors else f"{len(errors)} check(s) failed")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else P03 / "models")))
