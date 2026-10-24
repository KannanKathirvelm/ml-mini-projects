"""Train and compare fraud classifiers, then save the best one.

Fraud data is heavily imbalanced, so accuracy is meaningless (predicting
"not fraud" every time gives ~98.5%). We compare models on average precision
(area under the precision-recall curve) and tune the decision threshold for F1.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, classification_report,
                             confusion_matrix, precision_recall_curve, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from generate_data import generate

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "transactions.csv"
MODEL_DIR = ROOT / "models"

CATEGORICAL = ["merchant_category"]
NUMERIC = ["amount", "hour", "distance_from_home_km", "distance_from_last_txn_km",
           "ratio_to_median_amount", "online_order", "used_chip", "used_pin",
           "txn_count_last_24h"]
TARGET = "is_fraud"


def build_models():
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ("num", StandardScaler(), NUMERIC),
    ])
    return {
        "logistic_regression": Pipeline([
            ("pre", pre),
            ("clf", LogisticRegression(class_weight="balanced", max_iter=1000)),
        ]),
        "random_forest": Pipeline([
            ("pre", pre),
            ("clf", RandomForestClassifier(n_estimators=200, min_samples_leaf=2,
                                           class_weight="balanced_subsample",
                                           n_jobs=-1, random_state=42)),
        ]),
        "gradient_boosting": Pipeline([
            ("pre", pre),
            ("clf", HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                                   class_weight="balanced", random_state=42)),
        ]),
    }


def best_f1_threshold(y_true, proba):
    precision, recall, thresholds = precision_recall_curve(y_true, proba)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-9, None)
    i = int(np.argmax(f1[:-1]))
    return float(thresholds[i])


def main():
    if not DATA.exists():
        print("No dataset found, generating synthetic data...")
        DATA.parent.mkdir(exist_ok=True)
        generate().to_csv(DATA, index=False)

    df = pd.read_csv(DATA)
    X, y = df[CATEGORICAL + NUMERIC], df[TARGET]
    print(f"Loaded {len(df):,} transactions, fraud rate {y.mean():.2%}")

    # 60/20/20 split: train / validation (pick model + threshold) / test (final report)
    X_train, X_tmp, y_train, y_tmp = train_test_split(X, y, test_size=0.4, stratify=y, random_state=42)
    X_val, X_test, y_val, y_test = train_test_split(X_tmp, y_tmp, test_size=0.5, stratify=y_tmp, random_state=42)

    results = {}
    for name, model in build_models().items():
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_val)[:, 1]
        results[name] = (model, average_precision_score(y_val, proba), roc_auc_score(y_val, proba))
        print(f"  {name:20s} val AP={results[name][1]:.4f}  ROC-AUC={results[name][2]:.4f}")

    best_name = max(results, key=lambda k: results[k][1])
    best = results[best_name][0]
    threshold = best_f1_threshold(y_val, best.predict_proba(X_val)[:, 1])
    print(f"\nBest model: {best_name} (threshold {threshold:.3f})")

    test_proba = best.predict_proba(X_test)[:, 1]
    test_pred = (test_proba >= threshold).astype(int)
    report = classification_report(y_test, test_pred, target_names=["legit", "fraud"], output_dict=True)
    cm = confusion_matrix(y_test, test_pred)
    print(classification_report(y_test, test_pred, target_names=["legit", "fraud"], digits=4))
    print("Confusion matrix [[TN FP] [FN TP]]:\n", cm)

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump({"model": best, "threshold": threshold, "features": CATEGORICAL + NUMERIC},
                MODEL_DIR / "fraud_model.joblib")
    metrics = {
        "best_model": best_name,
        "threshold": threshold,
        "validation": {k: {"average_precision": v[1], "roc_auc": v[2]} for k, v in results.items()},
        "test": {
            "average_precision": average_precision_score(y_test, test_proba),
            "roc_auc": roc_auc_score(y_test, test_proba),
            "fraud_precision": report["fraud"]["precision"],
            "fraud_recall": report["fraud"]["recall"],
            "fraud_f1": report["fraud"]["f1-score"],
            "confusion_matrix": cm.tolist(),
        },
    }
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nSaved model and metrics to {MODEL_DIR}")


if __name__ == "__main__":
    main()
