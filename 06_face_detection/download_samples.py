"""Fetch the bundled test images into samples/.

Sources (all official OpenCV / scikit-image repositories):
- scikit-image `data.astronaut()`: NASA portrait of Eileen Collins (public domain).
- opencv/opencv samples/data: lena.jpg, messi5.jpg.
- opencv/opencv_extra testdata/cv/cascadeandhog/images: a few photos from the
  classic CMU/MIT frontal-face test set, which OpenCV uses to regression-test
  its cascades. These give us multi-face images (2 to 50+ faces), mostly
  grayscale and low resolution, i.e. a hard case for both detectors.
The images are research/demo data; check their original terms before reusing
them outside this project.
"""

import urllib.request
from pathlib import Path

import cv2

SAMPLES = Path(__file__).parent / "samples"
OPENCV = "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data"
EXTRA = "https://raw.githubusercontent.com/opencv/opencv_extra/4.x/testdata/cv/cascadeandhog/images"

URLS = {
    "lena.jpg": f"{OPENCV}/lena.jpg",
    "messi5.jpg": f"{OPENCV}/messi5.jpg",
    "karen-and-rob.png": f"{EXTRA}/karen-and-rob.png",
    "addams-family.png": f"{EXTRA}/addams-family.png",
    "waynesworld2.png": f"{EXTRA}/waynesworld2.png",
    "rehg-thanksgiving-1994.png": f"{EXTRA}/rehg-thanksgiving-1994.png",
    "class57.png": f"{EXTRA}/class57.png",
}


def main() -> None:
    SAMPLES.mkdir(exist_ok=True)
    from skimage import data
    astro = SAMPLES / "astronaut.png"
    if not astro.exists():
        cv2.imwrite(str(astro), cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR))
    print(f"[ok] {astro.name}")

    for name, url in URLS.items():
        dest = SAMPLES / name
        if not dest.exists():
            urllib.request.urlretrieve(url, dest)
        # Verify it is really an image (not an HTML error page).
        img = cv2.imread(str(dest))
        if img is None:
            dest.unlink()
            raise SystemExit(f"[!!] {name} is not a readable image ({url})")
        print(f"[ok] {name} {img.shape[1]}x{img.shape[0]}")


if __name__ == "__main__":
    main()
