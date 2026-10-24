"""Two face detectors behind one interface: `detector.detect(image) -> list[Face]`.

- HaarDetector: Viola-Jones cascade (2001). Slides a window over an image
  pyramid and runs a chain of very cheap Haar-feature tests; most windows are
  rejected in the first few stages, which is why it is fast on a CPU. It only
  knows upright frontal faces and has no real confidence score, so we report
  the cascade's "level weight" (how strongly the last stage voted).
- YuNetDetector: a tiny CNN (~75k parameters) trained on WIDER Face, run via
  OpenCV's DNN module. Gives a real confidence score and 5 landmarks (eyes,
  nose tip, mouth corners), and handles pose, lighting and scale far better.

Images are BGR numpy arrays, as returned by cv2.imread.
"""

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

MODELS_DIR = Path(__file__).parent / "models"
# The classic 2023mar release first; the 2026may dynamic-shape re-export is a
# fallback for OpenCV 5's ONNX Runtime engine (we pin OpenCV 4.x, see README).
YUNET_FILES = ["face_detection_yunet_2023mar.onnx", "face_detection_yunet_2026may.onnx"]


@dataclass
class Face:
    x: int
    y: int
    w: int
    h: int
    score: float
    landmarks: list[tuple[int, int]] = field(default_factory=list)

    @property
    def box(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h


class HaarDetector:
    name = "Haar cascade"

    def __init__(self, scale_factor: float = 1.1, min_neighbors: int = 5, min_size: int = 30):
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self.cascade = cv2.CascadeClassifier(str(path))
        if self.cascade.empty():
            raise RuntimeError(f"could not load {path}")
        self.scale_factor = scale_factor
        self.min_neighbors = min_neighbors
        self.min_size = min_size

    def detect(self, image: np.ndarray) -> list[Face]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        gray = cv2.equalizeHist(gray)
        boxes, _, weights = self.cascade.detectMultiScale3(
            gray, scaleFactor=self.scale_factor, minNeighbors=self.min_neighbors,
            minSize=(self.min_size, self.min_size), outputRejectLevels=True)
        return [Face(int(x), int(y), int(w), int(h), float(s))
                for (x, y, w, h), s in zip(boxes, np.ravel(weights))]


class YuNetDetector:
    name = "YuNet (DNN)"

    def __init__(self, score_threshold: float = 0.6, nms_threshold: float = 0.3):
        self.score_threshold = score_threshold
        self.model = self._load(score_threshold, nms_threshold)

    @staticmethod
    def _load(score_threshold: float, nms_threshold: float):
        errors = []
        for name in YUNET_FILES:
            path = MODELS_DIR / name
            if not path.exists():
                continue
            try:
                return cv2.FaceDetectorYN.create(
                    str(path), "", (320, 320), score_threshold, nms_threshold, 5000)
            except cv2.error as e:
                errors.append(f"{name}: {e.msg.strip()}")
        raise FileNotFoundError(
            "No usable YuNet model in models/. Run: .venv/bin/python download_models.py"
            + ("\n" + "\n".join(errors) if errors else ""))

    def detect(self, image: np.ndarray) -> list[Face]:
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        h, w = image.shape[:2]
        self.model.setInputSize((w, h))
        self.model.setScoreThreshold(self.score_threshold)
        _, rows = self.model.detect(image)
        faces = []
        for r in rows if rows is not None else []:
            x, y, bw, bh = (int(round(v)) for v in r[:4])
            marks = [(int(r[4 + 2 * i]), int(r[5 + 2 * i])) for i in range(5)]
            faces.append(Face(x, y, bw, bh, float(r[14]), marks))
        return faces


def make_detector(kind: str, **params):
    """kind: 'haar' or 'dnn'. Extra keyword params go to the detector."""
    if kind == "haar":
        return HaarDetector(**params)
    if kind == "dnn":
        return YuNetDetector(**params)
    raise ValueError(f"unknown detector {kind!r} (use 'haar' or 'dnn')")
