"""Recurrent models: a vanilla RNN and an LSTM sharing the same architecture."""
import numpy as np
import torch
from torch import nn

from data import window_input


class PriceRNN(nn.Module):
    """Stacked recurrent layers -> last hidden state -> linear head (next-day scaled log return).

    cell="rnn"  : plain tanh RNN. Simple, but gradients fade over long windows.
    cell="lstm" : LSTM. Input/forget/output gates let it keep longer-term memory.
    """

    def __init__(self, cell: str = "lstm", hidden: int = 64, layers: int = 2, dropout: float = 0.2):
        super().__init__()
        rnn_cls = {"rnn": nn.RNN, "lstm": nn.LSTM}[cell]
        self.cell = cell
        self.rnn = rnn_cls(input_size=1, hidden_size=hidden, num_layers=layers,
                           dropout=dropout if layers > 1 else 0.0, batch_first=True)
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, 1))

    def forward(self, x):  # x: (batch, window, 1)
        out, _ = self.rnn(x)
        return self.head(out[:, -1]).squeeze(-1)


@torch.no_grad()
def predict_prices(model: nn.Module, X: np.ndarray, prev_price: np.ndarray, scale: float) -> np.ndarray:
    """Turn predicted scaled log returns back into next-day prices."""
    model.eval()
    ret = model(torch.from_numpy(X)).numpy() * scale
    return prev_price * np.exp(ret)


@torch.no_grad()
def forecast(model: nn.Module, recent_prices, steps: int, scale: float, window: int):
    """Recursive multi-day forecast: append each predicted price and predict again."""
    model.eval()
    logp = list(np.log(np.asarray(recent_prices, dtype=float))[-window:])
    preds = []
    for _ in range(steps):
        x = torch.from_numpy(window_input(np.array(logp[-window:]), scale)).reshape(1, -1, 1)
        logp.append(logp[-1] + float(model(x)) * scale)
        preds.append(float(np.exp(logp[-1])))
    return preds
