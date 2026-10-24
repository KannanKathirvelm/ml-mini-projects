#!/usr/bin/env bash
# Create .venv for local runs with the same pins as the Docker image.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
if [ "$(uname)" = "Darwin" ]; then
  .venv/bin/pip install torch==2.14.1 torchvision==0.29.1           # macOS wheels are CPU/MPS
else
  .venv/bin/pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
fi
.venv/bin/pip install -r requirements.txt
.venv/bin/pip uninstall -y opencv-python opencv-python-headless
.venv/bin/pip install --no-deps "opencv-python-headless==4.14.0.94"
.venv/bin/python -c "import cv2; assert cv2.__version__.startswith('4.') and hasattr(cv2, 'CascadeClassifier'); print('OpenCV', cv2.__version__)"
