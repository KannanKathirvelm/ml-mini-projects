"""Orchestrator: fetch data once, run the specialists, then the lead agent.

Shared by the CLI and the dashboard so both produce identical reports.
"""
import time
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

import llm
from agents import INDIA_DATA_GAP, SPECIALISTS, Finding, LeadAnalyst
from data_tools import (TickerNotFound, benchmark_for, get_fundamentals, get_index_close,
                        get_market_pe, get_news, get_price_history)
from india import data_as_of, fmt_ist, format_money, is_indian, normalize_ticker
from indicators import benchmark_stats, compute_indicators

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


def get_benchmark(ticker: str, history: pd.DataFrame, currency: str | None) -> dict | None:
    """Stock vs Nifty 50 (Indian symbols) or S&P 500 (others); None if the index fails."""
    symbol, name = benchmark_for(ticker, currency)
    index = get_index_close(symbol)
    if index is None:
        return None
    return {"symbol": symbol, "name": name, **benchmark_stats(history["Close"], index)}


def run_analysis(ticker: str, use_llm: bool | None = None, model: str | None = None) -> Analysis:
    """Raises data_tools.TickerNotFound for an unknown symbol.

    `ticker` goes through india.normalize_ticker, so "reliance" analyses RELIANCE.NS.
    """
    try:
        ticker = normalize_ticker(ticker)
    except ValueError as exc:
        raise TickerNotFound(str(exc)) from exc
    use_llm = llm.llm_available() if use_llm is None else use_llm
    history = get_price_history(ticker)
    fetched_at = time.time()
    fundamentals = get_fundamentals(ticker)
    currency = fundamentals["profile"].get("currency")
    indian = is_indian(ticker, currency)
    data = {
        "ticker": ticker,
        "currency": currency,
        "is_indian": indian,
        "as_of": data_as_of(ticker, history.index[-1].date(), fetched_at),
        "indicators": compute_indicators(history),
        "benchmark": get_benchmark(ticker, history, currency),
        "fundamentals": fundamentals,
        "market_pe": get_market_pe() if indian else None,
        "news": get_news(ticker, fundamentals["profile"].get("longName")),
    }
    findings = [agent.run(data, use_llm, model) for agent in SPECIALISTS]
    report = LeadAnalyst().run(data, findings, use_llm, model)
    return Analysis(ticker, llm.mode_label(use_llm, model), data, findings, report, history)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- (none)"


def _pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def benchmark_table(b: dict | None) -> list[str]:
    """Markdown rows: stock vs index over 1m / 3m / 1y, plus beta."""
    if not b:
        return ["Benchmark data was not available."]
    rows = [f"| Period | Stock | {b['name']} |", "|---|---|---|"]
    rows += [f"| {lbl} | {_pct(b[f'stock_return_{k}'])} | {_pct(b[f'index_return_{k}'])} |"
             for k, lbl in (("1m", "1 month"), ("3m", "3 months"), ("1y", "1 year"))]
    beta = "n/a" if b.get("beta") is None else f"{b['beta']:.2f}"
    return rows + ["", f"Beta vs {b['name']} (1y daily returns): {beta}. "
                       f"Relative strength (1y): {_pct(b.get('relative_strength_1y'))}."]


def to_markdown(a: Analysis) -> str:
    r, p, ind = a.report, a.data["fundamentals"]["profile"], a.data["indicators"]
    cur = p.get("currency")
    stats = a.data["fundamentals"]["stats"]
    facts = [f"Sector: {p['sector']}" if p.get("sector") else "",
             f"Industry: {p['industry']}" if p.get("industry") else "",
             f"Market cap: {format_money(stats['marketCap'], cur, compact=True)}" if stats.get("marketCap") else ""]
    lines = [
        f"# Market insight: {p.get('longName', a.ticker)} ({a.ticker})",
        "",
        f"*Generated {a.generated} | {a.mode} | Last close {format_money(ind['last_close'], cur)} "
        f"({ind['last_date']}) | Data as of {fmt_ist(a.data['as_of']['as_of_ist'])}*",
        "",
        f"*{a.data['as_of']['note']}*",
        "",
        " | ".join(f for f in facts if f) or "",
        "",
        f"**Outlook: {r['outlook'].upper()}** (confidence: {r['confidence']})",
        "",
        "## Summary", r["summary"], "",
        "## Bullish points", _bullets(r["bullish_points"]), "",
        "## Bearish points", _bullets(r["bearish_points"]), "",
        "## Key risks", _bullets(r["key_risks"]), "",
        "## Overall outlook", r["outlook_rationale"], "",
        f"## Benchmark: vs {(a.data.get('benchmark') or {}).get('name', 'index')}",
        *benchmark_table(a.data.get("benchmark")), "",
    ]
    if a.data.get("is_indian"):
        lines += [f"*{INDIA_DATA_GAP}*", ""]
    lines += [
        "## Agent findings",
    ]
    for f in a.findings:
        lines += ["", f"### {f.agent}: {f.stance}", f.summary]
        if f.note:
            lines.append(f"*{f.note}*")
    if a.data["news"]:
        lines += ["", "## Recent headlines"]
        lines += [f"- {n['date']} {n['title']} ({n['publisher']})" for n in a.data["news"]]
    if a.data.get("is_indian") and len(a.data["news"]) < 3:
        lines += ["", f"*Only {len(a.data['news'])} relevant headline(s) found on Yahoo for this "
                      "Indian symbol; news coverage is sparse, so the sentiment view is weak.*"]
    if r.get("note"):
        lines += ["", f"*{r['note']}*"]
    lines += ["", "---", f"**Disclaimer:** {DISCLAIMER}", ""]
    return "\n".join(lines)
