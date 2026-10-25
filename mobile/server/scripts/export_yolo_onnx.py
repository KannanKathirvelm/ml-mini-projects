"""Export the YOLO11 checkpoints to ONNX for the slim (torch-free) server and check parity.

    .venv/bin/python scripts/export_yolo_onnx.py       # needs the full venv (ultralytics, torch, onnx)

Writes projects/07_object_detection/weights/yolo11{n,s}.onnx (opset 17, dynamic H/W so the
ultralytics rectangular letterbox can be reproduced exactly), then runs both images in samples/
through ultralytics (.pt) and app/yolo_onnx.py (.onnx) and fails if the classes, counts or boxes
(> 2 px) differ. The ONNX files are committed; this only needs re-running if the weights change.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
ROOT = SERVER / "projects" / "07_object_detection"
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".ultralytics"))
os.environ.setdefault("YOLO_OFFLINE", "1")
sys.path.insert(0, str(SERVER))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from ultralytics import YOLO  # noqa: E402

from app.yolo_onnx import OnnxYolo  # noqa: E402

MODELS = ["yolo11n", "yolo11s"]


def main() -> int:
    bad = 0
    for m in MODELS:
        pt = ROOT / "weights" / f"{m}.pt"
        out = Path(YOLO(str(pt)).export(format="onnx", imgsz=640, dynamic=True, simplify=False,
                                        opset=17, device="cpu"))
        size_mb = out.stat().st_size / 1e6
        print(f"{out.name}: {size_mb:.1f} MB")
        if size_mb > 50:
            print("  too large for plain git (> 50 MB)")
            bad += 1
        ref, onx = YOLO(str(pt)), OnnxYolo(out)
        for img_path in sorted((ROOT / "samples").glob("*.jpg")):
            img = cv2.imread(str(img_path))
            r = ref.predict(img, conf=0.25, iou=0.7, device="cpu", verbose=False)[0]
            o = onx.detect(img, conf=0.25, iou=0.7)
            rn = sorted(ref.names[int(c)] for c in r.boxes.cls)
            on = sorted(d.cls_name for d in o.detections)
            diff = (float(np.abs(r.boxes.xyxy.numpy() - np.array([d.box for d in o.detections])).max())
                    if rn == on and rn else 0.0)
            ok = rn == on and diff <= 2.0
            bad += not ok
            print(f"  {img_path.name}: ultralytics {len(rn)} / onnx {len(on)} detections, "
                  f"max box diff {diff:.3f} px  {'ok' if ok else 'MISMATCH'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
