"""Feature construction for the fraud-risk model.

Builds one row per claim from the 4 joined tables, and is explicit about every column
that was considered and excluded. "Leakage" here means: a column that could not actually
be known at the moment a claim is filed and triaged, or that trivially identifies a row
rather than describing it.

EXCLUDED_COLUMNS documents every exclusion and the reason, because the brief requires it
and because it's the honest way to defend the feature set in review.
"""
from __future__ import annotations

import pandas as pd

from .db import get_engine

# column -> why it is NOT a model feature
EXCLUDED_COLUMNS: dict[str, str] = {
    "fraud_reported": "the label itself.",
    "claim_id": "surrogate key, no generalizable signal; a tree could memorize it.",
    "incident_id": "surrogate key, same reason.",
    "policy_number": "natural key, same reason.",
    "vehicle_id": "surrogate key, same reason.",
    "insured_zip": "995 distinct values across 1,000 rows -- functionally an identifier, "
                   "not a generalizable category; including it risks memorizing individual "
                   "policyholders rather than learning a pattern.",
    "incident_city": "high-cardinality free text; same identifier risk as insured_zip.",
    "incident_location": "a street address -- uniquely identifying, not a repeatable pattern.",
    "auto_model": "39 values spread across only 14 auto_make values and 1,000 rows -- too "
                  "sparse to generalize; auto_make alone already captures the make-level "
                  "signal found in the SQL analysis (ANALYSIS.md F5).",
    "injury_claim": "a component of total_claim_amount (injury + property + vehicle = total, "
                    "verified in data/normalize_data.py). Including the components alongside "
                    "the total adds perfect collinearity, not new information.",
    "property_claim": "same reason as injury_claim.",
    "vehicle_claim": "same reason as injury_claim.",
    "policy_bind_date": "raw date; tenure is already captured by months_as_customer. The SQL "
                        "analysis (Q3) found no usable signal from the exact bind date.",
    "incident_date": "raw date; the data only spans ~2 months (ANALYSIS.md F6/Q8), so a "
                     "date-derived feature would overfit to that narrow window rather than "
                     "learn anything that generalizes.",
    "insured_hobbies": "EXCLUDED FROM THE PRODUCTION MODEL DESPITE BEING THE SINGLE STRONGEST "
                       "UNIVARIATE PREDICTOR FOUND. 'chess' -> 82.6% fraud (n=46) and "
                       "'cross-fit' -> 74.3% fraud (n=35), versus <=30% for every other one "
                       "of 20 hobby values and a 24.7% portfolio base rate. There is no "
                       "real-world causal story connecting a hobby to fraud at that "
                       "magnitude; this is a well-known artifact of this specific public "
                       "dataset. Using it would make the model look far more accurate than "
                       "any model built on real claims data could be. A sensitivity run WITH "
                       "it included is still produced (see train_model.py --with-hobbies) "
                       "purely to document the effect size, never as a deployed feature.",
}

CATEGORICAL_FEATURES: list[str] = [
    "incident_severity", "incident_type", "collision_type", "authorities_contacted",
    "property_damage", "police_report_available", "incident_state",
    "policy_state", "policy_csl", "insured_sex", "insured_education_level",
    "insured_occupation", "insured_relationship", "auto_make",
]
NUMERIC_FEATURES: list[str] = [
    "number_of_vehicles_involved", "bodily_injuries", "witnesses", "incident_hour_of_the_day",
    "months_as_customer", "age", "policy_deductable", "policy_annual_premium",
    "umbrella_limit", "capital_gains", "capital_loss", "auto_year", "total_claim_amount",
]

_QUERY = """
    SELECT
        c.claim_id, c.total_claim_amount, c.fraud_reported,
        i.incident_severity, i.incident_type, i.collision_type, i.authorities_contacted,
        i.property_damage, i.police_report_available, i.incident_state,
        i.number_of_vehicles_involved, i.bodily_injuries, i.witnesses,
        i.incident_hour_of_the_day,
        p.policy_state, p.policy_csl, p.policy_deductable, p.policy_annual_premium,
        p.umbrella_limit, p.insured_sex, p.insured_education_level, p.insured_occupation,
        p.insured_relationship, p.insured_hobbies, p.months_as_customer, p.age,
        p.capital_gains, p.capital_loss,
        v.auto_make, v.auto_year
    FROM claims c
    JOIN incidents i ON i.incident_id = c.incident_id
    JOIN policies  p ON p.policy_number = c.policy_number
    JOIN vehicles  v ON v.policy_number = c.policy_number
"""


def load_claims(with_hobbies: bool = False) -> pd.DataFrame:
    """One row per claim. `claim_id` is kept for joining back to predictions/SHAP output
    but is never passed into the model (see CATEGORICAL_FEATURES / NUMERIC_FEATURES)."""
    df = pd.read_sql(_QUERY, get_engine())
    df["y"] = (df.fraud_reported == "Y").astype(int)
    df["is_major_damage"] = (df.incident_severity == "Major Damage").astype(int)
    if not with_hobbies:
        df = df.drop(columns=["insured_hobbies"])
    return df


def feature_columns(with_hobbies: bool = False) -> tuple[list[str], list[str]]:
    cats = list(CATEGORICAL_FEATURES) + (["insured_hobbies"] if with_hobbies else [])
    return cats, list(NUMERIC_FEATURES)


if __name__ == "__main__":
    df = load_claims()
    cats, nums = feature_columns()
    print(f"{len(df)} claims, {len(cats)} categorical + {len(nums)} numeric features")
    print("excluded columns documented:", len(EXCLUDED_COLUMNS))
