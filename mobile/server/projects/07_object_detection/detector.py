"""Thin wrapper around an Ultralytics YOLO model.

The CLI, the benchmark and the Streamlit app all need the same thing: "give me
boxes, counts and an annotated frame for these thresholds". Keeping that in one
small class means the three front-ends never touch ultralytics directly.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

import config  # noqa: F401  (sets ultralytics paths before import)
from ultralytics import YOLO


@dataclass
class Detection:
    cls_name: str
    conf: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels
    track_id: int | None = None


@dataclass
class FrameResult:
    annotated: np.ndarray  # BGR image with boxes drawn
    detections: list[Detection] = field(default_factory=list)
    inference_ms: float = 0.0

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(d.cls_name for d in self.detections).most_common())


class Detector:
    def __init__(self, model: str = config.DEFAULT_MODEL, device: str | None = None):
        self.device = config.pick_device(device)
        self.model = YOLO(config.weights_path(model))
        self.names: dict[int, str] = self.model.names

    def class_ids(self, class_names: list[str] | None) -> list[int] | None:
        """Map names like ['person', 'car'] to COCO ids; None means all classes."""
        if not class_names:
            return None
        lookup = {n.lower(): i for i, n in self.names.items()}
        unknown = [c for c in class_names if c.lower() not in lookup]
        if unknown:
            raise ValueError(f"Unknown class(es): {unknown}. Valid: {sorted(lookup)}")
        return [lookup[c.lower()] for c in class_names]

    def detect(self, image, conf=0.25, iou=0.7, classes=None) -> FrameResult:
        """Run detection on a BGR array or image path."""
        r = self.model.predict(
            image, conf=conf, iou=iou, classes=self.class_ids(classes),
            device=self.device, verbose=False,
        )[0]
        return self._wrap(r)

    def track(self, frame, conf=0.25, iou=0.7, classes=None, tracker="bytetrack.yaml") -> FrameResult:
        """Detect + ByteTrack on one video frame; IDs persist across calls."""
        r = self.model.track(
            frame, conf=conf, iou=iou, classes=self.class_ids(classes),
            device=self.device, tracker=tracker, persist=True, verbose=False,
        )[0]
        return self._wrap(r)

    def reset_tracker(self) -> None:
        """Forget track IDs, e.g. before starting a new video."""
        for t in getattr(self.model.predictor, "trackers", None) or []:
            t.reset()

    def _wrap(self, r) -> FrameResult:
        dets = []
        b = r.boxes
        if b is not None and len(b):
            ids = b.id.int().tolist() if b.id is not None else [None] * len(b)
            for xyxy, c, k, tid in zip(b.xyxy.tolist(), b.conf.tolist(), b.cls.int().tolist(), ids):
                dets.append(Detection(self.names[k], float(c), tuple(xyxy), tid))
        return FrameResult(annotated=r.plot(), detections=dets, inference_ms=r.speed["inference"])


def timed(fn, *args, **kwargs):
    """Return (result, wall-clock ms) - includes pre/post-processing, unlike inference_ms."""
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return out, (time.perf_counter() - t0) * 1000


def video_writer(path, fps: float, size: tuple[int, int]):
    """H.264 ('avc1') plays in browsers and QuickTime; fall back to mp4v if unavailable."""
    import cv2

    for codec in ("avc1", "mp4v"):
        w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, size)
        if w.isOpened():
            return w
    raise RuntimeError(f"Could not open a video writer for {path}")
