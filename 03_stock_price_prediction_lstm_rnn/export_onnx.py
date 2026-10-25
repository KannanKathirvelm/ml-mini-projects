"""Export trained RNN / LSTM weights to ONNX and check parity with torch.

    python export_onnx.py                       # universal + every per-ticker model in models/
    python export_onnx.py --only universal      # just the universal pair
    python export_onnx.py --dir /some/staging   # a different models folder

For each <name>_{rnn,lstm}.pt it writes <name>_{rnn,lstm}.onnx (input "x": float32
[batch, window, 1], output "y": [batch]) and compares ONNX Runtime with torch on random and
real-looking windows. Exits 1 if the max abs difference exceeds --tol (default 1e-4 on the
scaled output, i.e. ~1e-6 of a daily return).

Needs: pip install onnx onnxruntime onnxscript
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import torch

from model import PriceRNN
from onnx_model import OnnxPredictor

MODEL_DIR = Path(__file__).parent / "models"
WINDOW = 60


def export(pt: Path, cell: str, out: Path) -> None:
    m = PriceRNN(cell)
    m.load_state_dict(torch.load(pt, weights_only=True))
    m.eval()
    x = torch.zeros(2, WINDOW, 1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:  # TorchScript exporter: emits native ONNX RNN/LSTM ops, small and fast
            torch.onnx.export(m, (x,), str(out), input_names=["x"], output_names=["y"],
                              dynamic_axes={"x": {0: "batch"}, "y": {0: "batch"}},
                              opset_version=17, dynamo=False)
        except Exception:
            batch = torch.export.Dim("batch", min=1, max=100000)
            torch.onnx.export(m, (x,), str(out), input_names=["x"], output_names=["y"],
                              dynamic_shapes={"x": {0: batch}}, dynamo=True)
    for extra in out.parent.glob(out.name + ".data"):
        raise RuntimeError(f"unexpected external data file {extra}")


def parity(pt: Path, cell: str, onnx_path: Path, n: int = 512) -> float:
    m = PriceRNN(cell)
    m.load_state_dict(torch.load(pt, weights_only=True))
    m.eval()
    rng = np.random.default_rng(0)
    # random-walk windows relative to the last day, like real inputs (scaled ~N(0,1) steps)
    steps = rng.normal(0, 1, (n, WINDOW)).cumsum(axis=1)
    X = (steps - steps[:, -1:])[..., None].astype(np.float32)
    X = np.concatenate([X, np.zeros((1, WINDOW, 1), np.float32)])
    with torch.no_grad():
        ref = m(torch.from_numpy(X)).numpy()
    got = OnnxPredictor(onnx_path)(X)
    one = OnnxPredictor(onnx_path)(X[:1])  # batch of 1, as in recursive forecasting
    return float(max(np.max(np.abs(ref - got)), np.max(np.abs(ref[:1] - one))))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=str(MODEL_DIR))
    p.add_argument("--only", default=None, help="model name prefix, e.g. universal or AAPL")
    p.add_argument("--tol", type=float, default=1e-4)
    a = p.parse_args()
    d = Path(a.dir)
    worst, bad = 0.0, []
    for pt in sorted(d.glob("*_rnn.pt")) + sorted(d.glob("*_lstm.pt")):
        name, cell = pt.stem.rsplit("_", 1)
        if a.only and name != a.only:
            continue
        out = pt.with_suffix(".onnx")
        export(pt, cell, out)
        diff = parity(pt, cell, out)
        worst = max(worst, diff)
        status = "ok" if diff <= a.tol else "FAIL"
        if diff > a.tol:
            bad.append(out.name)
        print(f"{out.name:28s} {out.stat().st_size / 1024:7.1f} KB  max |onnx - torch| = {diff:.2e}  {status}")
    if worst == 0.0 and not bad and not list(d.glob("*.onnx")):
        print("no models found", file=sys.stderr)
        return 1
    print(f"worst parity diff {worst:.2e} (tol {a.tol:g})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
