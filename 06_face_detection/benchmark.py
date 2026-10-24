"""Benchmark Haar vs YuNet on the bundled samples: speed, counts, precision/recall.

Speed: one warm-up call, then the median of N timed calls per image (single
thread via cv2.setNumThreads(1) by default, so numbers are comparable across
machines with different core counts; --threads 0 uses all cores).

Accuracy: samples/labels.json holds hand-verified face boxes for 7 images
(76 faces). A detection is a true positive if it overlaps an unmatched label
with IoU >= 0.3 (lenient, because Haar draws square boxes and YuNet tall ones).
This is a tiny, mostly grayscale, frontal-face sample: it shows the trend, it
is not a substitute for WIDER Face / FDDB.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import cv2

from detectors import make_detector

SAMPLES = Path(__file__).parent / "samples"


def iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    return inter / (aw * ah + bw * bh - inter) if inter else 0.0


def match(dets, gts, ignore, thr=0.3):
    """Greedy matching, highest score first. Returns (tp, fp, fn)."""
    unmatched = list(gts)
    tp = fp = 0
    for d in sorted(dets, key=lambda f: -f.score):
        best = max(unmatched, key=lambda g: iou(d.box, g), default=None)
        if best is not None and iou(d.box, best) >= thr:
            unmatched.remove(best)
            tp += 1
        elif not any(iou(d.box, g) >= thr for g in ignore):
            fp += 1
    return tp, fp, len(unmatched)


def time_ms(det, image, repeats: int) -> float:
    det.detect(image)  # warm-up (first call allocates buffers)
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        det.detect(image)
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repeats", type=int, default=20)
    p.add_argument("--threads", type=int, default=1, help="OpenCV threads (0 = OpenCV default)")
    p.add_argument("--threshold", type=float, default=0.6, help="YuNet confidence threshold")
    p.add_argument("--min-neighbors", type=int, default=5)
    p.add_argument("--scale-factor", type=float, default=1.1)
    args = p.parse_args()
    if args.threads:
        cv2.setNumThreads(args.threads)

    labels = json.loads((SAMPLES / "labels.json").read_text())
    detectors = {
        "haar": make_detector("haar", scale_factor=args.scale_factor, min_neighbors=args.min_neighbors),
        "dnn": make_detector("dnn", score_threshold=args.threshold),
    }
    images = sorted(f for f in SAMPLES.iterdir() if f.suffix in {".png", ".jpg"})
    totals = {k: [0, 0, 0, []] for k in detectors}  # tp, fp, fn, times

    print(f"OpenCV {cv2.__version__}, threads={args.threads or 'default'}, repeats={args.repeats}, "
          f"YuNet threshold={args.threshold}, Haar scaleFactor={args.scale_factor} "
          f"minNeighbors={args.min_neighbors}\n")
    print("| Image | Size | True faces | Haar found | Haar TP/FP | Haar ms | YuNet found | YuNet TP/FP | YuNet ms |")
    print("|---|---|---|---|---|---|---|---|---|")
    for path in images:
        image = cv2.imread(str(path))
        lab = labels.get(path.name)
        row = [path.name, f"{image.shape[1]}x{image.shape[0]}", str(len(lab["faces"])) if lab else "n/a"]
        for key, det in detectors.items():
            faces = det.detect(image)
            ms = time_ms(det, image, args.repeats)
            totals[key][3].append(ms)
            if lab:
                tp, fp, fn = match(faces, lab["faces"], lab["ignore"])
                for i, v in enumerate((tp, fp, fn)):
                    totals[key][i] += v
                row += [str(len(faces)), f"{tp}/{fp}", f"{ms:.1f}"]
            else:
                row += [str(len(faces)), "n/a", f"{ms:.1f}"]
        print("| " + " | ".join(row) + " |")

    print("\n| Detector | Faces (labelled) | TP | FP | FN | Precision | Recall | Mean time / image |")
    print("|---|---|---|---|---|---|---|---|")
    n_true = sum(len(v["faces"]) for k, v in labels.items() if not k.startswith("_"))
    for key, (tp, fp, fn, times) in totals.items():
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn) if tp + fn else 0
        print(f"| {detectors[key].name} | {n_true} | {tp} | {fp} | {fn} | {prec:.1%} | {rec:.1%} | "
              f"{statistics.mean(times):.1f} ms |")


if __name__ == "__main__":
    main()
