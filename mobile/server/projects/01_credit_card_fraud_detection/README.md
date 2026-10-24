# 💳 Credit Card Fraud Detection

Machine-learning model that flags fraudulent card transactions, with a CLI and a Streamlit dashboard.

## How it works

1. **Data** – `generate_data.py` creates 100,000 synthetic transactions (1.5% fraud). Fraud tends to be larger, happen late at night, far from home, online, and without a chip or PIN. The two groups overlap, so no single rule catches every case.
2. **Training** – `train.py` compares Logistic Regression, Random Forest and Gradient Boosting using a 60/20/20 train/validation/test split.
   - The classes are imbalanced, so models use `class_weight="balanced"`.
   - Models are ranked by **PR-AUC (average precision)**, not accuracy. Predicting "legit" every time already scores 98.5% accuracy.
   - The decision threshold is set to the one that maximizes F1 on the validation set.
3. **Prediction** – `predict.py` (CLI) and `app.py` (dashboard) load the saved model.

## Results (test set, 20,000 transactions)

| Metric | Value |
|---|---|
| Best model | Random Forest |
| Fraud precision | 89.6% |
| Fraud recall | 92.0% |
| PR-AUC | ~0.96 |
| ROC-AUC | ~0.997 |

## Run it

```bash
pip install -r requirements.txt
python generate_data.py      # creates data/transactions.csv
python train.py              # trains, compares, saves models/fraud_model.joblib
streamlit run app.py         # opens the dashboard
```

CLI examples:

```bash
python predict.py --amount 950 --hour 2 --distance-home 400 --category electronics --online 1 --chip 0 --pin 0
python predict.py --csv data/transactions.csv   # writes transactions_scored.csv
```

## Project structure

```
generate_data.py   synthetic dataset generator
train.py           model comparison, threshold tuning, saves model + metrics
predict.py         scoring helpers + CLI
app.py             Streamlit UI (single check, batch CSV, model metrics)
data/              generated dataset
models/            fraud_model.joblib, metrics.json
```

## Using real data

To use the [Kaggle credit card fraud dataset](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud), change `CATEGORICAL`, `NUMERIC` and `TARGET` in `train.py` to `[]`, `V1..V28 + Amount` and `Class`.
