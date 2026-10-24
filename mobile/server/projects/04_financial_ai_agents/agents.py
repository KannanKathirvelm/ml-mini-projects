"""The specialist agents and the lead agent that combines them.

Each agent has one role, a system prompt for LLM mode, and a deterministic
`rules()` method for offline mode. Both paths return the same `Finding` shape,
so the lead agent and the UI never care which mode produced it. If a Claude
call fails, the agent falls back to its rules and records why in `note`.
"""
import json
from dataclasses import asdict, dataclass, field

import llm

STANCES = ["bullish", "neutral", "bearish"]

FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "stance": {"type": "string", "enum": STANCES},
        "summary": {"type": "string"},
        "bullish_points": {"type": "array", "items": {"type": "string"}},
        "bearish_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["stance", "summary", "bullish_points", "bearish_points"],
    "additionalProperties": False,
}

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "bullish_points": {"type": "array", "items": {"type": "string"}},
        "bearish_points": {"type": "array", "items": {"type": "string"}},
        "key_risks": {"type": "array", "items": {"type": "string"}},
        "outlook": {"type": "string", "enum": STANCES},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "outlook_rationale": {"type": "string"},
    },
    "required": ["summary", "bullish_points", "bearish_points", "key_risks",
                 "outlook", "confidence", "outlook_rationale"],
    "additionalProperties": False,
}

STYLE = (
    "Be concrete and cite the numbers you were given. Do not invent data that is not in "
    "the input; if something is missing, say so. Keep each point to one sentence. "
    "This is educational analysis, not investment advice."
)


@dataclass
class Finding:
    agent: str
    stance: str
    summary: str
    bullish_points: list[str] = field(default_factory=list)
    bearish_points: list[str] = field(default_factory=list)
    source: str = "rules"  # "rules" or "llm"
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(x, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:+.{digits}f}%"


def _stance_from_score(score: float, threshold: float = 1.0) -> str:
    return "bullish" if score >= threshold else "bearish" if score <= -threshold else "neutral"


class Agent:
    name = "Agent"
    role = ""

    def rules(self, data: dict) -> Finding:
        raise NotImplementedError

    def prompt(self, data: dict) -> str:
        raise NotImplementedError

    def run(self, data: dict, use_llm: bool, model: str | None = None) -> Finding:
        if not use_llm:
            return self.rules(data)
        try:
            out = llm.ask_json(f"You are the {self.name}. {self.role} {STYLE}",
                               self.prompt(data), FINDING_SCHEMA, model)
            return Finding(agent=self.name, source="llm", **out)
        except llm.LLMError as exc:
            finding = self.rules(data)
            finding.note = f"LLM call failed ({exc}); used rule-based analysis."
            return finding


class TechnicalAnalyst(Agent):
    name = "Technical Analyst"
    role = "You read price trend, moving averages, momentum (RSI, MACD), volatility and drawdown."

    def prompt(self, data: dict) -> str:
        return (f"Ticker: {data['ticker']}\nTechnical indicators (returns/volatility as fractions):\n"
                f"{json.dumps(data['indicators'], indent=2)}\n\nGive your technical view.")

    def rules(self, data: dict) -> Finding:
        ind = data["indicators"]
        px, s50, s200 = ind["last_close"], ind["sma50"], ind["sma200"]
        bull, bear, score = [], [], 0.0

        if s50:
            if px > s50:
                score += 1; bull.append(f"Price {px:,.2f} is above the 50-day SMA ({s50:,.2f}).")
            else:
                score -= 1; bear.append(f"Price {px:,.2f} is below the 50-day SMA ({s50:,.2f}).")
        if s200:
            if px > s200:
                score += 1; bull.append(f"Price is above the 200-day SMA ({s200:,.2f}): long-term uptrend.")
            else:
                score -= 1; bear.append(f"Price is below the 200-day SMA ({s200:,.2f}): long-term downtrend.")
        if s50 and s200:
            if s50 > s200:
                score += 0.5; bull.append("50-day SMA is above the 200-day SMA (golden-cross alignment).")
            else:
                score -= 0.5; bear.append("50-day SMA is below the 200-day SMA (death-cross alignment).")

        r = ind["rsi14"]
        if r >= 70:
            score -= 0.5; bear.append(f"RSI(14) is {r:.0f}: overbought, pullback risk.")
        elif r <= 30:
            score += 0.5; bull.append(f"RSI(14) is {r:.0f}: oversold, rebound potential.")
        elif r >= 50:
            score += 0.25; bull.append(f"RSI(14) is {r:.0f}: positive momentum without being overbought.")
        else:
            score -= 0.25; bear.append(f"RSI(14) is {r:.0f}: momentum is soft.")

        if ind["macd"] > ind["macd_signal"]:
            score += 1; bull.append("MACD is above its signal line (bullish momentum).")
        else:
            score -= 1; bear.append("MACD is below its signal line (bearish momentum).")

        r3 = ind["return_3m"]
        if r3 is not None:
            (bull if r3 > 0 else bear).append(f"3-month return is {_pct(r3)}.")
            score += 0.5 if r3 > 0 else -0.5

        if ind["volatility_1y"] > 0.45:
            bear.append(f"High annualised volatility ({_pct(ind['volatility_1y'], 0)[1:]}).")
        if ind["drawdown_from_52w_high"] < -0.2:
            bear.append(f"Trading {_pct(ind['drawdown_from_52w_high'])} below its 52-week high.")

        stance = _stance_from_score(score, 1.5)
        summary = (f"Technical picture is {stance} (score {score:+.2f}). RSI {r:.0f}, "
                   f"1-year volatility {ind['volatility_1y']:.0%}, max 1-year drawdown "
                   f"{ind['max_drawdown_1y']:.0%}, 1-year return {_pct(ind['return_1y'])}.")
        return Finding(self.name, stance, summary, bull, bear)


class FundamentalAnalyst(Agent):
    name = "Fundamental Analyst"
    role = "You assess valuation, profitability, growth and balance-sheet strength from key stats."

    def prompt(self, data: dict) -> str:
        f = data["fundamentals"]
        return (f"Ticker: {data['ticker']}\nProfile: {json.dumps(f['profile'])}\n"
                f"Key stats from Yahoo Finance (margins/growth/ROE as fractions; dividendYield and "
                f"debtToEquity already in percent):\n{json.dumps(f['stats'], indent=2)}\n\n"
                "Give your fundamental view. Missing fields simply were not reported.")

    def rules(self, data: dict) -> Finding:
        s = data["fundamentals"]["stats"]
        bull, bear, score = [], [], 0.0

        pe = s.get("forwardPE") or s.get("trailingPE")
        if pe is not None:
            if pe <= 0:
                score -= 1; bear.append("Negative P/E: the company is not currently profitable.")
            elif pe < 15:
                score += 1; bull.append(f"Modest valuation at P/E {pe:.1f}.")
            elif pe > 35:
                score -= 1; bear.append(f"Rich valuation at P/E {pe:.1f}; high expectations priced in.")
            else:
                bull.append(f"P/E {pe:.1f} is within a typical range.")
        peg = s.get("pegRatio")
        if peg is not None and peg > 0:
            if peg < 1:
                score += 0.5; bull.append(f"PEG {peg:.2f} < 1: growth looks cheap relative to price.")
            elif peg > 2.5:
                score -= 0.5; bear.append(f"PEG {peg:.2f} is high relative to expected growth.")

        pm = s.get("profitMargins")
        if pm is not None:
            if pm > 0.15:
                score += 1; bull.append(f"Strong profit margin of {pm:.0%}.")
            elif pm < 0.05:
                score -= 1; bear.append(f"Thin profit margin of {pm:.1%}.")
        roe = s.get("returnOnEquity")
        if roe is not None:
            if roe > 0.15:
                score += 0.5; bull.append(f"High return on equity ({roe:.0%}).")
            elif roe < 0.05:
                score -= 0.5; bear.append(f"Weak return on equity ({roe:.1%}).")

        for key, label in (("revenueGrowth", "Revenue"), ("earningsGrowth", "Earnings")):
            g = s.get(key)
            if g is None:
                continue
            if g > 0.1:
                score += 0.75; bull.append(f"{label} growing {g:.0%} year over year.")
            elif g < 0:
                score -= 0.75; bear.append(f"{label} down {abs(g):.0%} year over year.")

        de = s.get("debtToEquity")
        if de is not None:
            if de > 150:
                score -= 1; bear.append(f"High leverage: debt/equity {de:.0f}%.")
            elif de < 50:
                score += 0.5; bull.append(f"Conservative balance sheet: debt/equity {de:.0f}%.")

        target, price = s.get("targetMeanPrice"), s.get("currentPrice")
        if target and price:
            upside = target / price - 1
            (bull if upside > 0 else bear).append(
                f"Analyst mean target {target:,.2f} implies {_pct(upside)} vs current price.")
            score += 0.5 if upside > 0.1 else -0.5 if upside < -0.05 else 0
        rec = s.get("recommendationKey")
        if rec in ("buy", "strong_buy"):
            bull.append(f"Analyst consensus: {rec.replace('_', ' ')}.")
        elif rec in ("sell", "strong_sell", "underperform"):
            bear.append(f"Analyst consensus: {rec.replace('_', ' ')}.")

        if not s:
            return Finding(self.name, "neutral", "No fundamental data was available for this symbol.", [], [])
        stance = _stance_from_score(score, 1.5)
        summary = (f"Fundamentals look {stance} (score {score:+.2f}) based on "
                   f"{len(s)} reported metrics.")
        return Finding(self.name, stance, summary, bull, bear)


POSITIVE_WORDS = {
    "beat", "beats", "surge", "surges", "soar", "soars", "rally", "rallies", "gain", "gains",
    "record", "upgrade", "upgraded", "strong", "growth", "profit", "jump", "jumps", "rise",
    "rises", "bullish", "outperform", "buy", "boost", "expands", "wins", "partnership", "high",
}
NEGATIVE_WORDS = {
    "miss", "misses", "fall", "falls", "drop", "drops", "plunge", "plunges", "slump", "cut",
    "cuts", "downgrade", "downgraded", "weak", "loss", "losses", "lawsuit", "probe", "fine",
    "bearish", "sell", "warns", "warning", "decline", "declines", "risk", "layoffs", "tumble", "hit",
}


def headline_sentiment(title: str) -> int:
    """+1 / 0 / -1 from a simple keyword count. Crude, but transparent."""
    words = {w.strip(".,:;!?'\"()").lower() for w in title.split()}
    score = len(words & POSITIVE_WORDS) - len(words & NEGATIVE_WORDS)
    return (score > 0) - (score < 0)


class NewsAnalyst(Agent):
    name = "News & Sentiment Analyst"
    role = "You judge the tone of recent headlines and what they could mean for the stock."

    def prompt(self, data: dict) -> str:
        heads = "\n".join(f"- [{n['date']}] {n['title']} ({n['publisher']})" for n in data["news"])
        return (f"Ticker: {data['ticker']}\nRecent headlines:\n{heads or '(none available)'}\n\n"
                "Assess overall news sentiment. Some headlines may be market-wide rather than "
                "company-specific; weigh them accordingly.")

    def rules(self, data: dict) -> Finding:
        news = data["news"]
        if not news:
            return Finding(self.name, "neutral", "No recent headlines were available; sentiment is unknown.")
        scored = [(headline_sentiment(n["title"]), n["title"]) for n in news]
        pos = [t for s, t in scored if s > 0]
        neg = [t for s, t in scored if s < 0]
        net = (len(pos) - len(neg)) / len(scored)
        stance = "bullish" if net >= 0.2 else "bearish" if net <= -0.2 else "neutral"
        summary = (f"{len(scored)} headlines: {len(pos)} positive, {len(neg)} negative, "
                   f"{len(scored) - len(pos) - len(neg)} neutral (keyword sentiment, net {net:+.2f}).")
        return Finding(self.name, stance, summary,
                       [f'Positive headline: "{t}"' for t in pos[:4]],
                       [f'Negative headline: "{t}"' for t in neg[:4]])


class LeadAnalyst:
    """Combines the specialists into the final report."""

    name = "Lead Analyst"
    weights = {"Technical Analyst": 0.4, "Fundamental Analyst": 0.4, "News & Sentiment Analyst": 0.2}

    def run(self, data: dict, findings: list[Finding], use_llm: bool, model: str | None = None) -> dict:
        if use_llm:
            try:
                report = llm.ask_json(
                    "You are the Lead Analyst of an equity research team. Combine your specialists' "
                    "findings into a balanced market-insight report. Resolve disagreements "
                    f"explicitly and list concrete key risks. {STYLE}",
                    self._prompt(data, findings), REPORT_SCHEMA, model)
                report["source"] = "llm"
                return report
            except llm.LLMError as exc:
                report = self.rules(data, findings)
                report["note"] = f"LLM call failed ({exc}); used rule-based synthesis."
                return report
        return self.rules(data, findings)

    def _prompt(self, data: dict, findings: list[Finding]) -> str:
        return (f"Ticker: {data['ticker']} ({data['fundamentals']['profile'].get('longName', '')})\n"
                f"Specialist findings:\n{json.dumps([f.to_dict() for f in findings], indent=2)}\n\n"
                f"Key indicators: {json.dumps(data['indicators'])}\n\nWrite the final report.")

    def rules(self, data: dict, findings: list[Finding]) -> dict:
        value = {"bullish": 1, "neutral": 0, "bearish": -1}
        score = sum(self.weights.get(f.agent, 0.2) * value[f.stance] for f in findings)
        outlook = "bullish" if score >= 0.25 else "bearish" if score <= -0.25 else "neutral"
        stances = [f.stance for f in findings]
        agree = max(stances.count(s) for s in STANCES)
        confidence = "high" if agree == len(findings) else "medium" if agree >= 2 else "low"

        name = data["fundamentals"]["profile"].get("longName", data["ticker"])
        views = ", ".join(f"{f.agent.split(' ')[0].lower()} {f.stance}" for f in findings)
        summary = (f"{name} ({data['ticker']}) closed at {data['indicators']['last_close']:,.2f} "
                   f"on {data['indicators']['last_date']}. Specialist views: {views}. "
                   f"Weighted outlook: {outlook} (score {score:+.2f}).")
        return {
            "summary": summary,
            "bullish_points": [p for f in findings for p in f.bullish_points[:3]],
            "bearish_points": [p for f in findings for p in f.bearish_points[:3]],
            "key_risks": self._risks(data),
            "outlook": outlook,
            "confidence": confidence,
            "outlook_rationale": (f"Weighted vote (technical 40%, fundamental 40%, news 20%) = "
                                  f"{score:+.2f}. The most common stance is held by {agree} of "
                                  f"{len(findings)} agents, so confidence is {confidence}."),
            "source": "rules",
        }

    @staticmethod
    def _risks(data: dict) -> list[str]:
        ind, s = data["indicators"], data["fundamentals"]["stats"]
        risks = []
        if ind["volatility_1y"] > 0.35:
            risks.append(f"Elevated volatility ({ind['volatility_1y']:.0%} annualised) means large price swings.")
        if ind["max_drawdown_1y"] < -0.25:
            risks.append(f"Suffered a {ind['max_drawdown_1y']:.0%} drawdown in the last year.")
        if ind["rsi14"] >= 70:
            risks.append("Overbought momentum (RSI >= 70) raises short-term pullback risk.")
        pe = s.get("forwardPE") or s.get("trailingPE")
        if pe and pe > 35:
            risks.append(f"Valuation risk: P/E {pe:.1f} leaves little room for disappointment.")
        if s.get("debtToEquity", 0) > 150:
            risks.append(f"Leverage risk: debt/equity {s['debtToEquity']:.0f}%.")
        if s.get("beta", 0) > 1.3:
            risks.append(f"High beta ({s['beta']:.2f}): amplified sensitivity to market moves.")
        if not data["news"]:
            risks.append("No recent headlines were available, so news-driven risk is unassessed.")
        risks.append("Broad market, interest-rate and macro shocks can override stock-specific signals.")
        risks.append("Yahoo Finance data may be delayed, incomplete or revised.")
        return risks


SPECIALISTS = [TechnicalAnalyst(), FundamentalAnalyst(), NewsAnalyst()]
