"""ONNX Runtime wrapper for the exported RNN / LSTM (no torch needed).

    fn = OnnxPredictor("models/universal_lstm.onnx")
    y = fn(X)          # X: float32 (batch, window, 1) -> scaled log returns (batch,)

Used by the slim server (`SERVER_PROFILE=slim`) together with universal.forecast/backtest.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


class OnnxPredictor:
    def __init__(self, path: str | Path, threads: int = 1):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        so.log_severity_level = 3
        self.path = Path(path)
        self.session = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name

    def __call__(self, X: np.ndarray) -> np.ndarray:
        X = np.ascontiguousarray(X, dtype=np.float32)
        if len(X) == 0:
            return np.zeros(0, dtype=np.float32)
        out = [self.session.run(None, {self.input: X[i:i + 1024]})[0].reshape(-1)
               for i in range(0, len(X), 1024)]
        return np.concatenate(out)
