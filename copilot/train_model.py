"""Fraud-risk model: stratified 5-fold CV, logistic regression vs XGBoost vs the
"flag all Major Damage" rule baseline, evaluated on identical folds.

Also runs a one-off sensitivity check with `insured_hobbies` included, purely to document
its effect size (see copilot/features.py EXCLUDED_COLUMNS) -- that variant is never saved
as a deployable artifact.

Run:  python -m copilot.train_model
Writes:
  models/xgboost_pipeline.joblib   -- the deployed model (fit on all 1,000 claims)
  models/model_config.json         -- feature lists + chosen threshold
  results/model_metrics.json       -- CV metrics (mean ± std), threshold rationale,
                                       global SHAP importances, hobbies sensitivity check
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from .config import MODELS_DIR, RESULTS_DIR
from .features import EXCLUDED_COLUMNS, feature_columns, load_claims

RANDOM_STATE = 42
N_FOLDS = 5
METRIC_NAMES = ["precision", "recall", "f1", "pr_auc", "roc_auc"]


def build_pipeline(model, categorical: list[str], numeric: list[str]) -> Pipeline:
    # NaNs in collision_type / property_damage / police_report_available are informative
    # (e.g. a theft has no collision_type), so they're imputed as their own explicit
    # "missing" category rather than dropped. umbrella_limit's single NaN (the repaired
    # negative-value row, see ANALYSIS.md F7) is median-imputed.
    cat_pipe = Pipeline(
        [
            ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=15)),
        ]
    )
    num_pipe = Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    pre = ColumnTransformer([("cat", cat_pipe, categorical), ("num", num_pipe, numeric)])
    return Pipeline([("pre", pre), ("model", model)])


def make_logistic() -> LogisticRegression:
    return LogisticRegression(max_iter=1000, C=0.5, class_weight="balanced", random_state=RANDOM_STATE)


def make_xgboost(pos_weight: float) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=150,
        max_depth=3,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="aucpr",
        random_state=RANDOM_STATE,
        scale_pos_weight=pos_weight,
    )


def _score(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray) -> dict[str, float]:
    return {
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "pr_auc": average_precision_score(y_true, y_proba),
        "roc_auc": roc_auc_score(y_true, y_proba),
    }


def cross_validate(df: pd.DataFrame, categorical: list[str], numeric: list[str]) -> dict:
    X = df[categorical + numeric]
    y = df["y"].to_numpy()
    major = df["is_major_damage"].to_numpy()
    pos_weight = (y == 0).sum() / max((y == 1).sum(), 1)

    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    fold_metrics: dict[str, dict[str, list[float]]] = {
        name: {m: [] for m in METRIC_NAMES} for name in ("logistic_regression", "xgboost", "baseline_major_damage")
    }
    oof = {"logistic_regression": np.zeros(len(df)), "xgboost": np.zeros(len(df))}

    for train_idx, val_idx in skf.split(X, y):
        y_va, maj_va = y[val_idx], major[val_idx]
        base_scores = _score(y_va, maj_va, maj_va.astype(float))
        for k, v in base_scores.items():
            fold_metrics["baseline_major_damage"][k].append(v)

        for name, model in (
            ("logistic_regression", make_logistic()),
            ("xgboost", make_xgboost(pos_weight)),
        ):
            pipe = build_pipeline(model, categorical, numeric)
            pipe.fit(X.iloc[train_idx], y[train_idx])
            proba = pipe.predict_proba(X.iloc[val_idx])[:, 1]
            oof[name][val_idx] = proba
            pred = (proba >= 0.5).astype(int)
            for k, v in _score(y_va, pred, proba).items():
                fold_metrics[name][k].append(v)

    summary = {
        name: {m: {"mean": float(np.mean(v)), "std": float(np.std(v))} for m, v in metrics.items()}
        for name, metrics in fold_metrics.items()
    }
    return {"summary": summary, "oof_proba": oof, "y": y, "major": major}


def choose_threshold(y: np.ndarray, proba: np.ndarray, baseline_precision: float, baseline_recall: float) -> dict:
    """Sweep thresholds on out-of-fold probabilities. Report the precision achieved at (at
    least) the baseline rule's recall, and the recall achieved at (at least) the baseline
    rule's precision -- then pick whichever framing actually beats the rule, and say so
    plainly if neither does."""
    thresholds = np.linspace(0.01, 0.99, 197)
    best_for_recall_match, best_for_precision_match = None, None
    for t in thresholds:
        pred = (proba >= t).astype(int)
        if pred.sum() == 0:
            continue
        p = precision_score(y, pred, zero_division=0)
        r = recall_score(y, pred, zero_division=0)
        if r >= baseline_recall and (best_for_recall_match is None or p > best_for_recall_match["precision"]):
            best_for_recall_match = {"threshold": float(t), "precision": p, "recall": r}
        if p >= baseline_precision and (best_for_precision_match is None or r > best_for_precision_match["recall"]):
            best_for_precision_match = {"threshold": float(t), "precision": p, "recall": r}

    beats_baseline = bool(
        best_for_recall_match and best_for_recall_match["precision"] > baseline_precision
    ) or bool(best_for_precision_match and best_for_precision_match["recall"] > baseline_recall)

    chosen = best_for_recall_match or {"threshold": 0.5, "precision": None, "recall": None}
    return {
        "baseline_precision": baseline_precision,
        "baseline_recall": baseline_recall,
        "at_baseline_recall": best_for_recall_match,
        "at_baseline_precision": best_for_precision_match,
        "chosen_threshold": chosen["threshold"],
        "beats_baseline": beats_baseline,
        "rationale": (
            "Chosen threshold matches the baseline rule's recall and reports the precision "
            "achieved at that recall -- the model is only worth using operationally if it "
            "gets equal-or-better recall for less investigator effort (fewer false "
            "positives, i.e. higher precision)."
        ),
    }


def global_shap_importance(pipe: Pipeline, X: pd.DataFrame, top_n: int = 10) -> list[dict]:
    pre: ColumnTransformer = pipe.named_steps["pre"]
    model = pipe.named_steps["model"]
    X_enc = pre.transform(X)
    if hasattr(X_enc, "toarray"):
        X_enc = X_enc.toarray()
    feature_names = list(pre.get_feature_names_out())
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_enc)
    mean_abs = np.abs(shap_values).mean(axis=0)
    order = np.argsort(mean_abs)[::-1][:top_n]
    return [{"feature": feature_names[i], "mean_abs_shap": float(mean_abs[i])} for i in order]


def main() -> None:
    df = load_claims(with_hobbies=False)
    categorical, numeric = feature_columns(with_hobbies=False)
    print(f"Production feature set: {len(df)} claims, {len(categorical)} categorical + "
          f"{len(numeric)} numeric features (insured_hobbies excluded -- see features.py)")

    cv = cross_validate(df, categorical, numeric)
    summary = cv["summary"]
    for name, metrics in summary.items():
        line = "  ".join(f"{m}={v['mean']:.3f}±{v['std']:.3f}" for m, v in metrics.items())
        print(f"[{name}] {line}")

    threshold_info = choose_threshold(
        cv["y"],
        cv["oof_proba"]["xgboost"],
        baseline_precision=summary["baseline_major_damage"]["precision"]["mean"],
        baseline_recall=summary["baseline_major_damage"]["recall"]["mean"],
    )
    print("Threshold selection (XGBoost OOF probabilities):", json.dumps(threshold_info, indent=2))

    # --- fit the deployable model on ALL data ---
    X_full = df[categorical + numeric]
    y_full = df["y"].to_numpy()
    pos_weight = (y_full == 0).sum() / max((y_full == 1).sum(), 1)
    final_pipe = build_pipeline(make_xgboost(pos_weight), categorical, numeric)
    final_pipe.fit(X_full, y_full)

    shap_importance = global_shap_importance(final_pipe, X_full)
    print("Top SHAP features (global, production model):")
    for item in shap_importance:
        print(f"   {item['feature']:35s} {item['mean_abs_shap']:.4f}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_pipe, MODELS_DIR / "xgboost_pipeline.joblib")
    with open(MODELS_DIR / "model_config.json", "w") as f:
        json.dump(
            {"categorical": categorical, "numeric": numeric, "threshold": threshold_info["chosen_threshold"]},
            f,
            indent=2,
        )

    # --- sensitivity check: what happens if insured_hobbies IS included (not deployed) ---
    df_h = load_claims(with_hobbies=True)
    cats_h, nums_h = feature_columns(with_hobbies=True)
    cv_h = cross_validate(df_h, cats_h, nums_h)
    hobbies_summary = cv_h["summary"]
    print("\nSensitivity check WITH insured_hobbies (not deployed):")
    for name, metrics in hobbies_summary.items():
        line = "  ".join(f"{m}={v['mean']:.3f}±{v['std']:.3f}" for m, v in metrics.items())
        print(f"[{name}] {line}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / "model_metrics.json", "w") as f:
        json.dump(
            {
                "n_claims": len(df),
                "fraud_rate": float(df["y"].mean()),
                "cv": {"n_folds": N_FOLDS, "random_state": RANDOM_STATE},
                "cv_metrics": summary,
                "threshold_selection": threshold_info,
                "shap_global_importance_top10": shap_importance,
                "feature_set": {
                    "categorical": categorical,
                    "numeric": numeric,
                    "excluded_columns": EXCLUDED_COLUMNS,
                },
                "hobbies_sensitivity_check": {
                    "description": (
                        "Same CV, same models, with insured_hobbies added back as a "
                        "categorical feature. NOT used in the deployed model -- see "
                        "features.py EXCLUDED_COLUMNS for why."
                    ),
                    "cv_metrics": hobbies_summary,
                },
            },
            f,
            indent=2,
        )
    print(f"\nWrote {MODELS_DIR / 'xgboost_pipeline.joblib'}")
    print(f"Wrote {RESULTS_DIR / 'model_metrics.json'}")


if __name__ == "__main__":
    main()
