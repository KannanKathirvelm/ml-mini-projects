"""Command-line object detection for images, videos and webcams.

Examples:
    python detect.py --source samples/bus.jpg --save
    python detect.py --source samples/pan_demo.mp4 --track --classes person bus --save
    python detect.py --source 0            # webcam, press q to quit
"""
from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

import cv2

from config import DEFAULT_MODEL, OUTPUTS_DIR
from detector import Detector, video_writer
from line_counter import LineCounter

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args():
    p = argparse.ArgumentParser(description="YOLO object detection (80 COCO classes)")
    p.add_argument("--source", required=True, help="image, folder, video file, or webcam index (0)")
    p.add_argument("--model", default=DEFAULT_MODEL, help="yolo11n.pt / yolo11s.pt / yolo11m.pt or a path")
    p.add_argument("--conf", type=float, default=0.25, help="confidence threshold")
    p.add_argument("--iou", type=float, default=0.7, help="NMS IoU threshold")
    p.add_argument("--classes", nargs="+", help="only keep these classes, e.g. person car")
    p.add_argument("--device", help="cpu / mps / cuda:0 (default: mps if available)")
    p.add_argument("--track", action="store_true", help="video: ByteTrack IDs + line-crossing counter")
    p.add_argument("--line", default="v",
                   help="counting line: 'v' (vertical centre), 'h' (horizontal centre) or x1,y1,x2,y2")
    p.add_argument("--save", action="store_true", help="write annotated output to outputs/")
    p.add_argument("--show", action="store_true", help="display a window (always on for webcam)")
    return p.parse_args()


def make_line(spec: str, w: int, h: int) -> LineCounter:
    if spec == "v":
        return LineCounter.vertical_center(w, h)
    if spec == "h":
        return LineCounter.horizontal_center(w, h)
    x1, y1, x2, y2 = (int(v) for v in spec.split(","))
    return LineCounter((x1, y1), (x2, y2))


def fmt_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{k}: {v}" for k, v in counts.items()) or "nothing detected"


def run_images(det: Detector, paths: list[Path], args) -> None:
    for path in paths:
        r = det.detect(str(path), args.conf, args.iou, args.classes)
        print(f"{path.name}: {fmt_counts(r.counts)}  ({r.inference_ms:.1f} ms inference)")
        for d in r.detections:
            print(f"   {d.cls_name:<14} {d.conf:.2f}  box={[round(v) for v in d.box]}")
        if args.save:
            out = OUTPUTS_DIR / f"{path.stem}_det{path.suffix}"
            cv2.imwrite(str(out), r.annotated)
            print(f"   saved -> {out}")
        if args.show:
            cv2.imshow("detections", r.annotated)
            cv2.waitKey(0)


def run_stream(det: Detector, source, args, is_webcam: bool) -> None:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"Could not open source {source!r}")
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_in = cap.get(cv2.CAP_PROP_FPS) or 30
    counter = make_line(args.line, w, h) if args.track else None
    show = args.show or is_webcam

    writer = None
    if args.save:
        name = "webcam" if is_webcam else Path(source).stem
        out = OUTPUTS_DIR / f"{name}_{'track' if args.track else 'det'}.mp4"
        writer = video_writer(out, fps_in, (w, h))

    peak = Counter()  # max simultaneous count per class, a useful summary without tracking
    frames, t_start, fps = 0, time.perf_counter(), 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t0 = time.perf_counter()
        if args.track:
            r = det.track(frame, args.conf, args.iou, args.classes)
            counter.update(r.detections)
        else:
            r = det.detect(frame, args.conf, args.iou, args.classes)
        inst_fps = 1 / max(time.perf_counter() - t0, 1e-6)
        fps = inst_fps if frames == 0 else 0.9 * fps + 0.1 * inst_fps  # smoothed for display
        for k, v in r.counts.items():
            peak[k] = max(peak[k], v)

        img = r.annotated
        if counter:
            counter.draw(img)
        cv2.putText(img, f"FPS {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
        if writer:
            writer.write(img)
        if show:
            cv2.imshow("YOLO detection (q to quit)", img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        frames += 1

    cap.release()
    if writer:
        writer.release()
        print(f"saved -> {out}")
    if show:
        cv2.destroyAllWindows()
    elapsed = time.perf_counter() - t_start
    print(f"{frames} frames in {elapsed:.1f}s ({frames / max(elapsed, 1e-6):.1f} FPS end-to-end)")
    print(f"peak objects in one frame: {fmt_counts(dict(peak.most_common()))}")
    if counter:
        print(f"line crossings: {fmt_counts(counter.totals)} "
              f"(forward {dict(counter.forward)}, backward {dict(counter.backward)})")


def main():
    args = parse_args()
    OUTPUTS_DIR.mkdir(exist_ok=True)
    det = Detector(args.model, args.device)
    print(f"model={args.model} device={det.device} conf={args.conf} iou={args.iou} classes={args.classes or 'all'}")

    src = args.source
    if src.isdigit():
        run_stream(det, int(src), args, is_webcam=True)
        return
    path = Path(src)
    if path.is_dir():
        run_images(det, sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_EXTS), args)
    elif path.suffix.lower() in IMAGE_EXTS:
        run_images(det, [path], args)
    else:
        run_stream(det, str(path), args, is_webcam=False)


if __name__ == "__main__":
    main()
