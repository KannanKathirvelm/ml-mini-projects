"""CLI: `.venv/bin/python report.py --ticker AAPL [--save] [--offline] [--model ID]`.

Prints the multi-agent market-insight report for one or more tickers.
"""
import argparse
import sys
from pathlib import Path

import llm
from data_tools import TickerNotFound
from pipeline import run_analysis, to_markdown

REPORT_DIR = Path(__file__).parent / "reports"


def main() -> int:
    ap = argparse.ArgumentParser(description="Multi-agent market insight report (not financial advice).")
    ap.add_argument("--ticker", nargs="+", required=True, help="Yahoo symbol(s), e.g. AAPL MSFT RELIANCE.NS")
    ap.add_argument("--save", action="store_true", help="also write markdown to reports/")
    ap.add_argument("--offline", action="store_true", help="force rule-based mode even if a key is set")
    ap.add_argument("--model", default=None, help=f"Claude model ID (default: {llm.MODEL})")
    args = ap.parse_args()

    use_llm = llm.llm_available() and not args.offline
    print(f"[mode] {llm.mode_label(use_llm, args.model)}", file=sys.stderr)

    failures, summary = 0, []
    for ticker in args.ticker:
        try:
            analysis = run_analysis(ticker, use_llm=use_llm, model=args.model)
        except TickerNotFound as exc:
            print(f"Error: {exc}", file=sys.stderr)
            failures += 1
            continue
        md = to_markdown(analysis)
        print(md)
        summary.append((analysis.ticker, analysis.report["outlook"], analysis.report["confidence"]))
        if args.save:
            REPORT_DIR.mkdir(exist_ok=True)
            path = REPORT_DIR / f"{analysis.ticker.replace('^', '')}_{analysis.generated[:10]}.md"
            path.write_text(md)
            print(f"[saved] {path}", file=sys.stderr)

    if len(summary) > 1:  # simple comparison table for multiple tickers
        print("| Ticker | Outlook | Confidence |\n|---|---|---|")
        for row in summary:
            print("| " + " | ".join(row) + " |")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
