"""Upload handling shared by the face and object endpoints."""
from __future__ import annotations

import base64

import cv2
import numpy as np
from fastapi import HTTPException, UploadFile

from .settings import JPEG_QUALITY, MAX_IMAGE_SIDE, MAX_UPLOAD_BYTES


async def read_image(upload: UploadFile | None) -> np.ndarray:
    """Read an uploaded image as BGR, rejecting >8 MB (413) and downscaling to max side 1280."""
    if upload is None:
        raise HTTPException(400, "Missing 'image' file field.")
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Image is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not data:
        raise HTTPException(400, "Uploaded image is empty.")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Could not decode the image. Send a JPEG or PNG file.")
    return downscale(img)


def downscale(img: np.ndarray, max_side: int = MAX_IMAGE_SIDE) -> np.ndarray:
    h, w = img.shape[:2]
    if max(h, w) <= max_side:
        return img
    s = max_side / max(h, w)
    return cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)


def to_b64_jpeg(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise HTTPException(500, "Could not encode the annotated image.")
    return base64.b64encode(buf.tobytes()).decode("ascii")
