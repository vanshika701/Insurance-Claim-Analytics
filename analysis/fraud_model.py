"""
A small supervised fraud-scoring model — the "what would you do next" follow-up to the
SQL/EDA work.

Goal: beat the one-line heuristic from the analysis ("investigate every Major Damage claim",
~61% precision / ~68% recall) with a model that uses incident features, and see how much
lift the extra features actually buy.

Approach (deliberately simple, fully explainable):
  * pull the 4 tables from MySQL, join to one row per claim
  * features = incident characteristics + a few policy/vehicle attributes
    (NO total_claim_amount-derived leakage beyond the raw amount, which the analysis
     showed carries little signal anyway)
  * stratified train/test split
  * two models: L2 logistic regression and a depth-limited decision tree
  * evaluate both against the "all Major Damage" baseline on the held-out test set
  * report ROC-AUC, precision/recall at the default threshold, and the top coefficients /
    feature importances
  * save analysis/../charts/08_model_vs_baseline.png

Run:  python analysis/fraud_model.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_auc_score, precision_score, recall_score, f1_score,
    precision_recall_curve, confusion_matrix,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from db.connection import get_engine

RANDOM_STATE = 42
CHARTS_DIR = PROJECT_ROOT / "charts"

CATEGORICAL = [
    "incident_severity", "incident_type", "collision_type", "authorities_contacted",
    "property_damage", "police_report_available", "insured_sex", "insured_education_level",
    "insured_relationship", "policy_state", "auto_make",
]
NUMERIC = [
    "number_of_vehicles_involved", "bodily_injuries", "witnesses",
    "incident_hour_of_the_day", "months_as_customer", "age",
    "policy_annual_premium", "total_claim_amount",
]


def load_claims() -> pd.DataFrame:
    sql = """
        SELECT
            i.incident_severity, i.incident_type, i.collision_type, i.authorities_contacted,
            i.property_damage, i.police_report_available, i.number_of_vehicles_involved,
            i.bodily_injuries, i.witnesses, i.incident_hour_of_the_day,
            p.insured_sex, p.insured_education_level, p.insured_relationship, p.policy_state,
            p.months_as_customer, p.age, p.policy_annual_premium,
            v.auto_make,
            c.total_claim_amount,
            c.fraud_reported
        FROM claims c
        JOIN incidents i ON i.incident_id   = c.incident_id
        JOIN policies  p ON p.policy_number  = c.policy_number
        JOIN vehicles  v ON v.policy_number  = c.policy_number
    """
    df = pd.read_sql(sql, get_engine())
    df["y"] = (df.fraud_reported == "Y").astype(int)
    return df


def build_pipeline(model) -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=15), CATEGORICAL),
        ("num", StandardScaler(), NUMERIC),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def evaluate(name: str, y_true, y_prob, threshold: float = 0.5) -> dict:
    y_pred = (y_prob >= threshold).astype(int)
    row = {
        "model": name,
        "roc_auc": roc_auc_score(y_true, y_prob),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "flagged": int(y_pred.sum()),
    }
    return row


def main() -> None:
    df = load_claims()
    X, y = df[CATEGORICAL + NUMERIC], df["y"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.30, stratify=y, random_state=RANDOM_STATE
    )
    print(f"train {len(X_train)}  test {len(X_test)}  fraud rate "
          f"{y_train.mean():.1%} / {y_test.mean():.1%}")

    results = []

    # --- baseline: flag every "Major Damage" claim -------------------------------
    base_pred = (X_test.incident_severity == "Major Damage").astype(int)
    results.append({
        "model": "baseline: all Major Damage",
        "roc_auc": roc_auc_score(y_test, base_pred),
        "precision": precision_score(y_test, base_pred),
        "recall": recall_score(y_test, base_pred),
        "f1": f1_score(y_test, base_pred),
        "flagged": int(base_pred.sum()),
    })

    # --- logistic regression ----------------------------------------------------
    logit = build_pipeline(LogisticRegression(max_iter=1000, C=0.5,
                                              class_weight="balanced",
                                              random_state=RANDOM_STATE))
    logit.fit(X_train, y_train)
    logit_prob = logit.predict_proba(X_test)[:, 1]
    results.append(evaluate("logistic regression", y_test, logit_prob))

    # --- decision tree --------------------------------------------------------
    tree = build_pipeline(DecisionTreeClassifier(max_depth=4, min_samples_leaf=25,
                                                 class_weight="balanced",
                                                 random_state=RANDOM_STATE))
    tree.fit(X_train, y_train)
    tree_prob = tree.predict_proba(X_test)[:, 1]
    results.append(evaluate("decision tree (depth 4)", y_test, tree_prob))

    res_df = pd.DataFrame(results).set_index("model").round(3)
    print("\n=== Held-out test performance ===")
    print(res_df.to_string())

    # --- what the logistic model learned --------------------------------------
    ohe = logit.named_steps["pre"].named_transformers_["cat"]
    feat_names = list(ohe.get_feature_names_out(CATEGORICAL)) + NUMERIC
    coefs = pd.Series(logit.named_steps["model"].coef_[0], index=feat_names)
    print("\nTop fraud-increasing features (logistic coefficients):")
    print(coefs.sort_values(ascending=False).head(8).round(3).to_string())
    print("\nTop fraud-decreasing features:")
    print(coefs.sort_values().head(5).round(3).to_string())

    # --- chart: PR curve + confusion matrices ---------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    for name, prob, color in [("logistic", logit_prob, "#2a78d6"),
                              ("decision tree", tree_prob, "#1baf7a")]:
        prec, rec, _ = precision_recall_curve(y_test, prob)
        axes[0].plot(rec, prec, label=name, color=color, lw=2)
    axes[0].scatter(results[0]["recall"], results[0]["precision"],
                    color="#d03b3b", zorder=5, label="baseline (all Major Damage)")
    axes[0].axhline(y_test.mean(), ls="--", color="#898781", lw=1)
    axes[0].set_xlabel("recall"); axes[0].set_ylabel("precision")
    axes[0].set_title("Precision–recall: model vs one-line rule")
    axes[0].legend(frameon=False, fontsize=9); axes[0].set_ylim(0, 1)

    cm = confusion_matrix(y_test, (logit_prob >= 0.5).astype(int))
    axes[1].imshow(cm, cmap="Blues")
    for (r, c), v in np.ndenumerate(cm):
        axes[1].text(c, r, str(v), ha="center", va="center",
                     color="white" if v > cm.max() / 2 else "#0b0b0b", fontsize=13)
    axes[1].set_xticks([0, 1], ["pred legit", "pred fraud"])
    axes[1].set_yticks([0, 1], ["true legit", "true fraud"])
    axes[1].set_title("Logistic regression — confusion matrix (test)")
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "08_model_vs_baseline.png", dpi=150, bbox_inches="tight")
    print(f"\nsaved {CHARTS_DIR / '08_model_vs_baseline.png'}")

    # --- takeaway -----------------------------------------------------------
    best = res_df.drop(index="baseline: all Major Damage").roc_auc.idxmax()
    print(f"\nTakeaway: {best} reaches ROC-AUC {res_df.loc[best, 'roc_auc']:.2f}. "
          "The lift over the one-line severity rule is modest — consistent with the EDA "
          "finding that severity carries most of the signal and the other features add a little.")


if __name__ == "__main__":
    main()
