"""One FastAPI server for the 7 ML mini projects. Contract: ../API.md.

    uvicorn app.main:app --host 0.0.0.0 --port 7860
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import settings
from .routers import finance, fraud, prices, stocks, vision

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("server")

PROJECTS = ["credit-card", "upi", "stocks", "finance", "prices", "faces", "objects"]


def preload() -> dict[str, str]:
    """Import every project and load its models once. Failures are logged, not fatal."""
    steps = {
        "credit-card": fraud.cc,
        "upi": fraud.upi,
        "stocks": stocks.ns,
        "finance": finance.ns,
        "prices": lambda: (prices.ns(), settings.SEED_PRICE_HISTORY and prices.seed_if_empty()),
        "faces": lambda: (vision.face_detector("yunet"), vision.face_detector("haar")),
        "objects": lambda: vision.yolo(vision.YOLO_MODELS[0]),
    }
    status = {}
    for name, fn in steps.items():
        t0 = time.perf_counter()
        try:
            fn()
            status[name] = "ok"
            log.info("loaded %-11s in %6.0f ms", name, (time.perf_counter() - t0) * 1000)
        except Exception as exc:  # keep serving the other projects
            status[name] = f"error: {exc}"
            log.exception("failed to load %s", name)
    return status


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if settings.PRELOAD:
        app.state.load_status = preload()
    elif settings.SEED_PRICE_HISTORY:
        prices.seed_if_empty()
    yield


app = FastAPI(title="ML mini projects API", version=settings.VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    response.headers["X-Process-Time-Ms"] = f"{ms:.1f}"
    log.info("%s %s -> %d in %.1f ms", request.method, request.url.path, response.status_code, ms)
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """Contract: `detail` is always a human-readable string."""
    parts = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", []) if x not in ("body", "query", "path", "form"))
        parts.append(f"{loc}: {e.get('msg')}" if loc else str(e.get("msg")))
    return JSONResponse({"detail": "Invalid request: " + "; ".join(parts)}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
                        status_code=500)


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.VERSION, "projects": PROJECTS}


@app.get("/")
def root():
    return {"name": "ML mini projects API", "docs": "/docs", "health": "/health"}


for r in (fraud.cc_router, fraud.upi_router, stocks.router, finance.router, prices.router,
          vision.faces_router, vision.objects_router):
    app.include_router(r)
