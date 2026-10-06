"""Score a single claim: fraud probability, risk band, top SHAP contributors, and whether
the "flag all Major Damage" baseline rule would flag it.

Used directly here for a sanity check, and by mcp_server's score_claim tool (Phase 4).

Run:  python -m copilot.score <claim_id>
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field

import joblib
import numpy as np
import pandas as pd
import shap

from .config import MODELS_DIR
from .db import get_engine

_PIPE = None
_CONFIG = None


def _load():
    global _PIPE, _CONFIG
    if _PIPE is None:
        _PIPE = joblib.load(MODELS_DIR / "xgboost_pipeline.joblib")
        _CONFIG = json.loads((MODELS_DIR / "model_config.json").read_text())
    return _PIPE, _CONFIG


def _risk_band(prob: float) -> str:
    if prob >= 0.6:
        return "high"
    if prob >= 0.3:
        return "medium"
    return "low"


@dataclass
class ClaimScore:
    claim_id: int
    found: bool
    fraud_probability: float | None = None
    risk_band: str | None = None
    threshold: float | None = None
    would_flag: bool | None = None
    major_damage_rule_flags: bool | None = None
    incident_severity: str | None = None
    top_contributing_features: list[dict] = field(default_factory=list)
    error: str | None = None


def score_claim(claim_id: int) -> ClaimScore:
    pipe, config = _load()
    categorical, numeric, threshold = config["categorical"], config["numeric"], config["threshold"]

    row = pd.read_sql(
        f"""
        SELECT c.claim_id, i.incident_severity, i.incident_type, i.collision_type,
               i.authorities_contacted, i.property_damage, i.police_report_available,
               i.incident_state, i.number_of_vehicles_involved, i.bodily_injuries,
               i.witnesses, i.incident_hour_of_the_day,
               p.policy_state, p.policy_csl, p.policy_deductable, p.policy_annual_premium,
               p.umbrella_limit, p.insured_sex, p.insured_education_level,
               p.insured_occupation, p.insured_relationship, p.months_as_customer, p.age,
               p.capital_gains, p.capital_loss,
               v.auto_make, v.auto_year, c.total_claim_amount
        FROM claims c
        JOIN incidents i ON i.incident_id = c.incident_id
        JOIN policies  p ON p.policy_number = c.policy_number
        JOIN vehicles  v ON v.policy_number = c.policy_number
        WHERE c.claim_id = {int(claim_id)}
        """,
        get_engine(),
    )
    if row.empty:
        return ClaimScore(claim_id=claim_id, found=False, error=f"No claim with claim_id={claim_id}")

    X = row[categorical + numeric]
    proba = float(pipe.predict_proba(X)[:, 1][0])

    pre = pipe.named_steps["pre"]
    model = pipe.named_steps["model"]
    X_enc = pre.transform(X)
    if hasattr(X_enc, "toarray"):
        X_enc = X_enc.toarray()
    feature_names = list(pre.get_feature_names_out())
    explainer = shap.TreeExplainer(model)
    shap_row = explainer.shap_values(X_enc)[0]
    order = np.argsort(np.abs(shap_row))[::-1][:5]
    top_features = [
        {"feature": feature_names[i], "shap_value": float(shap_row[i])} for i in order
    ]

    return ClaimScore(
        claim_id=int(claim_id),
        found=True,
        fraud_probability=round(proba, 4),
        risk_band=_risk_band(proba),
        threshold=threshold,
        would_flag=bool(proba >= threshold),
        major_damage_rule_flags=bool(row.iloc[0]["incident_severity"] == "Major Damage"),
        incident_severity=str(row.iloc[0]["incident_severity"]),
        top_contributing_features=top_features,
    )


if __name__ == "__main__":
    cid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(json.dumps(asdict(score_claim(cid)), indent=2))
