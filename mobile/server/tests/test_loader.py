"""All 7 projects load side by side despite clashing bare module names."""
import sys
from pathlib import Path

import cv2
import pandas as pd

from app import loader

CLASHING = {"predict", "train", "data", "features", "config", "generate_data", "model",
            "detector", "detectors", "draw", "db", "search", "history", "stores", "llm",
            "agents", "pipeline", "indicators", "data_tools", "matching", "alerts", "india",
            "universal", "onnx_model"}

SPECS = {
    "credit-card": ["predict", "generate_data", "train"],
    "upi": ["predict", "features", "generate_data", "train"],
    "stocks": ["train", "data", "model", "predict", "universal", "onnx_model", "india"],
    "finance": ["llm", "indicators", "data_tools", "agents", "pipeline"],
    "prices": ["config", "matching", "stores", "db", "search", "history", "alerts"],
    "faces": ["detectors", "draw"],
    "objects": ["config", "detector"],
}


def test_load_all_seven_in_isolation():
    spaces = {k: loader.load_modules(loader.project_dir(k), mods) for k, mods in SPECS.items()}
    # nothing bare-named is left behind in sys.modules
    assert not (CLASHING & set(sys.modules)), CLASHING & set(sys.modules)
    # every module came from its own project folder
    for key, ns in spaces.items():
        root = loader.project_dir(key).resolve()
        for name, mod in vars(ns).items():
            if name.startswith("__"):
                continue
            assert Path(mod.__file__).resolve().is_relative_to(root), (key, name, mod.__file__)
    # same bare names, different modules
    assert spaces["credit-card"].predict is not spaces["upi"].predict
    assert spaces["credit-card"].train is not spaces["stocks"].train
    assert spaces["prices"].config is not spaces["objects"].config
    # transitive bare imports resolved inside the right project
    assert spaces["stocks"].predict.load_prices is spaces["stocks"].data.load_prices
    assert spaces["upi"].predict.build_features is spaces["upi"].features.build_features

    # ...and each one actually works
    cc = spaces["credit-card"]
    bundle = cc.predict.load()
    row = pd.DataFrame([{"amount": 950, "hour": 2, "distance_from_home_km": 400,
                         "distance_from_last_txn_km": 300, "ratio_to_median_amount": 6,
                         "online_order": 1, "used_chip": 0, "used_pin": 0,
                         "txn_count_last_24h": 8, "merchant_category": "electronics"}])
    assert cc.predict.score(row, bundle).iloc[0].flagged == 1

    upi = spaces["upi"]
    b = upi.predict.load()
    raw = pd.DataFrame([{"payee_vpa": "refund.helpdesk42@ybl", "amount": 4999, "hour": 11,
                         "txn_type": "P2P", "mode": "collect_request", "is_new_payee": 1,
                         "payee_account_age_days": 4, "payee_fraud_reports": 2,
                         "device_changed_48h": 0, "sim_changed_48h": 0,
                         "failed_pin_attempts_24h": 0, "txns_last_1h": 1,
                         "amount_to_avg_ratio": 5.0, "remark": "refund processing"}])
    assert upi.predict.score(raw, b).iloc[0].risk_level == "HIGH"

    st = spaces["stocks"]
    prices, fc = st.predict.future_forecast("AAPL", 3)
    assert len(fc) == 3 and set(fc.columns) == {"rnn", "lstm"}

    fin = spaces["finance"]
    assert fin.llm.mode_label(False).startswith("Offline")
    assert fin.agents.headline_sentiment("Apple shares surge to record") == 1

    pr = spaces["prices"]
    shop = pr.stores.simulated_stores()[0]
    assert shop.search("iphone")
    assert pr.matching.same_product("Apple iPhone 13 Pro", "iPhone 13 Pro")

    fd = spaces["faces"]
    img = cv2.imread(str(loader.project_dir("faces") / "samples" / "lena.jpg"))
    faces = fd.detectors.make_detector("dnn").detect(img)
    assert len(faces) >= 1 and fd.draw.annotate(img, faces).shape == img.shape
    assert fd.detectors.make_detector("haar").detect(img)

    ob = spaces["objects"]
    r = ob.detector.Detector("yolo11n.pt", device="cpu").detect(
        str(loader.project_dir("objects") / "samples" / "bus.jpg"))
    assert "person" in r.counts


def test_opencv_is_v4_with_cascade():
    assert cv2.__version__.startswith("4.")
    assert hasattr(cv2, "CascadeClassifier")
