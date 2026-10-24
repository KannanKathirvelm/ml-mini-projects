"""Train an RNN and an LSTM on a stock's closing prices and compare them.

    python train.py --ticker AAPL
    python train.py --ticker RELIANCE.NS --epochs 80

Both models are also compared with a naive baseline ("tomorrow = today"),
which is surprisingly hard to beat for daily stock prices.
"""
import argparse
import copy
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from data import load_prices, split_data
from model import PriceRNN, predict_prices

MODEL_DIR = Path(__file__).parent / "models"
CELLS = ["rnn", "lstm"]


def safe_name(ticker):
    return ticker.replace("^", "_")


def metrics(actual, pred, prev):
    """Price-space errors plus how often the predicted up/down move was right."""
    err = pred - actual
    moved = pred != prev  # the naive baseline never predicts a move
    return {
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "mae": float(np.mean(np.abs(err))),
        "mape_pct": float(np.mean(np.abs(err / actual)) * 100),
        "direction_acc_pct": (float(np.mean(np.sign(pred - prev) == np.sign(actual - prev)) * 100)
                              if moved.any() else None),
    }


def train_one(cell, splits, epochs, lr, batch, patience, device, log=print):
    torch.manual_seed(42)
    model = PriceRNN(cell).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    X_tr, y_tr, *_ = splits["train"]
    X_va, y_va, *_ = splits["val"]
    loader = DataLoader(TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(y_tr)),
                        batch_size=batch, shuffle=True)
    X_va_t, y_va_t = torch.from_numpy(X_va).to(device), torch.from_numpy(y_va).to(device)

    best_loss, best_state, bad, history = float("inf"), None, 0, []
    for epoch in range(1, epochs + 1):
        model.train()
        total = 0.0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)  # keeps the plain RNN stable
            opt.step()
            total += loss.item() * len(xb)
        model.eval()
        with torch.no_grad():
            val_loss = loss_fn(model(X_va_t), y_va_t).item()
        history.append({"epoch": epoch, "train_loss": total / len(X_tr), "val_loss": val_loss})
        if val_loss < best_loss:
            best_loss, best_state, bad = val_loss, copy.deepcopy(model.state_dict()), 0
        else:
            bad += 1
        if epoch % 10 == 0 or epoch == 1:
            log(f"  [{cell}] epoch {epoch:3d}  train {total / len(X_tr):.4f}  val {val_loss:.4f}")
        if bad >= patience:
            log(f"  [{cell}] early stop at epoch {epoch} (best val {best_loss:.4f})")
            break
    model.load_state_dict(best_state)
    return model.cpu(), history


def run(ticker="AAPL", start="2015-01-01", window=60, epochs=60, lr=1e-3, batch=64,
        patience=10, device="cpu", refresh=False, log=print):
    """Train both models, save weights + meta JSON + plot, return the meta dict."""
    prices = load_prices(ticker, start, refresh)
    splits = split_data(prices, window)
    log(f"{ticker}: {len(prices)} days {prices.index[0].date()} -> {prices.index[-1].date()}, "
        f"train/val/test windows = {len(splits['train'][0])}/{len(splits['val'][0])}/{len(splits['test'][0])}")

    X_te, _, test_dates, prev = splits["test"]
    actual = prices.loc[test_dates].values
    results = {"naive_baseline": metrics(actual, prev, prev)}
    predictions = {"actual": actual.tolist(), "naive_baseline": prev.tolist()}
    histories = {}
    MODEL_DIR.mkdir(exist_ok=True)

    for cell in CELLS:
        log(f"\nTraining {cell.upper()}...")
        model, histories[cell] = train_one(cell, splits, epochs, lr, batch, patience, device, log)
        pred = predict_prices(model, X_te, prev, splits["scale"])
        results[cell] = metrics(actual, pred, prev)
        predictions[cell] = pred.tolist()
        torch.save(model.state_dict(), MODEL_DIR / f"{safe_name(ticker)}_{cell}.pt")

    log(f"\nTest results ({len(actual)} days, {test_dates[0].date()} -> {test_dates[-1].date()}):")
    log(f"  {'model':16s} {'RMSE':>9s} {'MAE':>9s} {'MAPE%':>7s} {'Dir%':>6s}")
    for name, m in results.items():
        d = "  n/a" if m["direction_acc_pct"] is None else f"{m['direction_acc_pct']:6.1f}"
        log(f"  {name:16s} {m['rmse']:9.3f} {m['mae']:9.3f} {m['mape_pct']:7.2f} {d}")

    meta = {
        "ticker": ticker, "window": window, "scale": splits["scale"],
        "last_date": str(prices.index[-1].date()), "test_dates": [str(d.date()) for d in test_dates],
        "results": results, "predictions": predictions, "history": histories,
    }
    (MODEL_DIR / f"{safe_name(ticker)}_meta.json").write_text(json.dumps(meta))

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(test_dates, actual, label="Actual", color="black", lw=1.6)
    for cell in CELLS:
        ax.plot(test_dates, predictions[cell], label=f"{cell.upper()} (RMSE {results[cell]['rmse']:.2f})", alpha=0.8)
    ax.set_title(f"{ticker}: next-day close on unseen test period")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(MODEL_DIR / f"{safe_name(ticker)}_test_plot.png", dpi=120)
    plt.close(fig)
    log(f"\nSaved models, metrics and plot to {MODEL_DIR}")
    return meta


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", default="AAPL")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--window", type=int, default=60, help="days of history per prediction")
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--patience", type=int, default=10)
    p.add_argument("--device", default="cpu", help="cpu or mps (Apple GPU); cpu is fast for models this small")
    p.add_argument("--refresh", action="store_true", help="re-download prices")
    a = p.parse_args()
    run(a.ticker, a.start, a.window, a.epochs, a.lr, a.batch, a.patience, a.device, a.refresh)


if __name__ == "__main__":
    main()
