# 📲 UPI Fraud Detection

Machine-learning model that flags fraudulent UPI payments and **explains why**, with a CLI and a Streamlit dashboard.

## Scam patterns covered

| Pattern | What happens | Main signals |
|---|---|---|
| **Fake refund / collect request** | Scammer sends a "refund" or "cashback" collect request; approving it with your PIN sends money out | `collect_request` mode, scam words in remark, support-style VPA, new young payee |
| **Account takeover (SIM swap)** | Attacker gets the victim's SIM or UPI on a new device and drains the account | SIM/device changed in 48h, failed PINs, night time, many quick transfers, high amount |
| **Fake merchant QR** | QR code points to a fraudster's account instead of the shop's | `qr_scan` to a recently created payee that already has fraud reports |

The data is synthetic and built to be realistic. Phone-number VPAs (`98xxxxxxxx@paytm`) are common for real users. Scammers often use normal-looking mule accounts. Some legitimate remarks contain words like "refund". So no single rule is enough.

## How it works

1. **`generate_data.py`** creates 100,000 transactions (2% fraud, split across the three patterns).
2. **`features.py`** turns the raw VPA and remark text into features: scam keywords, support-style handles, number-only VPAs, night time, log amount. It also turns the same features into plain-English **risk signals**.
3. **`train.py`** compares Logistic Regression, Random Forest and Gradient Boosting, ranks them by PR-AUC, tunes the threshold for F1, and reports recall per scam type plus feature importance.
4. **`predict.py` / `app.py`** score transactions as **LOW / MEDIUM / HIGH** risk and list the reasons.

## Results (test set, 20,000 transactions)

| Metric | Value |
|---|---|
| Best model | Gradient Boosting |
| Fraud precision | 91.6% |
| Fraud recall | 95.0% |
| PR-AUC | ~0.98 |
| Recall: account takeover / collect scam / fake QR | 100% / 94.6% / 89.7% |

## Run it

```bash
pip install -r requirements.txt
python generate_data.py      # creates data/upi_transactions.csv
python train.py              # trains, compares, saves models/upi_fraud_model.joblib
streamlit run app.py         # dashboard with 4 ready-made examples
```

CLI examples:

```bash
python predict.py --vpa refund.helpdesk42@ybl --amount 4999 --mode collect_request --remark "refund processing" --new-payee 1 --payee-age 3
python predict.py --csv data/upi_transactions.csv   # writes upi_transactions_scored.csv
```

Sample output:

```
Fraud probability: 99.9%  ->  HIGH risk
  - Collect request: approving it sends money OUT. Real refunds never need your PIN
  - Remark 'refund processing' uses common scam words
  - Payee VPA 'refund.helpdesk42@ybl' imitates an official/support handle
  - First payment to an account only 3 days old
```

## Project structure

```
generate_data.py   synthetic UPI dataset with 3 scam patterns
features.py        feature engineering + human-readable risk signals
train.py           model comparison, threshold tuning, per-scam recall, importance
predict.py         scoring helpers + CLI
app.py             Streamlit UI (single check with examples, batch CSV, model metrics)
data/  models/     generated dataset, saved model + metrics.json
```
