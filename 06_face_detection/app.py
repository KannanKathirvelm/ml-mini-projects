"""Streamlit demo: Haar cascade vs YuNet side by side on one image.

Run with:  .venv/bin/streamlit run app.py
"""

import time
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from detectors import HaarDetector, YuNetDetector
from draw import annotate

SAMPLES = Path(__file__).parent / "samples"

st.set_page_config(page_title="Face detection: Haar vs DNN", page_icon="🙂", layout="wide")
st.title("Face detection: Haar cascade vs YuNet (DNN)")
st.caption("Classic Viola-Jones cascade (2001) vs a tiny CNN, both running in OpenCV on the CPU.")


@st.cache_resource
def get_haar(scale_factor: float, min_neighbors: int) -> HaarDetector:
    return HaarDetector(scale_factor=scale_factor, min_neighbors=min_neighbors)


@st.cache_resource
def get_yunet(threshold: float) -> YuNetDetector:
    return YuNetDetector(score_threshold=threshold)


def decode(data: bytes) -> np.ndarray | None:
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


# ---- sidebar: input + settings ------------------------------------------------
with st.sidebar:
    st.header("Image")
    source = st.radio("Source", ["Sample", "Upload", "Camera"], horizontal=True)
    image = None
    if source == "Sample":
        names = sorted(p.name for p in SAMPLES.iterdir() if p.suffix in {".png", ".jpg"})
        default = names.index("addams-family.png") if "addams-family.png" in names else 0
        name = st.selectbox("Sample image", names, index=default)
        image = cv2.imread(str(SAMPLES / name))
    elif source == "Upload":
        up = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png", "bmp", "webp"])
        if up is not None:
            image = decode(up.getvalue())
            name = up.name
    else:
        snap = st.camera_input("Take a snapshot")
        if snap is not None:
            image = decode(snap.getvalue())
            name = "snapshot.png"

    st.header("YuNet (DNN)")
    threshold = st.slider("Confidence threshold", 0.1, 0.99, 0.6, 0.01)
    st.header("Haar cascade")
    scale_factor = st.slider("scaleFactor", 1.01, 1.5, 1.1, 0.01,
                             help="Image-pyramid step. Smaller = slower, finds more sizes.")
    min_neighbors = st.slider("minNeighbors", 1, 15, 5,
                              help="Overlapping hits needed. Higher = fewer false positives.")
    st.header("Display")
    blur = st.toggle("Blur / anonymise faces", value=False)
    landmarks = st.toggle("Show YuNet landmarks", value=True)

if image is None:
    st.info("Choose a sample, upload an image or take a camera snapshot to start.")
    st.stop()

# ---- detection ----------------------------------------------------------------
results = []
for det in (get_haar(scale_factor, min_neighbors), get_yunet(threshold)):
    t0 = time.perf_counter()
    faces = det.detect(image)
    ms = (time.perf_counter() - t0) * 1000
    results.append((det, faces, ms, annotate(image, faces, blur=blur, landmarks=landmarks)))

cols = st.columns(2)
for col, (det, faces, ms, out) in zip(cols, results):
    with col:
        st.subheader(det.name)
        m1, m2 = st.columns(2)
        m1.metric("Faces", len(faces))
        m2.metric("Time", f"{ms:.1f} ms")
        st.image(cv2.cvtColor(out, cv2.COLOR_BGR2RGB), width="stretch")
        ok, png = cv2.imencode(".png", out)
        stem = Path(name).stem
        st.download_button("Download annotated image", png.tobytes(),
                           file_name=f"{stem}_{'haar' if det is results[0][0] else 'yunet'}.png",
                           mime="image/png", key=f"dl_{det.name}", width="stretch")

st.caption("Haar scores are the cascade's final-stage weight (not a probability); YuNet scores are "
           "confidences in [0, 1]. Timing is a single call, so expect some jitter; see benchmark.py "
           "for proper numbers.")
