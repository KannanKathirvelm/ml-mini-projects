"""Download the YuNet face-detector weights from the official OpenCV model zoo.

Why a script instead of committing the weights: the .onnx files are binary blobs
that belong to opencv_zoo (MIT licence). Fetching them from the source keeps the
repo small and makes the provenance obvious.

Each file is checked against the SHA-256 and size published in opencv_zoo's
Git-LFS pointer files, then test-loaded with cv2.FaceDetectorYN. Nothing that is
downloaded is executed; ONNX files are just weights read by OpenCV.

Two variants are fetched:
- 2023mar: the classic YuNet release (fixed input shape).
- 2026may: the same network re-exported with dynamic H/W, which OpenCV 5.x's
  ONNX Runtime engine needs. detectors.py uses whichever one loads.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"
ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet"

# name -> (sha256, size in bytes), copied from the LFS pointers at
# https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4", 232589),
    "face_detection_yunet_2026may.onnx": (
        "ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0", 229738),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_valid(path: Path, digest: str, size: int) -> bool:
    return path.exists() and path.stat().st_size == size and sha256(path) == digest


def try_load(path: Path) -> bool:
    import cv2
    try:
        cv2.FaceDetectorYN.create(str(path), "", (320, 320))
        return True
    except cv2.error as e:
        print(f"  note: OpenCV could not load {path.name}: {e.msg.strip()[:120]}")
        return False


def main() -> int:
    MODELS_DIR.mkdir(exist_ok=True)
    ok = True
    for name, (digest, size) in MODELS.items():
        dest = MODELS_DIR / name
        if is_valid(dest, digest, size):
            print(f"[ok] {name} already present")
        else:
            url = f"{ZOO}/{name}"
            print(f"[..] downloading {url}")
            tmp = dest.with_suffix(".part")
            urllib.request.urlretrieve(url, tmp)
            if not is_valid(tmp, digest, size):
                tmp.unlink(missing_ok=True)
                print(f"[!!] {name}: size/hash mismatch, file discarded")
                ok = False
                continue
            tmp.rename(dest)
            print(f"[ok] {name}: sha256 + size verified ({size:,} bytes)")
        print(f"     loads in OpenCV: {try_load(dest)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
