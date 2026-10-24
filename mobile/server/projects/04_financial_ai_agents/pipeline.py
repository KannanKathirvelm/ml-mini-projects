"""Orchestrator: fetch data once, run the specialists, then the lead agent.

Shared by the CLI and the dashboard so both produce identical reports.
"""
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

import llm
from agents import SPECIALISTS, Finding, LeadAnalyst
from data_tools import get_fundamentals, get_news, get_price_history
from indicators import compute_indicators

DISCLAIMER = ("Not financial advice. This report is generated automatically for educational "
              "purposes from public Yahoo Finance data and may be inaccurate or out of date.")


@dataclass
class Analysis:
    ticker: str
    mode: str
    data: dict
    findings: list[Finding]
    report: dict
    history: pd.DataFrame = field(repr=False, default=None)
    generated: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))


def run_analysis(ticker: str, use_llm: bool | None = None, model: str | None = None) -> Analysis:
    """Raises data_tools.TickerNotFound for an unknown symbol."""
    ticker = ticker.strip().upper()
    use_llm = llm.llm_available() if use_llm is None else use_llm
    history = get_price_history(ticker)
    fundamentals = get_fundamentals(ticker)
    data = {
        "ticker": ticker,
        "indicators": compute_indicators(history),
        "fundamentals": fundamentals,
        "news": get_news(ticker, fundamentals["profile"].get("longName")),
    }
    findings = [agent.run(data, use_llm, model) for agent in SPECIALISTS]
    report = LeadAnalyst().run(data, findings, use_llm, model)
    return Analysis(ticker, llm.mode_label(use_llm, model), data, findings, report, history)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- (none)"


def to_markdown(a: Analysis) -> str:
    r, p, ind = a.report, a.data["fundamentals"]["profile"], a.data["indicators"]
    cur = p.get("currency", "")
    lines = [
        f"# Market insight: {p.get('longName', a.ticker)} ({a.ticker})",
        "",
        f"*Generated {a.generated} | {a.mode} | Last close {ind['last_close']:,.2f} {cur} "
        f"({ind['last_date']})*",
        "",
        f"**Outlook: {r['outlook'].upper()}** (confidence: {r['confidence']})",
        "",
        "## Summary", r["summary"], "",
        "## Bullish points", _bullets(r["bullish_points"]), "",
        "## Bearish points", _bullets(r["bearish_points"]), "",
        "## Key risks", _bullets(r["key_risks"]), "",
        "## Overall outlook", r["outlook_rationale"], "",
        "## Agent findings",
    ]
    for f in a.findings:
        lines += ["", f"### {f.agent}: {f.stance}", f.summary]
        if f.note:
            lines.append(f"*{f.note}*")
    if a.data["news"]:
        lines += ["", "## Recent headlines"]
        lines += [f"- {n['date']} {n['title']} ({n['publisher']})" for n in a.data["news"]]
    if r.get("note"):
        lines += ["", f"*{r['note']}*"]
    lines += ["", "---", f"**Disclaimer:** {DISCLAIMER}", ""]
    return "\n".join(lines)
