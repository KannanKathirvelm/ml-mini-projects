"""Headless dashboard smoke test (real Yahoo data, offline mode)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_dashboard_renders_report(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Summary" in text and "Key risks" in text and "Offline mode" in text
    assert len(at.tabs) == 4


def test_dashboard_bad_ticker(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.text_input[0].set_value("ZZZZNOTREAL").run()
    assert not at.exception
    assert any("No price data" in e.value for e in at.error)


def test_dashboard_india_name_resolution(monkeypatch):
    """Typing a company name resolves to the NSE symbol; ₹ and the Nifty benchmark are shown."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.text_input[0].set_value("infosys").run()
    assert not at.exception
    assert any("INFY.NS" in c.value for c in at.caption)
    text = " ".join(m.value for m in at.markdown)
    assert "NIFTY 50" in text and "₹" in text
    assert any(m.value.startswith("₹") for m in at.metric)
