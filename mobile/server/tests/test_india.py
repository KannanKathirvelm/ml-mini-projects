"""India endpoints (API.md sections 8 + 9), the ONNX model paths and the slim profile.

Quotes, intraday bars, forecasts and finance reports need internet (Yahoo Finance).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import loader
from app.main import app
from app.routers import stocks

SERVER = Path(__file__).resolve().parents[1]
QUOTE_KEYS = {"symbol", "name", "price", "change", "change_pct", "prev_close", "open", "high", "low",
              "volume", "currency", "display", "as_of_ist", "market_open", "source", "delayed_note"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ /api/india (offline parts)
def test_popular(client):
    b = client.get("/api/india/popular").json()
    assert len(b["stocks"]) == 20 and b["stocks"][0] == {"symbol": "RELIANCE.NS",
                                                         "name": "Reliance Industries", "sector": "Energy"}
    assert [i["symbol"] for i in b["indices"]] == ["^NSEI", "^BSESN", "^NSEBANK"]


def test_market_status(client):
    b = client.get("/api/india/market-status").json()
    assert set(b) == {"exchange", "is_open", "now_ist", "next_open_ist", "next_close_ist", "note"}
    assert b["exchange"] == "NSE" and isinstance(b["is_open"], bool) and b["now_ist"].endswith("+05:30")


def test_search(client):
    b = client.get("/api/india/search", params={"q": "infos"}).json()
    assert b["query"] == "infos"
    assert b["results"][0] == {"symbol": "INFY.NS", "nse_symbol": "INFY", "name": "Infosys Limited",
                               "isin": "INE009A01021", "series": "EQ"}
    assert len(client.get("/api/india/search", params={"q": "tata", "limit": 3}).json()["results"]) == 3
    assert client.get("/api/india/search", params={"q": "qqqqxxzz"}).json()["results"] == []
    assert client.get("/api/india/search", params={"q": ""}).status_code == 422
    assert client.get("/api/india/search", params={"q": "a", "limit": 51}).status_code == 422


def test_stocks_list(client):
    b = client.get("/api/india/stocks", params={"offset": 0, "limit": 5}).json()
    assert b["total"] > 2000 and len(b["stocks"]) == 5 and b["offset"] == 0 and b["limit"] == 5
    assert set(b["stocks"][0]) == {"symbol", "nse_symbol", "name", "isin", "series"}
    syms = [s["nse_symbol"] for s in b["stocks"]]
    assert syms == sorted(syms) and b["snapshot_date"]
    last = client.get("/api/india/stocks", params={"offset": b["total"] - 2, "limit": 10}).json()
    assert len(last["stocks"]) == 2
    assert client.get("/api/india/stocks", params={"limit": 501}).status_code == 422


def test_quotes_validation(client):
    many = ",".join(f"S{i}" for i in range(21))
    assert client.get("/api/india/quotes", params={"symbols": many}).status_code == 400
    assert client.get("/api/india/quotes", params={"symbols": " , "}).status_code == 400
    assert client.get("/api/india/intraday/reliance", params={"interval": "15m"}).status_code == 400


# ------------------------------------------------------------------ /api/india (network)
def test_quote(client):
    r = client.get("/api/india/quote/reliance")
    assert r.status_code == 200, r.text
    q = r.json()
    assert set(q) == QUOTE_KEYS and q["symbol"] == "RELIANCE.NS" and q["currency"] == "INR"
    assert q["price"] > 0 and q["display"]["price"].startswith("₹")
    assert client.get("/api/india/quote/ZZZZNOTREAL").status_code == 404


def test_quotes_batch(client):
    b = client.get("/api/india/quotes", params={"symbols": "RELIANCE,tcs,nifty,ZZZZNOTREAL"}).json()
    assert [q["symbol"] for q in b["quotes"]] == ["RELIANCE.NS", "TCS.NS", "^NSEI"]
    assert [e["symbol"] for e in b["errors"]] == ["ZZZZNOTREAL"]


def test_intraday(client):
    r = client.get("/api/india/intraday/reliance", params={"interval": "5m"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["symbol"] == "RELIANCE.NS" and b["interval"] == "5m" and b["session_date"]
    assert b["bars"] and set(b["bars"][0]) == {"time_ist", "open", "high", "low", "close", "volume"}
    assert b["bars"][0]["time_ist"].endswith("+05:30")


# ------------------------------------------------------------------ stocks: India fields
def test_stocks_tickers_universal(client):
    b = client.get("/api/stocks/tickers").json()
    assert b["universal"] is True and b["universal_info"]["kind"] == "universal"
    assert b["universal_info"]["trained_on"] >= 30


def test_forecast_universal_for_any_nse_stock(client):
    r = client.get("/api/stocks/infosys/forecast", params={"days": 3})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["ticker"] == b["normalized_ticker"] == "INFY.NS" and b["model"] == "universal"
    assert b["currency"] == "INR" and b["display"]["last_close"].startswith("₹")
    assert b["as_of_ist"].endswith("+05:30") and isinstance(b["market_open"], bool)
    assert len(b["forecast"]) == 3 and set(b["metrics"]) == {"naive_baseline", "rnn", "lstm"}
    assert len(b["test"]["dates"]) == len(b["test"]["actual"]) == len(b["test"]["rnn"]) == 120
    # the forecast stays near the last close (scale-free model, no explosion)
    assert all(abs(d["lstm"] / b["last_close"] - 1) < 0.2 for d in b["forecast"])


def test_forecast_model_choice(client):
    r = client.get("/api/stocks/reliance/forecast").json()
    assert r["ticker"] == "RELIANCE.NS" and r["model"] == "per_ticker"  # a per-ticker model exists
    u = client.get("/api/stocks/reliance/forecast", params={"model": "universal"}).json()
    assert u["model"] == "universal" and u["model_info"]["kind"] == "universal"
    assert client.get("/api/stocks/infosys/forecast", params={"model": "per_ticker"}).status_code == 404
    assert client.get("/api/stocks/AAPL/forecast", params={"model": "bogus"}).status_code == 422


def test_finance_india_fields(client):
    r = client.get("/api/finance/tcs/report")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["ticker"] == b["normalized_ticker"] == "TCS.NS" and b["currency"] == "INR"
    bm = b["benchmark"]
    assert bm["symbol"] == "^NSEI" and bm["name"] == "NIFTY 50"
    assert {"stock_return_1m", "index_return_1m", "stock_return_3m", "index_return_3m",
            "stock_return_1y", "index_return_1y", "beta"} <= set(bm)
    assert b["display"]["last_close"].startswith("₹") and b["as_of_ist"].endswith("+05:30")
    assert "sector" in b and "industry" in b and "market_cap_display" in b
    assert b["market_cap_display"] is None or "crore" in b["market_cap_display"]


# ------------------------------------------------------------------ ONNX parity (stocks)
def _onnx_fns(name):
    OnnxPredictor = stocks.ns().onnx_model.OnnxPredictor
    d = stocks.model_dir()
    return {c: OnnxPredictor(d / f"{name}_{c}.onnx") for c in stocks.CELLS}


@pytest.mark.parametrize("name,ticker", [("universal", "RELIANCE.NS"), ("universal", "AAPL"),
                                         ("AAPL", "AAPL"), ("RELIANCE.NS", "RELIANCE.NS")])
def test_stock_onnx_matches_torch(name, ticker):
    # stocks.ns() is the full (torch) namespace here; onnx_model is loaded alongside
    ns = loader.load_modules(loader.project_dir("stocks"), ["universal", "onnx_model", "data"])
    U = ns.universal
    torch_fns = stocks.predictors(name)
    onnx_fns = {c: ns.onnx_model.OnnxPredictor(stocks.model_dir() / f"{name}_{c}.onnx")
                for c in stocks.CELLS}
    prices = ns.data.load_prices(ticker)
    if name == "universal":
        scale = U.stock_scale(np.log(prices.values))
    else:
        scale = json.loads((stocks.model_dir() / f"{name}_meta.json").read_text())["scale"]
    for c in stocks.CELLS:
        a = np.array(U.forecast(torch_fns[c], prices.values, 10, scale))
        b = np.array(U.forecast(onnx_fns[c], prices.values, 10, scale))
        assert np.max(np.abs(a - b) / a) < 1e-5
    bt_t = U.backtest(torch_fns, prices)["predictions"]
    bt_o = U.backtest(onnx_fns, prices)["predictions"]
    for c in stocks.CELLS:
        assert np.max(np.abs(np.array(bt_t[c]) - bt_o[c]) / np.array(bt_t[c])) < 1e-5


# ------------------------------------------------------------------ ONNX parity (YOLO)
@pytest.mark.parametrize("model", ["yolo11n", "yolo11s"])
@pytest.mark.parametrize("image", ["bus.jpg", "zidane.jpg"])
def test_yolo_onnx_matches_ultralytics(model, image):
    import cv2

    from app.routers import vision
    from app.yolo_onnx import OnnxYolo

    root = loader.project_dir("objects")
    ref, _ = vision.yolo(f"{model}.pt")
    onx = OnnxYolo(root / "weights" / f"{model}.onnx")
    img = cv2.imread(str(root / "samples" / image))
    for conf, iou, classes in [(0.25, 0.7, None), (0.1, 0.5, None), (0.25, 0.7, ["person"])]:
        a = ref.detect(img, conf=conf, iou=iou, classes=classes)
        b = onx.detect(img, conf=conf, iou=iou, classes=classes)
        assert a.counts == b.counts
        assert [d.cls_name for d in a.detections] == [d.cls_name for d in b.detections]
        if a.detections:
            assert np.abs(np.array([d.box for d in a.detections]) - [d.box for d in b.detections]).max() < 2.0
            assert np.abs(np.array([d.conf for d in a.detections]) - [d.conf for d in b.detections]).max() < 1e-3
        assert a.annotated.shape == b.annotated.shape


# ------------------------------------------------------------------ slim profile end to end
def test_slim_profile_subprocess():
    """The slim server answers every endpoint without importing torch/ultralytics, and its
    numbers match this (full) process."""
    env = dict(os.environ, SERVER_PROFILE="slim", PRELOAD="0")
    r = subprocess.run([sys.executable, str(SERVER / "tests" / "slim_smoke.py")], cwd=SERVER, env=env,
                       capture_output=True, text=True, timeout=900)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["fails"] == [] and out["heavy_modules"] == [], (out["fails"], r.stderr[-2000:])
    full = stocks.forecast_body("RELIANCE.NS", 5, "universal")
    slim = out["stocks_reliance_universal"]
    assert slim["lstm"] == [d["lstm"] for d in full["forecast"]]
    assert slim["rnn"] == [d["rnn"] for d in full["forecast"]]
    full_aapl = stocks.forecast_body("AAPL", 5, "per_ticker")
    assert out["stocks_aapl"]["lstm"] == [d["lstm"] for d in full_aapl["forecast"]]
