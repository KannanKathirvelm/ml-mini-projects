# 🎯 Object Detection System (YOLO11)

Finds and labels objects from the 80 COCO classes (people, cars, buses, dogs, phones, ...) in images, videos and a live webcam. It comes with a CLI, a speed/accuracy benchmark and a Streamlit app.

## What it does

- Draws a bounding box for each object, with its class and confidence.
- Lets you set the **confidence** and **NMS IoU** thresholds.
- Has a **class filter**, e.g. only `person` and `car`.
- Shows **per-class counts** for every image or frame.
- Can **track objects** in video (ByteTrack) and run a **line-crossing counter**, e.g. "5 people and 1 bus crossed the line".
- Lets you pick the model size: `yolo11n` (nano), `yolo11s` (small) or `yolo11m` (medium).
- Picks the device for you: Apple `mps` if it's available, otherwise `cpu`. You can override this.

## How YOLO works (short version)

YOLO ("You Only Look Once") finds every object in a **single forward pass** of a convolutional network. It doesn't propose regions first and classify them afterwards.

1. **Backbone.** A CNN pulls out features at several scales. Small objects are found on the high-resolution maps and large objects on the coarse ones.
2. **Head.** For each grid location, the network predicts box coordinates and a score for each of the 80 classes. YOLO11 is *anchor-free*: it predicts box edges directly instead of adjusting preset anchor boxes.
3. **Post-processing.** Boxes below the **confidence** threshold are dropped. **Non-Maximum Suppression** then removes duplicates: when two boxes of the same class overlap by more than the **IoU** threshold, only the more confident one is kept.

**Tracking** adds identity across frames. ByteTrack predicts where each tracked box should be next (Kalman filter) and matches new detections to those predictions. It also uses low-confidence boxes to keep tracks alive through occlusion. Once every object has a stable ID, counting line crossings is easy: watch for an ID's centre point moving from one side of the line to the other (the sign of a cross product).

## Results

The numbers below are real, from `evaluate.py` on an Apple M2 with torch 2.14.1 and ultralytics 8.4.187. Speed is the median over 2 sample images × 20 runs, measured after warm-up.

| Model | Device | Inference (ms) | End-to-end (ms) | FPS (end-to-end) |
|---|---|---|---|---|
| yolo11n | CPU | 46.1 | 51.2 | 19.5 |
| yolo11n | MPS | 4.9 | 19.5 | 51.3 |
| yolo11s | CPU | 83.5 | 89.2 | 11.2 |
| yolo11s | MPS | 5.0 | 25.9 | 38.6 |

*End-to-end* covers reading the image, resizing, inference, NMS and building the results. On MPS the GPU runs asynchronously, so the "inference" column partly hides work that shows up later in post-processing. Trust the end-to-end column. On MPS, overhead outside the network dominates, so moving from n to s costs much less there than on CPU.

The validation run is a sanity check on **coco8**. Its validation split is only **4 images with 17 boxes**:

| Model | mAP50 | mAP50-95 | Precision | Recall |
|---|---|---|---|---|
| yolo11n | 0.854 | 0.631 | 0.57 | 0.85 |
| yolo11s | 0.935 | 0.745 | 0.935 | 0.787 |

> coco8 only confirms that the weights, labels and evaluation code fit together. It is far too small to be a real accuracy number. For reference, Ultralytics publishes **39.5** (n) and **47.0** (s) mAP50-95 on the full COCO val2017 (5,000 images).

Video check: `samples/pan_demo.mp4` with `--track` processed 233 frames at about 30–39 FPS end-to-end on MPS. With `--classes person bus` it counted 5 people and 1 bus crossing the centre line. The scene contains 6 people: the partly visible person cut off at the left edge of `bus.jpg` wasn't counted.

## Run it

Set up (Python 3.12):

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

Create the demo video from the sample images:

```bash
python make_sample_video.py
```

Detect objects in an image and save the annotated copy to `outputs/`:

```bash
python detect.py --source samples/bus.jpg --save
```

Run on every image in a folder, people only, with a stricter threshold:

```bash
python detect.py --source samples --classes person --conf 0.5 --save
```

Track objects in a video and count crossings of the vertical centre line:

```bash
python detect.py --source samples/pan_demo.mp4 --track --classes person bus --save
```

Use a custom line (`x1,y1,x2,y2`) or a horizontal one (`--line h`), for example for cars on a road:

```bash
python detect.py --source traffic.mp4 --track --classes car truck bus --line h --save
```

Use the webcam (opens a window with FPS; press `q` to quit):

```bash
python detect.py --source 0
```

Use a bigger model or force a device:

```bash
python detect.py --source samples/zidane.jpg --model yolo11s.pt --device cpu --save
```

Run the benchmark and coco8 validation:

```bash
python evaluate.py
```

Start the Streamlit app:

```bash
streamlit run app.py
```

The app has three tabs:

- **Image.** Pick a sample or upload a file, then see the annotated result, the inference time, a counts table and bar chart, and a download button.
- **Video.** Pick a sample or upload a short clip (first 300 frames). Optionally turn on tracking and line crossing to get an annotated H.264 video you can download.
- **Camera snapshot.** Uses `st.camera_input`.

The sidebar holds the model size, device, confidence/IoU sliders and the class filter.

Model weights download automatically on first use into `weights/`, from the Ultralytics GitHub releases. The coco8 dataset downloads into `datasets/`.

## Project structure

```
config.py              paths; keeps ultralytics settings/datasets/runs/weights inside the project; device pick
detector.py            Detector class: detect / track -> FrameResult (annotated image, detections, counts, ms)
line_counter.py        LineCounter: counts tracked IDs crossing a line, by class and direction
detect.py              CLI for images, folders, videos and webcam
evaluate.py            CPU vs MPS speed benchmark + coco8 mAP sanity check
app.py                 Streamlit UI
make_sample_video.py   builds samples/pan_demo.mp4 by panning across the sample images
samples/               bus.jpg, zidane.jpg (Ultralytics sample images), pan_demo.mp4
outputs/               annotated images/videos and eval_*.json (git-ignored)
```

## Limitations

- **Webcam mode is untested.** It was written for this setup but couldn't be run here because there's no camera. On macOS, the terminal app needs camera permission.
- **coco8 is tiny.** The mAP above is a smoke test, not a benchmark. Full COCO validation needs the 5,000-image val2017 set (about 1 GB).
- **The test video is synthetic.** It's a camera pan across still photos, so objects move rigidly. Real footage has occlusion, motion blur and people crossing each other, all of which make tracking harder. Even on this easy clip, ByteTrack sometimes gave new IDs to the same object (IDs reached about 60 for roughly 10 real objects). The counter counts each ID once, so a long gap could still cause a double count.
- **Pretrained on COCO only.** Objects outside the 80 classes are missed or mislabelled; one example is the tie detected on Zidane at low confidence. Detecting new classes needs fine-tuning.
- **The app processes video in memory.** It handles at most 300 frames per clip, so it's only suited to short clips.
