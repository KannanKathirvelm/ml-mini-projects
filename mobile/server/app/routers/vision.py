"""Projects 06 (face detection) and 07 (YOLO11 object detection)."""
from __future__ import annotations

import threading
import time
from functools import lru_cache

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from .. import loader
from ..imaging import read_image, to_b64_jpeg
from ..settings import OBJECTS_DEVICE, SLIM

faces_router = APIRouter(prefix="/api/faces", tags=["faces"])
objects_router = APIRouter(prefix="/api/objects", tags=["objects"])


def _bool(v: str | bool | None, name: str) -> bool:
    if isinstance(v, bool):
        return v
    s = (v or "false").strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off", ""):
        return False
    raise HTTPException(400, f"'{name}' must be true or false.")


def _float(v: str | float | None, name: str, default: float, lo: float, hi: float) -> float:
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    try:
        x = float(v)
    except ValueError:
        raise HTTPException(400, f"'{name}' must be a number between {lo} and {hi}.") from None
    if not lo <= x <= hi:
        raise HTTPException(400, f"'{name}' must be between {lo} and {hi}.")
    return x


# ---------------------------------------------------------------------- faces
FACE_DETECTORS = {"yunet": ("dnn", "YuNet"), "haar": ("haar", "Haar")}


def faces_ns():
    return loader.get("faces", ["detectors", "draw"])


@lru_cache(maxsize=None)
def face_detector(kind: str):
    """One detector instance per kind, plus a lock (OpenCV detectors keep state)."""
    return faces_ns().detectors.make_detector(FACE_DETECTORS[kind][0]), threading.Lock()


@faces_router.post("/detect")
async def detect_faces(image: UploadFile | None = File(None), detector: str = Form("yunet"),
                       blur: str = Form("false"), threshold: str | None = Form(None)):
    kind = (detector or "yunet").strip().lower()
    if kind not in ("yunet", "haar", "both"):
        raise HTTPException(400, f"Unknown detector '{detector}'. Use yunet, haar or both.")
    do_blur = _bool(blur, "blur")
    thr = _float(threshold, "threshold", 0.6, 0.0, 1.0)
    img = await read_image(image)
    return await run_in_threadpool(_detect_faces, img, kind, do_blur, thr)


def _detect_faces(img, kind: str, do_blur: bool, thr: float) -> dict:
    draw = faces_ns().draw
    results = []
    for k in (["yunet", "haar"] if kind == "both" else [kind]):
        det, lock = face_detector(k)
        with lock:
            if k == "yunet":
                det.score_threshold = thr
            t0 = time.perf_counter()
            faces = det.detect(img)
            ms = (time.perf_counter() - t0) * 1000
        annotated = draw.annotate(img, faces, blur=do_blur, label=FACE_DETECTORS[k][1])
        results.append({
            "detector": k, "count": len(faces), "time_ms": round(ms, 1),
            "faces": [{"x": f.x, "y": f.y, "w": f.w, "h": f.h, "score": round(f.score, 3),
                       "landmarks": [list(p) for p in f.landmarks] if k == "yunet" else None}
                      for f in faces],
            "image_base64": to_b64_jpeg(annotated),
        })
    return {"results": results}


# -------------------------------------------------------------------- objects
YOLO_MODELS = ["yolo11n.pt", "yolo11s.pt"]


def objects_ns():
    return loader.get("objects", ["config", "detector"])


def yolo(model: str):
    """Full profile: ultralytics on the .pt weights. Slim: ONNX Runtime on the exported .onnx
    (same boxes, scores and drawing; see app/yolo_onnx.py)."""
    return _yolo_onnx(model) if SLIM else _yolo_torch(model)


@lru_cache(maxsize=None)
def _yolo_torch(model: str):
    return objects_ns().detector.Detector(model, device=OBJECTS_DEVICE), threading.Lock()


@lru_cache(maxsize=1)  # 512 MB budget: keep only the most recently used YOLO session
def _yolo_onnx(model: str):
    import gc

    from ..yolo_onnx import OnnxYolo

    gc.collect()
    path = loader.project_dir("objects") / "weights" / model.replace(".pt", ".onnx")
    return OnnxYolo(path), threading.Lock()


@lru_cache(maxsize=1)
def _class_names() -> tuple[str, ...]:
    names = yolo(YOLO_MODELS[0])[0].names
    return tuple(names[i] for i in sorted(names))


@objects_router.get("/classes")
def classes():
    return {"classes": list(_class_names()), "models": YOLO_MODELS}


@objects_router.post("/detect")
async def detect_objects(image: UploadFile | None = File(None), conf: str | None = Form(None),
                         iou: str | None = Form(None), classes: str = Form(""),
                         model: str = Form("yolo11n.pt")):
    model = (model or YOLO_MODELS[0]).strip()
    if model not in YOLO_MODELS:
        raise HTTPException(400, f"Unknown model '{model}'. Use one of {YOLO_MODELS}.")
    c = _float(conf, "conf", 0.25, 0.0, 1.0)
    i = _float(iou, "iou", 0.7, 0.0, 1.0)
    wanted = [s.strip() for s in (classes or "").split(",") if s.strip()] or None
    det, lock = yolo(model)
    try:
        det.class_ids(wanted)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    img = await read_image(image)
    return await run_in_threadpool(_detect_objects, det, lock, img, c, i, wanted)


def _detect_objects(det, lock, img, c: float, i: float, wanted) -> dict:
    with lock:
        r = det.detect(img, conf=c, iou=i, classes=wanted)
    return {
        "count": len(r.detections), "time_ms": round(r.inference_ms, 1), "counts": r.counts,
        "detections": [{"cls": d.cls_name, "conf": round(d.conf, 3),
                        "box": [round(v, 1) for v in d.box]} for d in r.detections],
        "image_base64": to_b64_jpeg(r.annotated),
    }
