"""Benchmark speed (CPU vs Apple MPS) and sanity-check accuracy on coco8.

Speed: each sample image is run several times after a warm-up (the first MPS
call compiles kernels and is far slower). We report the model's own
inference time and the full wall-clock time including pre/post-processing.

Accuracy: coco8 is the 8-image subset of COCO that Ultralytics auto-downloads.
Its val split is just 4 images / 17 boxes,
so it only proves the pipeline is wired correctly; real mAP needs COCO val2017
(5,000 images). Treat the coco8 number as a smoke test, not a score.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import torch

from config import DEFAULT_MODEL, OUTPUTS_DIR, RUNS_DIR, SAMPLES_DIR
from detector import Detector, timed


def bench_speed(model: str, device: str, runs: int, warmup: int = 3) -> dict:
    det = Detector(model, device)
    images = sorted(SAMPLES_DIR.glob("*.jpg"))
    wall, infer = [], []
    for img in images:
        path = str(img)
        for _ in range(warmup):
            det.detect(path)
        for _ in range(runs):
            r, ms = timed(det.detect, path)
            wall.append(ms)
            infer.append(r.inference_ms)
    w, i = statistics.median(wall), statistics.median(infer)
    return {"device": device, "images": len(images), "runs_per_image": runs,
            "inference_ms": round(i, 2), "end_to_end_ms": round(w, 2), "fps": round(1000 / w, 1)}


def validate(model: str, device: str) -> dict:
    det = Detector(model, device)
    m = det.model.val(data="coco8.yaml", device=device, imgsz=640, plots=False,
                      project=str(RUNS_DIR), name="val_coco8", exist_ok=True, verbose=False)
    return {"dataset": "coco8 val split (4 images, 17 boxes)", "device": device,
            "mAP50": round(float(m.box.map50), 3), "mAP50-95": round(float(m.box.map), 3),
            "precision": round(float(m.box.mp), 3), "recall": round(float(m.box.mr), 3)}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--runs", type=int, default=20, help="timed runs per image")
    p.add_argument("--skip-val", action="store_true")
    args = p.parse_args()

    devices = ["cpu"] + (["mps"] if torch.backends.mps.is_available() else [])
    speed = [bench_speed(args.model, d, args.runs) for d in devices]

    print(f"\nSpeed - {args.model}, median over {speed[0]['images']} images x {args.runs} runs")
    print(f"{'device':<8}{'inference ms':>14}{'end-to-end ms':>16}{'FPS':>8}")
    for s in speed:
        print(f"{s['device']:<8}{s['inference_ms']:>14.1f}{s['end_to_end_ms']:>16.1f}{s['fps']:>8.1f}")

    results = {"model": args.model, "torch": torch.__version__, "speed": speed}
    if not args.skip_val:
        v = validate(args.model, devices[-1])
        results["validation"] = v
        print(f"\nValidation on {v['dataset']} ({v['device']}): mAP50={v['mAP50']}  "
              f"mAP50-95={v['mAP50-95']}  P={v['precision']}  R={v['recall']}")
        print("Note: coco8 is a sanity check only - far too small for a meaningful mAP.")

    OUTPUTS_DIR.mkdir(exist_ok=True)
    out = OUTPUTS_DIR / f"eval_{Path(args.model).stem}.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
