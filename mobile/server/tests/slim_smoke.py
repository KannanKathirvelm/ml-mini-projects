"""Hit every endpoint on the SLIM profile and check torch/ultralytics never load.

    SERVER_PROFILE=slim python tests/slim_smoke.py            # in-process (TestClient)
    python tests/slim_smoke.py --url http://127.0.0.1:7870    # against a running server

Prints one JSON line with per-endpoint status codes and a few values (used by
tests/test_slim.py and for the Render RSS measurement). Exit code 1 on any failure.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))
SAMPLES = {"faces": SERVER / "projects/06_face_detection/samples/lena.jpg",
           "objects": SERVER / "projects/07_object_detection/samples/bus.jpg"}
CARD = {"amount": 950, "hour": 2, "distance_from_home_km": 400, "distance_from_last_txn_km": 300,
        "ratio_to_median_amount": 6, "online_order": 1, "used_chip": 0, "used_pin": 0,
        "txn_count_last_24h": 8, "merchant_category": "electronics"}


def run(client) -> dict:
    out, fails = {}, []

    def call(name, method, path, expect=200, **kw):
        t0 = time.perf_counter()
        r = getattr(client, method)(path, **kw)
        out[name] = {"status": r.status_code, "ms": round((time.perf_counter() - t0) * 1000)}
        if r.status_code != expect:
            fails.append(f"{name}: {r.status_code} {r.text[:200]}")
            return None
        return r.json()

    h = call("health", "get", "/health")
    if h and h.get("profile") != "slim":
        fails.append(f"health profile is {h.get('profile')}")
    call("cc_meta", "get", "/api/credit-card/meta")
    p = call("cc_predict", "post", "/api/credit-card/predict", json=CARD)
    if p and not p["flagged"]:
        fails.append("credit card example not flagged")
    ex = call("upi_examples", "get", "/api/upi/examples")
    call("upi_meta", "get", "/api/upi/meta")
    if ex:
        u = call("upi_predict", "post", "/api/upi/predict", json=ex[1]["input"])
        if u and u["risk_level"] != "HIGH":
            fails.append("UPI scam example not HIGH")
    t = call("stocks_tickers", "get", "/api/stocks/tickers")
    if t and not t["universal"]:
        fails.append("universal model missing")
    f = call("stocks_reliance", "get", "/api/stocks/reliance/forecast", params={"days": 5})
    if f:
        out["stocks_reliance"].update(model=f["model"], currency=f["currency"],
                                      forecast=[d["lstm"] for d in f["forecast"]],
                                      last_close=f["last_close"])
    fu = call("stocks_reliance_universal", "get", "/api/stocks/RELIANCE.NS/forecast",
              params={"days": 5, "model": "universal"})
    if fu:
        out["stocks_reliance_universal"].update(rnn=[d["rnn"] for d in fu["forecast"]],
                                                lstm=[d["lstm"] for d in fu["forecast"]],
                                                metrics=fu["metrics"])
    fa = call("stocks_aapl", "get", "/api/stocks/AAPL/forecast", params={"days": 5})
    if fa:
        out["stocks_aapl"].update(model=fa["model"], lstm=[d["lstm"] for d in fa["forecast"]])
    tr = call("stocks_train", "post", "/api/stocks/infosys/train")
    if tr and (tr["model"] != "universal" or tr.get("trained") is not False):
        fails.append("slim train should return the universal forecast")
    call("stocks_unknown", "get", "/api/stocks/ZZZZNOTREAL/forecast", expect=404)
    fin = call("finance_tcs", "get", "/api/finance/tcs/report")
    if fin and not (fin.get("benchmark") and fin["benchmark"]["symbol"] == "^NSEI"):
        fails.append("finance benchmark missing")
    call("prices_search", "get", "/api/prices/search", params={"q": "iphone"})
    call("prices_tracked", "get", "/api/prices/tracked")
    call("india_popular", "get", "/api/india/popular")
    call("india_status", "get", "/api/india/market-status")
    s = call("india_search", "get", "/api/india/search", params={"q": "infos"})
    if s and s["results"][0]["symbol"] != "INFY.NS":
        fails.append("search infos != INFY.NS")
    call("india_stocks", "get", "/api/india/stocks", params={"limit": 5})
    call("india_quote", "get", "/api/india/quote/reliance")
    call("india_quotes", "get", "/api/india/quotes", params={"symbols": "RELIANCE,TCS,nifty"})
    call("india_intraday", "get", "/api/india/intraday/reliance", params={"interval": "5m"})
    for det in ("yunet", "haar"):
        with open(SAMPLES["faces"], "rb") as fh:
            call(f"faces_{det}", "post", "/api/faces/detect",
                 files={"image": ("lena.jpg", fh, "image/jpeg")}, data={"detector": det})
    call("objects_classes", "get", "/api/objects/classes")
    for m in ("yolo11n.pt", "yolo11s.pt"):
        with open(SAMPLES["objects"], "rb") as fh:
            o = call(f"objects_{m}", "post", "/api/objects/detect",
                     files={"image": ("bus.jpg", fh, "image/jpeg")}, data={"model": m})
        if o:
            out[f"objects_{m}"].update(counts=o["counts"],
                                       boxes=[d["box"] for d in o["detections"]])
    out["fails"] = fails
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    a = ap.parse_args()
    if a.url:
        import httpx

        with httpx.Client(base_url=a.url, timeout=180) as c:
            out = run(c)
    else:
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            out = run(c)
        heavy = sorted(m for m in ("torch", "ultralytics", "torchvision") if m in sys.modules)
        if heavy:
            out["fails"].append(f"heavy modules imported: {heavy}")
        out["heavy_modules"] = heavy
    print(json.dumps(out))
    return 1 if out["fails"] else 0


if __name__ == "__main__":
    sys.exit(main())
