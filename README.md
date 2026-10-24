# ML & AI Mini Projects

Seven small, independent projects covering fraud detection, deep learning, AI agents, web apps and computer vision. Each folder is a complete project with its own README, a command-line tool and a Streamlit dashboard.

| # | Project | What it does | Key result | Stack |
|---|---|---|---|---|
| 1 | [Credit card fraud detection](01_credit_card_fraud_detection/README.md) | Flags fraudulent card transactions | 92.0% fraud recall, 89.6% precision (Random Forest) | scikit-learn |
| 2 | [UPI fraud detection](02_upi_fraud_detection/README.md) | Rates UPI payments LOW / MEDIUM / HIGH risk and explains why | 95.0% recall, 91.6% precision across 3 scam types | scikit-learn |
| 3 | [Stock price prediction (RNN vs LSTM)](03_stock_price_prediction_lstm_rnn/README.md) | Next-day price prediction and N-day forecast for any Yahoo Finance ticker | ~1.1% error on AAPL, but no better than "tomorrow = today"; direction ~50% | PyTorch, yfinance |
| 4 | [Financial AI agents](04_financial_ai_agents/README.md) | Technical, fundamental and news agents plus a lead agent write a market-insight report | Works offline (rule-based); uses Claude when `ANTHROPIC_API_KEY` is set | Anthropic SDK, yfinance |
| 5 | [Price comparison app](05_price_comparison_app/README.md) | Compares one product across stores, picks the best total price, tracks history and alerts | 5 stores (2 public demo APIs + 3 simulated), SQLite price history | requests, SQLite |
| 6 | [Face detection](06_face_detection/README.md) | Haar cascade vs YuNet on images, video and webcam, with face blurring | YuNet: 100% precision and recall on 76 hand-checked faces, ~5x faster than Haar | OpenCV 4 |
| 7 | [Object detection](07_object_detection/README.md) | YOLO11 detection of 80 object classes, with tracking and line-crossing counts | ~51 FPS on Apple GPU (MPS); mAP50 0.854 on coco8 sanity check | Ultralytics YOLO |

> The data in projects 1, 2 and 5 is synthetic or demo data. Projects 3 and 4 are educational, not financial advice.

## Setup

Projects 1 and 2 use your main Python (`pip install -r requirements.txt`). Projects 3–7 each have their own virtual environment in `.venv`, so heavy dependencies like PyTorch don't clash.

To recreate a missing `.venv`, run these inside that project's folder:

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

The parent folder name ends with a space (`My new project `), so keep paths in quotes.

## How to run each project

### 1. Credit card fraud detection

```bash
cd "/Users/kannan-moni/Desktop/My new project /01_credit_card_fraud_detection"
```

```bash
python3 train.py
```

```bash
streamlit run app.py
```

### 2. UPI fraud detection

```bash
cd "/Users/kannan-moni/Desktop/My new project /02_upi_fraud_detection"
```

```bash
python3 train.py
```

```bash
streamlit run app.py
```

### 3. Stock price prediction (RNN vs LSTM)

```bash
cd "/Users/kannan-moni/Desktop/My new project /03_stock_price_prediction_lstm_rnn"
```

```bash
.venv/bin/python train.py --ticker AAPL
```

```bash
.venv/bin/streamlit run app.py
```

### 4. Financial AI agents

```bash
cd "/Users/kannan-moni/Desktop/My new project /04_financial_ai_agents"
```

```bash
.venv/bin/python report.py --ticker AAPL
```

```bash
.venv/bin/streamlit run app.py
```

To use Claude instead of the rule-based agents, set your key first (`export ANTHROPIC_API_KEY=...`).

### 5. Price comparison app

```bash
cd "/Users/kannan-moni/Desktop/My new project /05_price_comparison_app"
```

```bash
.venv/bin/python compare.py "iphone"
```

```bash
.venv/bin/streamlit run app.py
```

### 6. Face detection

```bash
cd "/Users/kannan-moni/Desktop/My new project /06_face_detection"
```

```bash
.venv/bin/python detect.py --image samples/addams-family.png --detector dnn --out outputs/addams.jpg
```

```bash
.venv/bin/streamlit run app.py
```

### 7. Object detection

```bash
cd "/Users/kannan-moni/Desktop/My new project /07_object_detection"
```

```bash
.venv/bin/python detect.py --source samples/bus.jpg --save
```

```bash
.venv/bin/streamlit run app.py
```

## Not yet tested

- Webcam modes in projects 6 and 7 (no camera was available while building).
- Real Claude API calls in project 4. LLM mode was only tested against a mock.
