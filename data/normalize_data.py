"""
Clean the raw flat Kaggle dataset and normalize it into 4 related tables.

Input : data/insurance_claims.csv   (1,000 rows x 39 cols + junk _c39)
Output: data/{policies,vehicles,incidents,claims}.csv  and, unless --no-db is
        passed, the same data loaded into the MySQL `insurance_claims` database
        using the schema in db/schema.sql.

Cleaning steps
--------------
* column names: hyphens -> underscores, lowercased
* drop the trailing junk column `_c39`
* `"?"` placeholders (collision_type, property_damage, police_report_available)
  -> NULL / NaN  (rows are kept, not dropped)
* `umbrella_limit` has one negative value in the raw data -> set to NULL
* generate surrogate keys: vehicle_id, incident_id, claim_id

Normalization (see db/schema.sql for the full DDL)
-------------------------------------------------
    policies (policy_number PK)
       |-- vehicles  (vehicle_id PK, policy_number FK)
       |-- incidents (incident_id PK, policy_number FK)
              |-- claims (claim_id PK, incident_id FK, policy_number FK)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
RAW_CSV = HERE / "insurance_claims.csv"
SCHEMA_SQL = PROJECT_ROOT / "db" / "schema.sql"

QUESTION_MARK_COLS = ["collision_type", "property_damage", "police_report_available"]

POLICY_COLS = [
    "policy_number", "months_as_customer", "age", "policy_bind_date", "policy_state",
    "policy_csl", "policy_deductable", "policy_annual_premium", "umbrella_limit",
    "insured_zip", "insured_sex", "insured_education_level", "insured_occupation",
    "insured_hobbies", "insured_relationship", "capital_gains", "capital_loss",
]
VEHICLE_COLS = ["vehicle_id", "policy_number", "auto_make", "auto_model", "auto_year"]
INCIDENT_COLS = [
    "incident_id", "policy_number", "incident_date", "incident_type", "collision_type",
    "incident_severity", "authorities_contacted", "incident_state", "incident_city",
    "incident_location", "incident_hour_of_the_day", "number_of_vehicles_involved",
    "property_damage", "bodily_injuries", "witnesses", "police_report_available",
]
CLAIM_COLS = [
    "claim_id", "policy_number", "incident_id", "total_claim_amount",
    "injury_claim", "property_claim", "vehicle_claim", "fraud_reported",
]


def load_and_clean(raw_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(raw_csv)

    # column names: hyphens -> underscores, lowercase
    df.columns = [c.strip().lower().replace("-", "_") for c in df.columns]

    # drop junk trailing column(s)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_c")], errors="ignore")

    # "?" placeholders -> NaN
    for col in QUESTION_MARK_COLS:
        df[col] = df[col].replace("?", np.nan)

    # authorities_contacted already has real NaNs in the raw file -> normalize blank strings too
    df["authorities_contacted"] = df["authorities_contacted"].replace({"?": np.nan, "": np.nan})

    # negative umbrella_limit is a data error -> NULL
    neg = int((df["umbrella_limit"] < 0).sum())
    if neg:
        print(f"  [clean] {neg} negative umbrella_limit value(s) set to NULL")
        df.loc[df["umbrella_limit"] < 0, "umbrella_limit"] = np.nan

    # parse dates
    df["policy_bind_date"] = pd.to_datetime(df["policy_bind_date"]).dt.date
    df["incident_date"] = pd.to_datetime(df["incident_date"]).dt.date

    # surrogate keys (stable: 1..N in file order)
    df = df.reset_index(drop=True)
    df["vehicle_id"] = df.index + 1
    df["incident_id"] = df.index + 1
    df["claim_id"] = df.index + 1

    return df


def split_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "policies": df[POLICY_COLS].copy(),
        "vehicles": df[VEHICLE_COLS].copy(),
        "incidents": df[INCIDENT_COLS].copy(),
        "claims": df[CLAIM_COLS].copy(),
    }


def validate(tables: dict[str, pd.DataFrame]) -> None:
    p, v, i, c = tables["policies"], tables["vehicles"], tables["incidents"], tables["claims"]
    assert p["policy_number"].is_unique, "policy_number not unique"
    assert set(v["policy_number"]) <= set(p["policy_number"]), "vehicle FK violation"
    assert set(i["policy_number"]) <= set(p["policy_number"]), "incident FK violation"
    assert set(c["policy_number"]) <= set(p["policy_number"]), "claim FK violation"
    assert set(c["incident_id"]) <= set(i["incident_id"]), "claim->incident FK violation"
    bad = ((c.injury_claim + c.property_claim + c.vehicle_claim) != c.total_claim_amount).sum()
    assert bad == 0, f"{bad} claim rows where parts != total"
    print("  [validate] PK/FK integrity + claim-amount arithmetic OK")


def write_csvs(tables: dict[str, pd.DataFrame], out_dir: Path) -> None:
    for name, frame in tables.items():
        path = out_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        print(f"  [csv] {path.name:16s} {len(frame):>5d} rows")


def load_mysql(tables: dict[str, pd.DataFrame], schema_sql: Path) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from db.connection import get_engine  # noqa: E402
    from sqlalchemy import text  # noqa: E402

    engine = get_engine()
    ddl = schema_sql.read_text()

    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
            conn.execute(text(stmt))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    for name in ["policies", "vehicles", "incidents", "claims"]:
        frame = tables[name].where(pd.notnull(tables[name]), None)
        frame.to_sql(name, engine, if_exists="append", index=False)
        print(f"  [mysql] loaded {name}")

    with engine.connect() as conn:
        for name in ["policies", "vehicles", "incidents", "claims"]:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
            print(f"  [mysql] {name:10s} {n:>5d} rows")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-db", action="store_true", help="write CSVs only, skip MySQL load")
    args = ap.parse_args()

    print(f"Reading {RAW_CSV.relative_to(PROJECT_ROOT)}")
    df = load_and_clean(RAW_CSV)
    tables = split_tables(df)
    validate(tables)
    write_csvs(tables, HERE)

    if args.no_db:
        print("Skipping MySQL load (--no-db).")
        return
    load_mysql(tables, SCHEMA_SQL)
    print("Done.")


if __name__ == "__main__":
    main()
