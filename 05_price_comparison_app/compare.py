"""CLI: compare prices for a product across all stores.

    python compare.py "iphone"
    python compare.py "laptop" --top 3
    python compare.py "perfume" --track "Dior J'adore" --target 9000
    python compare.py --seed-history
"""
import argparse
import sys

import db
from formatting import inr
from history import seed_history
from search import search_all


def print_group(group, index: int):
    best = group.best
    print(f"\n[{index}] {group.title}  ({len(group.stores)} store(s))")
    print(f"    {'store':<13} {'price':>11} {'ship':>7} {'total':>11} {'days':>4} {'rating':>6}  stock")
    for o in sorted(group.offers, key=lambda o: o.total_inr):
        mark = " <- best" if o is best else ""
        print(f"    {o.store:<13} {inr(o.price_inr):>11} {inr(o.shipping_inr):>7} "
              f"{inr(o.total_inr):>11} {o.delivery_days if o.delivery_days is not None else '-':>4} "
              f"{o.rating if o.rating is not None else '-':>6}  "
              f"{'yes' if o.in_stock else 'NO'}{mark}")
    if len(group.offers) > 1:
        print(f"    Best deal: {best.store} at {inr(best.total_inr)}; "
              f"saves {inr(group.savings)} vs {group.worst.store}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Compare product prices across stores.")
    p.add_argument("query", nargs="?", help="product to search for")
    p.add_argument("--top", type=int, default=5, help="product groups to show (default 5)")
    p.add_argument("--track", metavar="TITLE", help="track the group whose title contains TITLE")
    p.add_argument("--target", type=float, help="target total price in INR for --track")
    p.add_argument("--seed-history", action="store_true",
                   help="backfill 30 days of simulated-store price history")
    args = p.parse_args(argv)

    conn = db.connect()
    if args.seed_history:
        rows = seed_history(30, conn)
        print(f"Seeded {rows} simulated history rows into data/prices.db")
        if not args.query:
            return 0
    if not args.query:
        p.error("a query is required (or use --seed-history)")

    res = search_all(args.query)
    db.save_offers(conn, res.offers, args.query)
    print(f'Search "{args.query}": {len(res.offers)} offers from '
          f"{len(res.stores_ok)} store(s), {len(res.groups)} product(s)")
    for store, err in res.errors.items():
        print(f"  ! {store} unavailable, skipped ({err})")
    for i, g in enumerate(res.groups[: args.top], 1):
        print_group(g, i)

    if args.track:
        if args.target is None:
            p.error("--track needs --target")
        match = next((g for g in res.groups if args.track.lower() in g.title.lower()), None)
        if not match:
            print(f'\nNo product matching "{args.track}" to track.')
            return 1
        db.track(conn, match, args.query, args.target)
        print(f'\nTracking "{match.title}" with target {inr(args.target)} '
              f"(current best {inr(match.best.total_inr)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
