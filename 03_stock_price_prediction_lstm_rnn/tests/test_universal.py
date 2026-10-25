"""Universal-model helpers (offline) + a headless dashboard smoke test (real Yahoo data)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import universal as U

ROOT = Path(__file__).resolve().parents[1]


def walk(n=600, seed=0, start=100.0):
    rng = np.random.default_rng(seed)
    return pd.Series(start * np.exp(np.cumsum(rng.normal(0, 0.015, n))),
                     index=pd.bdate_range("2023-01-02", periods=n))


def test_universe_file():
    train, hold = U.read_universe()
    assert 40 <= len(train) <= 60 and len(hold) >= 5
    assert train[0] == "RELIANCE.NS" and "M&M.NS" in train and "BAJAJ-AUTO.NS" in train
    assert not set(train) & set(hold)


def test_scale_free_windows():
    p = walk()
    (parts, scale) = U.stock_windows(p, p.index[400], p.index[500])
    X, y, dates, prev, actual = parts["train"]
    assert X.shape[1:] == (U.WINDOW, 1) and np.all(X[:, -1, 0] == 0)  # relative to the last day
    assert scale == pytest.approx(0.015, rel=0.15)
    # the same series at 100x the price gives identical inputs
    parts2, scale2 = U.stock_windows(p * 100, p.index[400], p.index[500])
    assert scale2 == pytest.approx(scale) and np.allclose(parts2["train"][0], X, atol=1e-5)
    assert len(parts["test"][0]) == 100 and dates.max() < p.index[400]


def test_forecast_and_backtest_with_dummy_model():
    p = walk()
    zero = lambda X: np.zeros(len(X), np.float32)  # predicts "no change"  # noqa: E731
    fc = U.forecast(zero, p.values, 5, 0.015)
    assert fc == pytest.approx([p.iloc[-1]] * 5)
    bt = U.backtest({"rnn": zero, "lstm": zero}, p)
    assert len(bt["dates"]) == U.BACKTEST_DAYS
    assert bt["results"]["rnn"]["rmse"] == pytest.approx(bt["results"]["naive_baseline"]["rmse"])
    up = lambda X: np.ones(len(X), np.float32)  # noqa: E731
    assert U.forecast(up, p.values, 1, 0.01)[0] == pytest.approx(p.iloc[-1] * np.exp(0.01))


def test_pooled_metrics():
    rows = [{"actual": np.array([101.0, 99.0]), "prev": np.array([100.0, 101.0]),
             "rnn": np.array([100.5, 100.0])}]
    m = U.pooled_metrics(rows)
    assert m["naive_baseline"]["mean_rmse_ratio_vs_naive"] == 1.0
    assert m["rnn"]["mean_rmse_ratio_vs_naive"] < 1.0 and m["rnn"]["stocks_beating_naive_rmse"] == 1
    assert m["rnn"]["direction_acc_pct"] == 100.0 and m["up_days_pct"] == 50.0


def test_short_history_rejected():
    with pytest.raises(ValueError):
        U.backtest({"x": lambda X: np.zeros(len(X))}, walk(80))


@pytest.mark.skipif(not (ROOT / "models" / "universal_meta.json").exists(), reason="universal model not trained")
def test_dashboard_universal_default():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()
    assert not at.exception
    assert "RELIANCE.NS" in at.subheader[0].value
    assert any(m.value.startswith("₹") for m in at.metric)
    text = " ".join(m.value for m in at.markdown)
    assert "Walk-forward check" in text and "forecast" in text
    at.text_input[0].set_value("infosys").run()
    assert not at.exception and "INFY.NS" in at.subheader[0].value
