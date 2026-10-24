"""Every endpoint in ../API.md, including error cases.

Finance, prices (demo store APIs) and stock price refreshes need internet.
The real stock training run is opt-in:  RUN_TRAIN=1 pytest
"""
import base64
import os

import pytest
from fastapi.testclient import TestClient

from app import loader
from app.main import app

FACES = loader.project_dir("faces") / "samples"
OBJECTS = loader.project_dir("objects") / "samples"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(app) as c:
        yield c


def is_jpeg_b64(s: str) -> bool:
    return not s.startswith("data:") and base64.b64decode(s)[:2] == b"\xff\xd8"


def test_health(client):
    r = client.get("/health")
    assert r.json() == {"status": "ok", "version": "1", "projects": [
        "credit-card", "upi", "stocks", "finance", "prices", "faces", "objects"]}


def test_cors(client):
    r = client.get("/health", headers={"Origin": "capacitor://localhost"})
    assert r.headers["access-control-allow-origin"] == "*"


# ------------------------------------------------------------------ 1 + 2
CARD = {"amount": 950, "hour": 2, "distance_from_home_km": 400, "distance_from_last_txn_km": 300,
        "ratio_to_median_amount": 6, "online_order": 1, "used_chip": 0, "used_pin": 0,
        "txn_count_last_24h": 8, "merchant_category": "electronics"}


def test_credit_card(client):
    m = client.get("/api/credit-card/meta").json()
    assert m["categories"] == ["grocery", "gas", "restaurant", "electronics", "travel", "online_retail"]
    assert set(m["metrics"]) == {"best_model", "fraud_precision", "fraud_recall",
                                 "average_precision", "roc_auc"}
    r = client.post("/api/credit-card/predict", json=CARD).json()
    assert set(r) == {"fraud_probability", "flagged", "threshold"}
    assert r["flagged"] is True and r["fraud_probability"] > 0.9
    legit = dict(CARD, amount=20, hour=14, distance_from_home_km=2, distance_from_last_txn_km=1,
                 ratio_to_median_amount=1, online_order=0, used_chip=1, used_pin=1,
                 txn_count_last_24h=2, merchant_category="grocery")
    assert client.post("/api/credit-card/predict", json=legit).json()["flagged"] is False


def test_credit_card_errors(client):
    r = client.post("/api/credit-card/predict", json=dict(CARD, merchant_category="casino"))
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    r = client.post("/api/credit-card/predict", json={"amount": 1})
    assert r.status_code == 422 and "hour" in r.json()["detail"]


def test_upi(client):
    m = client.get("/api/upi/meta").json()
    assert set(m["metrics"]["recall_by_fraud_type"]) == {"account_takeover", "collect_scam", "fake_qr"}
    ex = client.get("/api/upi/examples").json()
    assert [e["name"] for e in ex] == ["Normal: paying a friend", "Scam: fake refund collect request",
                                       "Scam: SIM swap takeover", "Scam: fake merchant QR"]
    levels = []
    for e in ex:
        r = client.post("/api/upi/predict", json=e["input"]).json()
        assert set(r) == {"fraud_probability", "risk_level", "flagged", "threshold", "reasons"}
        assert isinstance(r["reasons"], list)
        levels.append(r["risk_level"])
    assert levels == ["LOW", "HIGH", "HIGH", "HIGH"]
    bad = dict(ex[0]["input"], mode="teleport")
    assert client.post("/api/upi/predict", json=bad).status_code == 422


# ---------------------------------------------------------------------- 3
def test_stocks(client):
    t = client.get("/api/stocks/tickers").json()["trained"]
    assert {"AAPL", "MSFT", "RELIANCE.NS", "TCS.NS"} <= set(t)
    r = client.get("/api/stocks/AAPL/forecast", params={"days": 5})
    assert r.status_code == 200, r.text
    b = r.json()
    assert set(b) == {"ticker", "last_close", "last_date", "history", "forecast", "metrics", "test"}
    assert len(b["history"]) == 90 and len(b["forecast"]) == 5
    assert set(b["forecast"][0]) == {"date", "rnn", "lstm"}
    assert set(b["metrics"]) == {"naive_baseline", "rnn", "lstm"}
    assert b["metrics"]["naive_baseline"]["direction_acc_pct"] is None
    assert len(b["test"]["dates"]) == len(b["test"]["actual"]) == len(b["test"]["lstm"])
    assert client.get("/api/stocks/tcs.ns/forecast").json()["ticker"] == "TCS.NS"


def test_stocks_errors(client):
    r = client.get("/api/stocks/ZZZNOTTRAINED/forecast")
    assert r.status_code == 404 and "ZZZNOTTRAINED" in r.json()["detail"]
    assert client.get("/api/stocks/AAPL/forecast", params={"days": 31}).status_code == 422
    assert client.get("/api/stocks/AAPL/forecast", params={"days": 0}).status_code == 422
    r = client.post("/api/stocks/NOTAREALTICKERXYZ/train")
    assert r.status_code == 400 and r.json()["detail"]


@pytest.mark.skipif(not os.environ.get("RUN_TRAIN"), reason="slow (~30-60 s); set RUN_TRAIN=1")
def test_stocks_train(client):
    r = client.post("/api/stocks/MSFT/train")
    assert r.status_code == 200, r.text
    assert len(r.json()["forecast"]) == 10


# ---------------------------------------------------------------------- 4
def test_finance(client):
    r = client.get("/api/finance/AAPL/report")
    assert r.status_code == 200, r.text
    b = r.json()
    keys = {"ticker", "company", "mode", "mode_label", "currency", "last_close", "last_date",
            "outlook", "confidence", "summary", "bullish", "bearish", "risks", "overall", "agents",
            "headlines", "indicators", "chart", "markdown"}
    assert set(b) == keys
    assert b["mode"] in ("offline", "llm") and b["outlook"] in ("bullish", "neutral", "bearish")
    assert b["confidence"] in ("low", "medium", "high")
    assert [a["name"] for a in b["agents"]] == ["Technical Analyst", "Fundamental Analyst",
                                                "News & Sentiment Analyst"]
    assert set(b["indicators"]) == {"rsi", "volatility_1y", "return_1m", "max_drawdown_1y"}
    assert 200 <= len(b["chart"]) <= 250 and set(b["chart"][0]) == {"date", "close", "sma20", "sma50", "sma200"}
    assert b["markdown"].startswith("# Market insight")


def test_finance_unknown(client):
    r = client.get("/api/finance/NOTAREALTICKERXYZ/report")
    assert r.status_code == 404 and r.json()["detail"]


# ---------------------------------------------------------------------- 5
def test_prices_flow(client):
    s = client.get("/api/prices/search", params={"q": "iphone"}).json()
    assert {"ShopKart", "MegaMart", "QuickBuy"} <= set(s["stores_ok"])
    g = s["groups"][0]
    assert set(g) == {"product", "store_count", "best", "savings_inr", "offers"}
    totals = [o["total_inr"] for o in g["offers"]]
    assert totals == sorted(totals)
    assert set(g["offers"][0]) == {"store", "title", "price_inr", "shipping_inr", "total_inr",
                                   "delivery_days", "rating", "in_stock", "url", "image"}
    if g["best"]:
        assert g["best"]["in_stock"] and g["best"]["total_inr"] == min(
            o["total_inr"] for o in g["offers"] if o["in_stock"])

    h = client.get("/api/prices/history", params={"product": "iPhone 13 Pro", "days": 30}).json()
    assert max(len(s["points"]) for s in h["series"]) >= 25  # seeded 30 days

    t = client.post("/api/prices/track", json={"product": "iPhone 13 Pro", "target_inr": 95000})
    assert t.status_code == 200, t.text
    t = t.json()
    assert set(t) == {"product", "target_inr", "latest_best_inr", "latest_store", "hit"}
    assert t["hit"] is True
    assert any(x["product"] == t["product"] for x in client.get("/api/prices/tracked").json())
    alerts = client.post("/api/prices/check-alerts").json()
    a = next(x for x in alerts if x["product"] == t["product"])
    assert set(a) == {"product", "target_inr", "best_inr", "store", "hit"}
    assert client.delete("/api/prices/track", params={"product": "iPhone 13 Pro"}).json() == {"removed": True}
    assert client.delete("/api/prices/track", params={"product": "iPhone 13 Pro"}).json() == {"removed": False}


def test_prices_errors(client):
    assert client.get("/api/prices/search").status_code == 422
    r = client.post("/api/prices/track", json={"product": "zzqx nonexistent gadget", "target_inr": 10})
    assert r.status_code == 404


# ---------------------------------------------------------------------- 6
def _upload(path):
    return {"image": (path.name, path.read_bytes(), "image/jpeg")}


def test_faces(client):
    r = client.post("/api/faces/detect", files=_upload(FACES / "lena.jpg")).json()
    assert len(r["results"]) == 1
    y = r["results"][0]
    assert y["detector"] == "yunet" and y["count"] >= 1
    assert len(y["faces"][0]["landmarks"]) == 5 and is_jpeg_b64(y["image_base64"])

    r = client.post("/api/faces/detect", files=_upload(FACES / "class57.png"),
                    data={"detector": "both", "blur": "true", "threshold": "0.5"}).json()
    assert [x["detector"] for x in r["results"]] == ["yunet", "haar"]
    assert r["results"][1]["faces"][0]["landmarks"] is None


def test_faces_downscale(client):
    import cv2
    import numpy as np
    big = cv2.resize(cv2.imread(str(FACES / "lena.jpg")), (2560, 2560))
    ok, buf = cv2.imencode(".jpg", big)
    r = client.post("/api/faces/detect", files={"image": ("big.jpg", buf.tobytes(), "image/jpeg")}).json()
    out = cv2.imdecode(np.frombuffer(base64.b64decode(r["results"][0]["image_base64"]), np.uint8), 1)
    assert max(out.shape[:2]) == 1280


def test_faces_errors(client):
    r = client.post("/api/faces/detect", files=_upload(FACES / "lena.jpg"), data={"detector": "mtcnn"})
    assert r.status_code == 400 and "mtcnn" in r.json()["detail"]
    big = {"image": ("big.jpg", b"\xff\xd8" + os.urandom(8 * 1024 * 1024 + 10), "image/jpeg")}
    assert client.post("/api/faces/detect", files=big).status_code == 413
    bad = {"image": ("x.jpg", b"not an image", "image/jpeg")}
    assert client.post("/api/faces/detect", files=bad).status_code == 400
    r = client.post("/api/faces/detect", files=_upload(FACES / "lena.jpg"), data={"threshold": "2"})
    assert r.status_code == 400
    assert client.post("/api/faces/detect").status_code == 400


# ---------------------------------------------------------------------- 7
def test_objects(client):
    c = client.get("/api/objects/classes").json()
    assert len(c["classes"]) == 80 and c["classes"][0] == "person"
    assert c["models"] == ["yolo11n.pt", "yolo11s.pt"]
    r = client.post("/api/objects/detect", files=_upload(OBJECTS / "bus.jpg")).json()
    assert set(r) == {"count", "time_ms", "counts", "detections", "image_base64"}
    assert r["counts"].get("person", 0) >= 3 and r["count"] == len(r["detections"])
    assert len(r["detections"][0]["box"]) == 4 and is_jpeg_b64(r["image_base64"])
    r = client.post("/api/objects/detect", files=_upload(OBJECTS / "bus.jpg"),
                    data={"classes": "bus", "model": "yolo11s.pt", "conf": "0.4"}).json()
    assert set(r["counts"]) == {"bus"}


def test_objects_errors(client):
    r = client.post("/api/objects/detect", files=_upload(OBJECTS / "bus.jpg"), data={"model": "yolo99.pt"})
    assert r.status_code == 400
    r = client.post("/api/objects/detect", files=_upload(OBJECTS / "bus.jpg"), data={"classes": "unicorn"})
    assert r.status_code == 400 and "unicorn" in r.json()["detail"]
    big = {"image": ("big.jpg", os.urandom(9 * 1024 * 1024), "image/jpeg")}
    assert client.post("/api/objects/detect", files=big).status_code == 413
