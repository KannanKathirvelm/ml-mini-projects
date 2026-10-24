"""Re-fetch every tracked product and report which reached its target price.

Run it by hand or from cron, e.g. daily at 9am:
    0 9 * * * cd /path/to/05_price_comparison_app && .venv/bin/python check_alerts.py
Exit code is 0 if no alert fired and 2 if at least one did (handy for scripts).
"""
import sys

from alerts import check_alerts
from formatting import inr


def main() -> int:
    results = check_alerts()
    if not results:
        print("No tracked products. Track one with:  "
              'python compare.py "iphone" --track "iPhone 13 Pro" --target 85000')
        return 0
    for r in results:
        if r.best is None:
            print(f"[ -- ] {r.title}: {r.note} (target {inr(r.target)})")
        else:
            status = "HIT " if r.hit else "wait"
            print(f"[{status}] {r.title}: best {inr(r.best)} at {r.store} "
                  f"(target {inr(r.target)})")
    hits = sum(r.hit for r in results)
    print(f"\n{hits} of {len(results)} tracked product(s) at or below target.")
    return 2 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
