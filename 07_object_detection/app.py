"""Streamlit front-end for the YOLO detector.

Run with:  streamlit run app.py
The model is cached per (size, device) so moving a slider only re-runs
inference, not model loading.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st

from config import MODEL_SIZES, SAMPLES_DIR, pick_device
from detector import Detector, FrameResult, video_writer
from line_counter import LineCounter

MAX_VIDEO_FRAMES = 300  # keep uploads snappy; ~10 s at 30 FPS

st.set_page_config(page_title="YOLO Object Detection", page_icon="🎯", layout="wide")


@st.cache_resource(show_spinner="Loading model...")
def load_detector(model: str, device: str) -> Detector:
    return Detector(model, device)


def counts_view(result: FrameResult) -> None:
    if not result.detections:
        st.info("No objects above the confidence threshold.")
        return
    df = pd.DataFrame(result.counts.items(), columns=["class", "count"])
    c1, c2 = st.columns([1, 2])
    c1.dataframe(df, hide_index=True, width="stretch")
    c2.bar_chart(df.set_index("class"))
    with st.expander("All detections"):
        st.dataframe(
            pd.DataFrame(
                [{"class": d.cls_name, "confidence": round(d.conf, 3),
                  "box (x1,y1,x2,y2)": [round(v) for v in d.box]} for d in result.detections]
            ),
            hide_index=True, width="stretch",
        )


def show_image_result(det: Detector, bgr: np.ndarray, conf, iou, classes, name: str) -> None:
    r = det.detect(bgr, conf, iou, classes)
    st.image(cv2.cvtColor(r.annotated, cv2.COLOR_BGR2RGB), width="stretch")
    m1, m2 = st.columns(2)
    m1.metric("Objects", len(r.detections))
    m2.metric("Inference time", f"{r.inference_ms:.1f} ms")
    counts_view(r)
    ok, buf = cv2.imencode(".png", r.annotated)
    st.download_button("Download annotated image", buf.tobytes(), file_name=f"{Path(name).stem}_det.png",
                       mime="image/png")


def process_video(det: Detector, src_path: str, conf, iou, classes, track: bool) -> dict:
    cap = cv2.VideoCapture(src_path)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or MAX_VIDEO_FRAMES, MAX_VIDEO_FRAMES)
    out_path = Path(tempfile.mkdtemp()) / "annotated.mp4"
    writer = video_writer(out_path, fps, (w, h))
    counter = LineCounter.vertical_center(w, h) if track else None
    if track:
        det.reset_tracker()

    peak, infer_ms, n = {}, [], 0
    bar = st.progress(0.0, text="Processing video...")
    while n < total:
        ok, frame = cap.read()
        if not ok:
            break
        r = det.track(frame, conf, iou, classes) if track else det.detect(frame, conf, iou, classes)
        for k, v in r.counts.items():
            peak[k] = max(peak.get(k, 0), v)
        if counter:
            counter.update(r.detections)
            counter.draw(r.annotated)
        writer.write(r.annotated)
        infer_ms.append(r.inference_ms)
        n += 1
        bar.progress(n / total, text=f"Processing frame {n}/{total}")
    cap.release()
    writer.release()
    bar.empty()
    return {"path": out_path, "frames": n, "peak": peak,
            "crossings": counter.totals if counter else None,
            "ms": float(np.mean(infer_ms)) if infer_ms else 0.0}


# ---------------- sidebar ----------------
st.sidebar.title("Settings")
size = st.sidebar.selectbox("Model size", list(MODEL_SIZES), help="Bigger = more accurate, slower")
device = st.sidebar.selectbox("Device", ["auto", "cpu", "mps"], help="auto = mps if available")
device = pick_device(None if device == "auto" else device)
conf = st.sidebar.slider("Confidence threshold", 0.05, 0.95, 0.25, 0.05)
iou = st.sidebar.slider("NMS IoU threshold", 0.1, 0.95, 0.7, 0.05,
                        help="Lower = more aggressive removal of overlapping boxes")
det = load_detector(MODEL_SIZES[size], device)
classes = st.sidebar.multiselect("Only these classes (empty = all 80)", sorted(det.names.values()))
st.sidebar.caption(f"Model `{MODEL_SIZES[size]}` on `{det.device}`")

# ---------------- main ----------------
st.title("🎯 YOLO Object Detection")
st.caption("YOLO11 pretrained on COCO (80 classes): people, vehicles, animals, everyday objects.")

tab_img, tab_vid, tab_cam = st.tabs(["Image", "Video", "Camera snapshot"])

with tab_img:
    samples = sorted(p.name for p in SAMPLES_DIR.glob("*.jpg"))
    choice = st.radio("Source", ["Sample image", "Upload"], horizontal=True)
    bgr, name = None, "image"
    if choice == "Sample image":
        name = st.selectbox("Sample", samples)
        bgr = cv2.imread(str(SAMPLES_DIR / name))
    else:
        up = st.file_uploader("Image", type=["jpg", "jpeg", "png", "bmp", "webp"])
        if up:
            bgr = cv2.imdecode(np.frombuffer(up.getvalue(), np.uint8), cv2.IMREAD_COLOR)
            name = up.name
    if bgr is not None:
        show_image_result(det, bgr, conf, iou, classes, name)

with tab_vid:
    st.write(f"Short clips only - the first {MAX_VIDEO_FRAMES} frames are processed.")
    vchoice = st.radio("Video source", ["Sample video", "Upload"], horizontal=True)
    track = st.checkbox("Track objects + count crossings of a vertical centre line (ByteTrack)", value=True)
    src = None
    if vchoice == "Sample video":
        sample_vid = SAMPLES_DIR / "pan_demo.mp4"
        if sample_vid.exists():
            src = str(sample_vid)
        else:
            st.warning("Run `python make_sample_video.py` to create the sample clip.")
    else:
        vup = st.file_uploader("Video", type=["mp4", "mov", "avi", "mkv"])
        if vup:
            tmp = Path(tempfile.mkdtemp()) / vup.name
            tmp.write_bytes(vup.getvalue())
            src = str(tmp)
    if src and st.button("Run detection on video", type="primary"):
        res = process_video(det, src, conf, iou, classes, track)
        video_bytes = res["path"].read_bytes()
        st.video(video_bytes)
        m1, m2 = st.columns(2)
        m1.metric("Frames processed", res["frames"])
        m2.metric("Avg inference / frame", f"{res['ms']:.1f} ms")
        st.write("**Peak objects in a single frame**")
        if res["peak"]:
            st.bar_chart(pd.Series(res["peak"], name="count"))
        if res["crossings"] is not None:
            st.write("**Line crossings (unique track IDs)**")
            st.dataframe(pd.DataFrame(res["crossings"].items(), columns=["class", "crossed"]),
                         hide_index=True)
        st.download_button("Download annotated video", video_bytes, file_name="annotated.mp4",
                           mime="video/mp4")

with tab_cam:
    shot = st.camera_input("Take a snapshot")
    if shot:
        bgr = cv2.imdecode(np.frombuffer(shot.getvalue(), np.uint8), cv2.IMREAD_COLOR)
        show_image_result(det, bgr, conf, iou, classes, "snapshot")
