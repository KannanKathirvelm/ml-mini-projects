"""Build a short test video from the bundled sample images.

There's no licence-clean street footage bundled here, so we fake camera motion:
paste bus.jpg and zidane.jpg onto a wide grey strip and slide a window across
it. Every object enters on the right and leaves on the left, which gives the
tracker real motion and the line counter real crossings to count.
"""
import cv2
import numpy as np

from config import SAMPLES_DIR

H, W, STEP, FPS = 540, 960, 10, 30


def main(out=SAMPLES_DIR / "pan_demo.mp4"):
    tiles = []
    for name in ("bus.jpg", "zidane.jpg"):
        img = cv2.imread(str(SAMPLES_DIR / name))
        tiles.append(cv2.resize(img, (round(img.shape[1] * H / img.shape[0]), H)))
    pad = np.full((H, W, 3), 114, np.uint8)
    strip = np.hstack([pad, *tiles, pad])

    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    n = 0
    for x in range(0, strip.shape[1] - W + 1, STEP):
        writer.write(strip[:, x : x + W])
        n += 1
    writer.release()
    print(f"Wrote {out} ({n} frames, {n / FPS:.1f}s, {W}x{H})")


if __name__ == "__main__":
    main()
