"""Data-quality validation checks for the claims database.

Detects the two known defects documented in ANALYSIS.md (finding F7):
  1. An incident dated before its own policy's bind date -- impossible, a data-entry error.
     Checked directly against the loaded DB (it was never repaired, by design: ANALYSIS.md
     flags it rather than silently dropping the row).
  2. A negative umbrella_limit -- repaired to NULL by data/normalize_data.py before the
     original load. Checked by diffing the raw source CSV against the loaded DB, so the
     validator reports both "what was wrong" and "confirmed it was fixed."

Run:  python -m copilot.validate
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .config import PROJECT_ROOT
from .db import run_readonly

RAW_CSV = PROJECT_ROOT / "data" / "insurance_claims.csv"


@dataclass
class ValidationFinding:
    check: str
    status: str  # "FLAGGED_IN_DB" | "REPAIRED_UPSTREAM" | "OK"
    count: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""


def check_incident_before_bind() -> ValidationFinding:
    sql = """
        SELECT p.policy_number, p.policy_bind_date, i.incident_id, i.incident_date
        FROM policies p
        JOIN incidents i ON i.policy_number = p.policy_number
        WHERE i.incident_date < p.policy_bind_date
    """
    rows = run_readonly(sql)
    return ValidationFinding(
        check="incident_before_policy_bind_date",
        status="FLAGGED_IN_DB" if rows else "OK",
        count=len(rows),
        rows=rows,
        note=(
            "Incident dated before its policy existed -- a data-entry error. Kept and "
            "flagged rather than silently dropped, per ANALYSIS.md F7."
            if rows
            else "No incident-before-bind rows found."
        ),
    )


def check_negative_umbrella_limit() -> ValidationFinding:
    db_rows = run_readonly(
        "SELECT policy_number, umbrella_limit FROM policies WHERE umbrella_limit < 0"
    )
    raw = pd.read_csv(RAW_CSV)
    raw.columns = [c.strip().lower().replace("-", "_") for c in raw.columns]
    raw_bad = raw.loc[raw.umbrella_limit < 0, ["policy_number", "umbrella_limit"]].to_dict(
        "records"
    )

    if db_rows:
        status = "FLAGGED_IN_DB"
        note = "Negative umbrella_limit present in the loaded DB -- the upstream repair did not hold."
        rows = db_rows
    elif raw_bad:
        status = "REPAIRED_UPSTREAM"
        note = (
            "Raw source CSV had a negative umbrella_limit; data/normalize_data.py set it "
            "to NULL before load. Confirmed clean in the loaded DB."
        )
        rows = raw_bad
    else:
        status, note, rows = "OK", "No negative umbrella_limit in raw source or DB.", []

    return ValidationFinding(
        check="negative_umbrella_limit", status=status, count=len(rows), rows=rows, note=note
    )


def run_all() -> list[ValidationFinding]:
    return [check_incident_before_bind(), check_negative_umbrella_limit()]


if __name__ == "__main__":
    for finding in run_all():
        print(f"[{finding.status}] {finding.check} (n={finding.count})")
        print(f"   {finding.note}")
        for row in finding.rows:
            print("   ", row)
