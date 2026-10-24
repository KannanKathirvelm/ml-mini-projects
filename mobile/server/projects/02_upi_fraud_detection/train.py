"""Train and compare UPI fraud classifiers, then save the best one.

Models are ranked by average precision (PR-AUC) because fraud is rare, and the
decision threshold is tuned for F1. The test report also breaks recall down by
scam type, so you can see which pattern the model struggles with.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, classification_report,
                             confusion_matrix, precision_recall_curve, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from features import CATEGORICAL, FEATURES, NUMERIC, build_features
from generate_data import generate

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "upi_transactions.csv"
MODEL_DIR = ROOT / "models"


def build_models():
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ("num", StandardScaler(), NUMERIC),
    ])
    return {
        "logistic_regression": Pipeline([
            ("pre", pre),
            ("clf", LogisticRegression(class_weight="balanced", max_iter=2000)),
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
    return float(thresholds[int(np.argmax(f1[:-1]))])


def main():
    if not DATA.exists():
        print("No dataset found, generating synthetic data...")
        DATA.parent.mkdir(exist_ok=True)
        generate().to_csv(DATA, index=False)

    df = build_features(pd.read_csv(DATA))
    X, y = df[FEATURES], df["is_fraud"]
    print(f"Loaded {len(df):,} UPI transactions, fraud rate {y.mean():.2%}")

    idx_train, idx_tmp = train_test_split(df.index, test_size=0.4, stratify=y, random_state=42)
    idx_val, idx_test = train_test_split(idx_tmp, test_size=0.5, stratify=y[idx_tmp], random_state=42)

    results = {}
    for name, model in build_models().items():
        model.fit(X.loc[idx_train], y[idx_train])
        proba = model.predict_proba(X.loc[idx_val])[:, 1]
        results[name] = (model, average_precision_score(y[idx_val], proba), roc_auc_score(y[idx_val], proba))
        print(f"  {name:20s} val AP={results[name][1]:.4f}  ROC-AUC={results[name][2]:.4f}")

    best_name = max(results, key=lambda k: results[k][1])
    best = results[best_name][0]
    threshold = best_f1_threshold(y[idx_val], best.predict_proba(X.loc[idx_val])[:, 1])
    print(f"\nBest model: {best_name} (threshold {threshold:.3f})")

    test = df.loc[idx_test].copy()
    test["proba"] = best.predict_proba(test[FEATURES])[:, 1]
    test["pred"] = (test["proba"] >= threshold).astype(int)
    report = classification_report(test.is_fraud, test.pred, target_names=["legit", "fraud"], output_dict=True)
    cm = confusion_matrix(test.is_fraud, test.pred)
    print(classification_report(test.is_fraud, test.pred, target_names=["legit", "fraud"], digits=4))
    print("Confusion matrix [[TN FP] [FN TP]]:\n", cm)

    recall_by_type = test[test.is_fraud == 1].groupby("fraud_type")["pred"].mean().round(4).to_dict()
    print("\nRecall by scam type:", recall_by_type)

    imp = permutation_importance(best, test[FEATURES], test.is_fraud, scoring="average_precision",
                                 n_repeats=3, random_state=42, n_jobs=-1)
    importance = dict(sorted(zip(FEATURES, imp.importances_mean.round(4)), key=lambda kv: -kv[1]))
    print("Top features:", list(importance)[:6])

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump({"model": best, "threshold": threshold, "features": FEATURES},
                MODEL_DIR / "upi_fraud_model.joblib")
    metrics = {
        "best_model": best_name,
        "threshold": threshold,
        "validation": {k: {"average_precision": v[1], "roc_auc": v[2]} for k, v in results.items()},
        "test": {
            "average_precision": average_precision_score(test.is_fraud, test.proba),
            "roc_auc": roc_auc_score(test.is_fraud, test.proba),
            "fraud_precision": report["fraud"]["precision"],
            "fraud_recall": report["fraud"]["recall"],
            "fraud_f1": report["fraud"]["f1-score"],
            "confusion_matrix": cm.tolist(),
            "recall_by_fraud_type": recall_by_type,
        },
        "feature_importance": {k: float(v) for k, v in importance.items()},
    }
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nSaved model and metrics to {MODEL_DIR}")


if __name__ == "__main__":
    main()
