"""YOLO11 object detection with ONNX Runtime + OpenCV only (slim profile: no torch, no ultralytics).

Reproduces what `ultralytics.YOLO.predict` does for a detection model, so the API response is the
same as the full server's:

1. letterbox: resize keeping the aspect ratio so the long side is 640, then pad to a multiple of
   32 with grey (114) borders (ultralytics `LetterBox(auto=True)`; the ONNX files are exported
   with dynamic height/width for exactly this),
2. BGR -> RGB, 0-1 float, NCHW,
3. decode the (1, 84, N) output: xywh boxes + 80 class scores, best class per box,
   confidence filter, optional class filter,
4. class-aware greedy NMS (boxes offset by class id * 7680, like ultralytics + torchvision),
   at most 300 detections,
5. undo the letterbox and clip to the image,
6. draw boxes and "name 0.93" labels with the ultralytics colour palette.

Export (done once, files committed): see scripts/export_yolo_onnx.py.
"""
from __future__ import annotations

import ast
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

MAX_WH = 7680
MAX_NMS = 30000
MAX_DET = 300
PALETTE_HEX = ("042AFF", "0BDBEB", "F3F3F3", "00DFB7", "111F68", "FF6FDD", "FF444F", "CCED00",
               "00F344", "BD00FF", "00B4FF", "DD00BA", "00FFFF", "26C000", "01FFB3", "7D24FF",
               "7B0068", "FF1B6C", "FC6D2F", "A2FF0B")
PALETTE_RGB = [tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) for h in PALETTE_HEX]
# ultralytics Annotator: text colour per box colour (in BGR, as drawn)
DARK = {(235, 219, 11), (243, 243, 243), (183, 223, 0), (221, 111, 255), (0, 237, 204),
        (68, 243, 0), (255, 255, 0), (179, 255, 1), (11, 255, 162)}
LIGHT = {(255, 42, 4), (79, 68, 255), (255, 0, 189), (255, 180, 0), (186, 0, 221), (0, 192, 38),
         (255, 36, 125), (104, 0, 123), (108, 27, 255), (47, 109, 252), (104, 31, 17)}


@dataclass
class Detection:
    cls_name: str
    conf: float
    box: tuple[float, float, float, float]
    track_id: int | None = None


@dataclass
class FrameResult:
    annotated: np.ndarray
    detections: list[Detection] = field(default_factory=list)
    inference_ms: float = 0.0

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(d.cls_name for d in self.detections).most_common())


def letterbox(img: np.ndarray, size: int = 640, stride: int = 32):
    """Returns (padded image, gain, (pad_left, pad_top)), like ultralytics LetterBox(auto=True)."""
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    new_w, new_h = int(round(w * r)), int(round(h * r))
    dw, dh = (size - new_w) % stride / 2, (size - new_h) % stride / 2
    if (w, h) != (new_w, new_h):
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return img, r, (left, top)


def nms(boxes: np.ndarray, iou: float) -> np.ndarray:
    """Greedy NMS on score-sorted xyxy boxes (same rule as torchvision.ops.nms: drop IoU > iou)."""
    x1, y1, x2, y2 = boxes.T
    area = (x2 - x1) * (y2 - y1)
    order, keep = np.arange(len(boxes)), []
    while len(order):
        i, rest = order[0], order[1:]
        keep.append(i)
        w = np.clip(np.minimum(x2[i], x2[rest]) - np.maximum(x1[i], x1[rest]), 0, None)
        h = np.clip(np.minimum(y2[i], y2[rest]) - np.maximum(y1[i], y1[rest]), 0, None)
        inter = w * h
        order = rest[inter / (area[i] + area[rest] - inter + 1e-9) <= iou]
    return np.array(keep, dtype=int)


def decode(out: np.ndarray, conf: float, iou: float, class_ids: list[int] | None):
    """(1, 4 + nc, N) raw output -> (boxes xyxy in letterbox coords, scores, class ids)."""
    p = out[0].T  # (N, 4 + nc)
    scores_all = p[:, 4:]
    cls = scores_all.argmax(1)
    score = scores_all[np.arange(len(p)), cls]
    keep = score > conf
    if class_ids is not None:
        keep &= np.isin(cls, class_ids)
    p, cls, score = p[keep], cls[keep], score[keep]
    if not len(p):
        return np.zeros((0, 4), np.float32), np.zeros(0, np.float32), np.zeros(0, int)
    order = np.argsort(-score)[:MAX_NMS]
    p, cls, score = p[order], cls[order], score[order]
    xy, wh = p[:, :2], p[:, 2:4]
    boxes = np.concatenate([xy - wh / 2, xy + wh / 2], axis=1)
    idx = nms(boxes + (cls[:, None] * MAX_WH), iou)[:MAX_DET]
    return boxes[idx], score[idx], cls[idx]


def draw(img: np.ndarray, dets: list[tuple[np.ndarray, float, int]], names: dict[int, str]) -> np.ndarray:
    im = np.ascontiguousarray(img.copy())
    lw = max(round(sum(im.shape) / 2 * 0.003), 2)
    tf, sf = max(lw - 1, 1), lw / 3
    for box, score, c in reversed(dets):  # ultralytics draws the lowest-confidence box first
        r, g, b = PALETTE_RGB[int(c) % len(PALETTE_RGB)]
        color = (b, g, r)
        txt = (104, 31, 17) if color in DARK else (255, 255, 255)
        p1, p2 = (int(box[0]), int(box[1])), (int(box[2]), int(box[3]))
        cv2.rectangle(im, p1, p2, color, thickness=lw, lineType=cv2.LINE_AA)
        label = f"{names[int(c)]} {score:.2f}"
        w, h = cv2.getTextSize(label, 0, fontScale=sf, thickness=tf)[0]
        h += 3
        outside = p1[1] >= h
        if p1[0] > im.shape[1] - w:
            p1 = (im.shape[1] - w, p1[1])
        q2 = (p1[0] + w, p1[1] - h if outside else p1[1] + h)
        cv2.rectangle(im, p1, q2, color, -1, cv2.LINE_AA)
        cv2.putText(im, label, (p1[0], p1[1] - 2 if outside else p1[1] + h - 1), 0, sf, txt,
                    thickness=tf, lineType=cv2.LINE_AA)
    return im


class OnnxYolo:
    """Same public surface as projects/07_object_detection/detector.Detector."""

    def __init__(self, path: str | Path, imgsz: int = 640, threads: int = 1):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        so.log_severity_level = 3
        # memory: no arena growth spikes between differently sized images
        so.enable_cpu_mem_arena = False
        so.enable_mem_pattern = False  # input sizes vary (rectangular letterbox)
        self.session = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name
        meta = self.session.get_modelmeta().custom_metadata_map
        self.names: dict[int, str] = {int(k): v for k, v in ast.literal_eval(meta["names"]).items()}
        self.imgsz = imgsz

    def class_ids(self, class_names: list[str] | None) -> list[int] | None:
        if not class_names:
            return None
        lookup = {n.lower(): i for i, n in self.names.items()}
        unknown = [c for c in class_names if c.lower() not in lookup]
        if unknown:
            raise ValueError(f"Unknown class(es): {unknown}. Valid: {sorted(lookup)}")
        return [lookup[c.lower()] for c in class_names]

    def detect(self, image, conf=0.25, iou=0.7, classes=None) -> FrameResult:
        img = cv2.imread(str(image)) if isinstance(image, (str, Path)) else image
        lb, gain, (pl, pt) = letterbox(img, self.imgsz)
        x = np.ascontiguousarray(lb[:, :, ::-1].transpose(2, 0, 1))[None].astype(np.float32) / 255.0
        t0 = time.perf_counter()
        out = self.session.run(None, {self.input: x})[0]
        ms = (time.perf_counter() - t0) * 1000
        boxes, scores, cls = decode(out, conf, iou, self.class_ids(classes))
        h, w = img.shape[:2]
        if len(boxes):
            boxes[:, [0, 2]] = ((boxes[:, [0, 2]] - pl) / gain).clip(0, w)
            boxes[:, [1, 3]] = ((boxes[:, [1, 3]] - pt) / gain).clip(0, h)
        triples = list(zip(boxes, scores.tolist(), cls.tolist()))
        dets = [Detection(self.names[int(c)], float(s), tuple(float(v) for v in b)) for b, s, c in triples]
        return FrameResult(annotated=draw(img, triples, self.names), detections=dets, inference_ms=ms)
