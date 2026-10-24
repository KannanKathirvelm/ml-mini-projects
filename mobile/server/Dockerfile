# Hugging Face Space (Docker SDK): one FastAPI server for the 7 ML mini projects.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libglib/libgomp: runtime libs used by opencv-python-headless and torch
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# CPU-only torch from the PyTorch wheel index (no CUDA libs, ~1.5 GB smaller)
RUN pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt \
 && pip uninstall -y opencv-python opencv-python-headless \
 && pip install --no-deps "opencv-python-headless==4.14.0.94" \
 && python -c "import cv2, torch; assert cv2.__version__.startswith('4.') and hasattr(cv2, 'CascadeClassifier'); assert not torch.cuda.is_available(); print('OpenCV', cv2.__version__, 'torch', torch.__version__)"

# HF Spaces run the container as uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    YOLO_CONFIG_DIR=/home/user/.config/Ultralytics \
    MPLCONFIGDIR=/home/user/.config/matplotlib \
    SERVER_DATA_DIR=/tmp/ml-mini-projects \
    PRICES_DB_PATH=/tmp/ml-mini-projects/prices.db \
    OBJECTS_DEVICE=cpu
WORKDIR /home/user/app

COPY --chown=user . .

# Retrain the 01/02 scikit-learn models with the scikit-learn pinned above (deterministic,
# ~30 s), train any stock model that isn't shipped (needs network), and pre-fetch YOLO
# weights + the Ultralytics font into $YOLO_CONFIG_DIR so runtime needs no downloads.
RUN python scripts/build_models.py --sklearn --force --clean-data \
        --stocks AAPL,MSFT,RELIANCE.NS,TCS.NS --warm-yolo

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
