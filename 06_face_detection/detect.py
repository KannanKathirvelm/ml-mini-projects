"""Command-line face detection on an image, a video file, or the webcam.

Examples:
    detect.py --image samples/lena.jpg --detector dnn --out outputs/lena.jpg
    detect.py --video clip.mp4 --detector haar --blur --out outputs/clip.mp4
    detect.py --webcam --detector dnn          # press q to quit
"""

import argparse
import time
from pathlib import Path

import cv2

from detectors import make_detector
from draw import _text, annotate


def build_detector(args):
    if args.detector == "haar":
        return make_detector("haar", scale_factor=args.scale_factor, min_neighbors=args.min_neighbors)
    return make_detector("dnn", score_threshold=args.threshold)


def run_image(det, args) -> None:
    image = cv2.imread(args.image)
    if image is None:
        raise SystemExit(f"could not read image {args.image}")
    t0 = time.perf_counter()
    faces = det.detect(image)
    ms = (time.perf_counter() - t0) * 1000
    print(f"{det.name}: {len(faces)} face(s) in {ms:.1f} ms")
    for i, f in enumerate(faces, 1):
        print(f"  #{i} box=(x={f.x}, y={f.y}, w={f.w}, h={f.h}) score={f.score:.2f}")
    out = annotate(image, faces, blur=args.blur, label=det.name)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(args.out, out)
        print(f"saved {args.out}")
    if args.show:
        cv2.imshow("faces", out)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


def run_stream(det, args) -> None:
    """Shared loop for video files and the webcam."""
    source = args.camera if args.webcam else args.video
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"could not open {'camera ' + str(source) if args.webcam else source}")
    show = args.webcam or args.show
    writer, frames, total_faces, fps = None, 0, 0, 0.0
    t_start = prev = time.perf_counter()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            faces = det.detect(frame)
            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 * (1 / max(now - prev, 1e-6)) if frames else 1 / max(now - prev, 1e-6)
            prev = now
            frames += 1
            total_faces += len(faces)
            out = annotate(frame, faces, blur=args.blur, label=det.name)
            _text(out, f"{fps:.1f} FPS", (8, out.shape[0] - 12), 0.6)
            if args.out:
                if writer is None:
                    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25
                    writer = cv2.VideoWriter(args.out, cv2.VideoWriter_fourcc(*"mp4v"),
                                             src_fps, (out.shape[1], out.shape[0]))
                writer.write(out)
            if show:
                cv2.imshow("faces (q to quit)", out)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()
    secs = time.perf_counter() - t_start
    print(f"{det.name}: {frames} frames, {total_faces} detections, "
          f"{frames / max(secs, 1e-6):.1f} FPS average")
    if args.out and frames:
        print(f"saved {args.out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Face detection with Haar cascade or YuNet (DNN).")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="path to an image")
    src.add_argument("--video", help="path to a video file")
    src.add_argument("--webcam", action="store_true", help="use the webcam (q to quit)")
    p.add_argument("--camera", type=int, default=0, help="webcam index (default 0)")
    p.add_argument("--detector", choices=["haar", "dnn"], default="dnn")
    p.add_argument("--blur", action="store_true", help="anonymise detected faces")
    p.add_argument("--out", help="save annotated image / video here")
    p.add_argument("--show", action="store_true", help="open a window for --image/--video")
    p.add_argument("--threshold", type=float, default=0.6, help="DNN confidence threshold")
    p.add_argument("--scale-factor", type=float, default=1.1, help="Haar pyramid step (>1)")
    p.add_argument("--min-neighbors", type=int, default=5, help="Haar overlapping hits needed")
    args = p.parse_args()

    det = build_detector(args)
    if args.image:
        run_image(det, args)
    else:
        run_stream(det, args)


if __name__ == "__main__":
    main()
