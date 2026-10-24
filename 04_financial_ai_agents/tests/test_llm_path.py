"""LLM-path checks without a key or network.

The SDK client is built on an httpx MockTransport, so the real `anthropic`
request serialisation runs but nothing leaves the machine.
"""
import json

import anthropic
import httpx2 as httpx  # anthropic >= 1.x is built on httpx2
import pandas as pd
import pytest

import agents
import llm
from indicators import compute_indicators


def make_data():
    idx = pd.bdate_range("2024-01-01", periods=300)
    close = pd.Series(range(100, 400), index=idx, dtype=float)
    df = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1}, index=idx)
    return {
        "ticker": "TEST",
        "indicators": compute_indicators(df),
        "fundamentals": {"profile": {"longName": "Test Co"}, "stats": {"trailingPE": 20.0}},
        "news": [{"title": "Test Co beats estimates", "publisher": "X", "date": "2026-01-01", "link": ""}],
    }


def mock_client(monkeypatch, reply: dict, status: int = 200, stop_reason: str = "end_turn"):
    """Install an SDK client whose transport records requests and returns `reply`."""
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append({"url": str(request.url), "headers": request.headers, "body": json.loads(request.content)})
        if status != 200:
            return httpx.Response(status, json={"type": "error", "error": {"type": "api_error", "message": "boom"}})
        return httpx.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": llm.MODEL,
            "content": [{"type": "text", "text": json.dumps(reply)}],
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    client = anthropic.Anthropic(api_key="test-not-a-real-key", max_retries=0,
                                 http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(llm, "_client", client)
    return sent


FINDING = {"stance": "bullish", "summary": "Uptrend.", "bullish_points": ["a"], "bearish_points": []}


def test_specialist_request_shape(monkeypatch):
    sent = mock_client(monkeypatch, FINDING)
    f = agents.TechnicalAnalyst().run(make_data(), use_llm=True, model="claude-opus-5-5")
    assert f.source == "llm" and f.stance == "bullish" and f.summary == "Uptrend."
    req = sent[0]
    assert req["url"] == "https://api.anthropic.com/v1/messages"
    body = req["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["system"].startswith("You are the Technical Analyst")
    assert body["messages"][0]["role"] == "user" and "rsi14" in body["messages"][0]["content"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["format"]["schema"] == agents.FINDING_SCHEMA
    assert body["output_config"]["effort"] == llm.EFFORT
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req["headers"]["anthropic-beta"]
    assert "temperature" not in body and "thinking" not in body


def test_lead_report_from_llm(monkeypatch):
    reply = {"summary": "s", "bullish_points": ["b"], "bearish_points": ["x"], "key_risks": ["r"],
             "outlook": "neutral", "confidence": "medium", "outlook_rationale": "why"}
    sent = mock_client(monkeypatch, reply)
    data = make_data()
    findings = [agents.Finding("Technical Analyst", "bullish", "t")]
    report = agents.LeadAnalyst().run(data, findings, use_llm=True)
    assert report["outlook"] == "neutral" and report["source"] == "llm"
    assert sent[0]["body"]["output_config"]["format"]["schema"] == agents.REPORT_SCHEMA
    assert "Technical Analyst" in sent[0]["body"]["messages"][0]["content"]


@pytest.mark.parametrize("status,stop", [(500, "end_turn"), (200, "refusal")])
def test_falls_back_to_rules(monkeypatch, status, stop):
    mock_client(monkeypatch, FINDING, status=status, stop_reason=stop)
    f = agents.NewsAnalyst().run(make_data(), use_llm=True)
    assert f.source == "rules" and "LLM call failed" in f.note


def test_mode_detection(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not llm.llm_available()
    assert "Offline" in llm.mode_label(False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert llm.llm_available()
    assert "claude-opus-5-5" in llm.mode_label(True)
