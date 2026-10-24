"""Drawing helpers: boxes + scores, landmarks, face count, and anonymising blur.

Kept separate from detectors.py so detection stays pure (image in, faces out)
and the CLI, benchmark and Streamlit app all render results the same way.
"""

import cv2
import numpy as np

from detectors import Face

GREEN = (60, 200, 60)
LANDMARK_COLOURS = [(255, 0, 0), (0, 0, 255), (0, 255, 255), (255, 0, 255), (0, 165, 255)]


def blur_faces(image: np.ndarray, faces: list[Face]) -> np.ndarray:
    """Heavy blur + pixelation inside each box, so the face is not recoverable."""
    out = image.copy()
    H, W = out.shape[:2]
    for f in faces:
        x0, y0 = max(f.x, 0), max(f.y, 0)
        x1, y1 = min(f.x + f.w, W), min(f.y + f.h, H)
        if x1 <= x0 or y1 <= y0:
            continue
        roi = out[y0:y1, x0:x1]
        small = cv2.resize(roi, (8, 8), interpolation=cv2.INTER_LINEAR)
        pix = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
        out[y0:y1, x0:x1] = cv2.GaussianBlur(pix, (0, 0), max(2, (x1 - x0) // 10))
    return out


def annotate(image: np.ndarray, faces: list[Face], blur: bool = False,
             landmarks: bool = True, label: str | None = None) -> np.ndarray:
    out = blur_faces(image, faces) if blur else image.copy()
    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    thick = max(1, round(max(out.shape[:2]) / 400))
    for f in faces:
        cv2.rectangle(out, (f.x, f.y), (f.x + f.w, f.y + f.h), GREEN, thick)
        _text(out, f"{f.score:.2f}", (f.x, max(f.y - 4, 12)), 0.45 * thick)
        if landmarks and not blur:
            for (px, py), c in zip(f.landmarks, LANDMARK_COLOURS):
                cv2.circle(out, (px, py), thick + 1, c, -1)
    header = f"{label + ': ' if label else ''}{len(faces)} face{'s' if len(faces) != 1 else ''}"
    _text(out, header, (8, int(30 * thick)), 0.6 * thick)
    return out


def _text(img, text, org, scale):
    """White text with a dark outline so it is readable on any background."""
    t = max(1, int(scale * 2))
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), t + 2, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), t, cv2.LINE_AA)
