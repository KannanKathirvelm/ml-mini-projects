"""Train the pooled "India universal" RNN + LSTM on many NSE stocks at once.

    python train_universal.py                 # stocks in india_universe.txt, cached prices
    python train_universal.py --refresh       # re-download prices first (nightly job)
    python train_universal.py --epochs 5 --limit 10   # quick smoke run

Every stock's windows are scaled by its own volatility and split by the SAME calendar dates
(validation = the year before the last year, test = the last year), then pooled. The stocks
after `[holdout]` in india_universe.txt are never trained on; they measure how well the model
does on stocks it has never seen. Both are compared with the naive "tomorrow = today" baseline.

Writes models/universal_{rnn,lstm}.pt and models/universal_meta.json (or into --out).
"""
from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

import universal as U
from data import load_prices
from model import PriceRNN

CELLS = ["rnn", "lstm"]
MIN_DAYS = 400


def torch_predict_fn(model: nn.Module):
    model.eval()

    @torch.no_grad()
    def fn(X: np.ndarray) -> np.ndarray:
        out = [model(torch.from_numpy(np.ascontiguousarray(X[i:i + 4096]))).numpy()
               for i in range(0, len(X), 4096)]
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)
    return fn


def load_universe(symbols, start, refresh, log):
    out = {}
    for s in symbols:
        try:
            p = load_prices(s, start, refresh=refresh)
        except Exception as exc:
            log(f"  skip {s}: {exc}")
            continue
        p = p[p > 0].dropna()
        if len(p) < MIN_DAYS:
            log(f"  skip {s}: only {len(p)} days")
            continue
        out[s] = p
    return out


def train_cell(cell, Xtr, ytr, Xva, yva, epochs, lr, batch, patience, log):
    torch.manual_seed(42)
    rng = np.random.default_rng(42)
    model = PriceRNN(cell)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    Xtr_t, ytr_t = torch.from_numpy(Xtr), torch.from_numpy(ytr)
    Xva_t, yva_t = torch.from_numpy(Xva), torch.from_numpy(yva)
    best, best_state, bad, hist = float("inf"), None, 0, []
    for epoch in range(1, epochs + 1):
        t0 = time.time()
        model.train()
        perm = torch.from_numpy(rng.permutation(len(Xtr)))
        total = 0.0
        for i in range(0, len(perm), batch):
            idx = perm[i:i + batch]
            xb, yb = Xtr_t[idx], ytr_t[idx]
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total += loss.item() * len(idx)
        model.eval()
        with torch.no_grad():
            val = sum(loss_fn(model(Xva_t[j:j + 8192]), yva_t[j:j + 8192]).item()
                      * len(Xva_t[j:j + 8192]) for j in range(0, len(Xva_t), 8192)) / len(Xva_t)
        hist.append({"epoch": epoch, "train_loss": total / len(Xtr), "val_loss": val})
        log(f"  [{cell}] epoch {epoch:2d}  train {total / len(Xtr):.4f}  val {val:.4f}  ({time.time() - t0:.0f}s)")
        if val < best - 1e-5:
            best, best_state, bad = val, copy.deepcopy(model.state_dict()), 0
        else:
            bad += 1
            if bad >= patience:
                log(f"  [{cell}] early stop (best val {best:.4f})")
                break
    model.load_state_dict(best_state)
    return model.eval(), hist


def evaluate(models, data: dict, kind: str) -> tuple[dict, dict]:
    """Pooled + per-stock metrics on the 'test' part of each stock."""
    fns = {c: torch_predict_fn(m) for c, m in models.items()}
    rows, per_stock = [], {}
    for sym, (parts, scale) in data.items():
        X, _, dates, prev, actual = parts["test"]
        if len(X) == 0:
            continue
        row = {"symbol": sym, "actual": actual, "prev": prev}
        for c, fn in fns.items():
            row[c] = U.predict_prices(fn, X, prev, scale)
        rows.append(row)
        per_stock[sym] = {"naive_baseline": U.metrics(actual, prev, prev),
                          **{c: U.metrics(actual, row[c], prev) for c in fns},
                          "days": int(len(X)), "scale": scale}
    pooled = U.pooled_metrics(rows)
    pooled["kind"] = kind
    return pooled, per_stock


def run(universe_file=U.UNIVERSE_FILE, start="2015-01-01", epochs=25, lr=1e-3, batch=256,
        patience=4, refresh=False, out_dir: Path = U.MODEL_DIR, limit=None, log=print) -> dict:
    t_start = time.time()
    train_syms, hold_syms = U.read_universe(universe_file)
    if limit:
        train_syms, hold_syms = train_syms[:limit], hold_syms[:max(2, limit // 5)]
    log(f"Loading {len(train_syms)} training + {len(hold_syms)} held-out stocks...")
    train_px = load_universe(train_syms, start, refresh, log)
    hold_px = load_universe(hold_syms, start, refresh, log)
    if len(train_px) < 2:
        raise RuntimeError("fewer than 2 training stocks have data")
    last_date = max(p.index[-1] for p in train_px.values())
    val_start, test_start = U.split_dates(last_date)
    log(f"Split: train < {val_start.date()} <= val < {test_start.date()} <= test <= {last_date.date()}")

    tr_data = {s: U.stock_windows(p, val_start, test_start) for s, p in train_px.items()}
    ho_data = {}
    for s, p in hold_px.items():
        logp = np.log(p.values)
        ho_data[s] = U.stock_windows(p, val_start, test_start,
                                     scale=U.stock_scale(logp[p.index < test_start]))

    def stack(part):
        X = np.concatenate([d[0][part][0] for d in tr_data.values()])
        y = np.concatenate([d[0][part][1] for d in tr_data.values()])
        return X, y
    Xtr, ytr = stack("train")
    Xva, yva = stack("val")
    log(f"Windows: train {len(Xtr):,}  val {len(Xva):,}  "
        f"test {sum(len(d[0]['test'][0]) for d in tr_data.values()):,}  "
        f"held-out stocks test {sum(len(d[0]['test'][0]) for d in ho_data.values()):,}")

    models, hists = {}, {}
    for cell in CELLS:
        log(f"\nTraining universal {cell.upper()}...")
        t0 = time.time()
        models[cell], hists[cell] = train_cell(cell, Xtr, ytr, Xva, yva, epochs, lr, batch, patience, log)
        log(f"  [{cell}] {time.time() - t0:.0f}s")

    pooled_time, per_time = evaluate(models, tr_data, "held-out time (training stocks, test year)")
    pooled_hold, per_hold = evaluate(models, ho_data, "held-out stocks (never trained on, test year)")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for cell, m in models.items():
        torch.save(m.state_dict(), out_dir / f"universal_{cell}.pt")
    meta = {
        "kind": "universal", "window": U.WINDOW, "scale_lookback": U.SCALE_LOOKBACK,
        "cells": CELLS, "start": start,
        "train_symbols": sorted(train_px), "holdout_symbols": sorted(hold_px),
        "skipped": sorted(set(train_syms + hold_syms) - set(train_px) - set(hold_px)),
        "last_date": str(last_date.date()), "val_start": str(val_start.date()),
        "test_start": str(test_start.date()),
        "n_windows": {"train": int(len(Xtr)), "val": int(len(Xva))},
        "eval": {"held_out_time": pooled_time, "held_out_stocks": pooled_hold},
        "per_stock": {"held_out_time": per_time, "held_out_stocks": per_hold},
        "history": hists,
        "trained_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "train_seconds": round(time.time() - t_start, 1),
    }
    (out_dir / "universal_meta.json").write_text(json.dumps(meta, indent=1))
    log("\n" + summary_table(meta))
    log(f"\nSaved universal models to {out_dir} in {meta['train_seconds']:.0f}s")
    return meta


def summary_table(meta: dict) -> str:
    lines = []
    for key, ev in meta["eval"].items():
        lines.append(f"{ev['kind']}: {ev['n_stocks']} stocks, {ev['n_days']:,} stock-days, "
                     f"up days {ev['up_days_pct']:.1f}%")
        lines.append(f"  {'model':15s} {'MAPE%':>7s} {'RMSE ret%':>10s} {'Dir%':>6s} {'RMSE/naive':>11s} {'beat naive':>11s}")
        for m in ["naive_baseline", *meta["cells"]]:
            e = ev[m]
            d = "   n/a" if e["direction_acc_pct"] is None else f"{e['direction_acc_pct']:6.1f}"
            lines.append(f"  {m:15s} {e['mape_pct']:7.3f} {e['rmse_return_pct']:10.3f} {d} "
                         f"{e['mean_rmse_ratio_vs_naive']:11.4f} {e['stocks_beating_naive_rmse']:5d}/{ev['n_stocks']}")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default=str(U.UNIVERSE_FILE))
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--epochs", type=int, default=25)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--batch", type=int, default=256)
    p.add_argument("--patience", type=int, default=4)
    p.add_argument("--refresh", action="store_true", help="re-download prices")
    p.add_argument("--limit", type=int, default=None, help="use only the first N training stocks")
    p.add_argument("--out", default=str(U.MODEL_DIR), help="output folder")
    p.add_argument("--threads", type=int, default=None, help="torch CPU threads")
    a = p.parse_args()
    if a.threads:
        torch.set_num_threads(a.threads)
    run(Path(a.universe), a.start, a.epochs, a.lr, a.batch, a.patience, a.refresh, Path(a.out), a.limit)


if __name__ == "__main__":
    main()
