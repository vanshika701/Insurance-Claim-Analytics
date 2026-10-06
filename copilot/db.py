"""Read-only data access layer for the Copilot extension.

Backend is chosen by DB_BACKEND (see copilot/config.py):
  - "mysql" (default): reuses db/connection.py's engine against the existing
    insurance_claims MySQL database.
  - "sqlite": data/claims.db, built by `python -m copilot.build_sqlite`. No MySQL
    server required -- used for evaluation/CI and anyone without this project's
    MySQL user configured.

Everything here is read-only *by convention*. The actual enforcement that untrusted SQL
can only be a single SELECT statement lives in mcp_server/sql_guard.py, which is the only
caller that should ever pass free-text SQL from an LLM into run_readonly(). Internal,
trusted callers (validate.py, the model's feature builder) may call it directly with SQL
they wrote themselves.
"""
from __future__ import annotations

import sys
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .config import DB_BACKEND, PROJECT_ROOT, SQLITE_PATH

sys.path.insert(0, str(PROJECT_ROOT))  # so `import db.connection` (the original module) resolves

_engine: Engine | None = None

SCHEMA_DESCRIPTIONS: dict[str, str] = {
    "policies": "One row per insurance policy: the insured person and policy terms. "
                "Primary key: policy_number.",
    "vehicles": "One row per insured vehicle. Links to policies via policy_number.",
    "incidents": "One row per reported incident/accident. Links to policies via "
                 "policy_number. incident_severity is the strongest known fraud signal "
                 "in this dataset (see ANALYSIS.md finding F1/F2).",
    "claims": "One row per claim: dollar amounts and the fraud_reported ground-truth "
              "label ('Y'/'N'). Links to incidents via incident_id.",
}

TABLES = ("policies", "vehicles", "incidents", "claims")


def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine for the configured backend."""
    global _engine
    if _engine is not None:
        return _engine

    if DB_BACKEND == "sqlite":
        if not SQLITE_PATH.exists():
            raise FileNotFoundError(
                f"SQLite fallback DB not found at {SQLITE_PATH}. Build it with: "
                f"python -m copilot.build_sqlite"
            )
        from sqlalchemy import create_engine

        _engine = create_engine(f"sqlite:///{SQLITE_PATH}")
    else:
        from db.connection import get_engine as _mysql_engine  # the original project's helper

        _engine = _mysql_engine()
    return _engine


def get_schema() -> dict[str, Any]:
    """Return {table: {description, columns: [{name, type, nullable}]}} for all 4 tables."""
    insp = sa_inspect(get_engine())
    schema: dict[str, Any] = {}
    for table in TABLES:
        columns = [
            {"name": c["name"], "type": str(c["type"]), "nullable": bool(c["nullable"])}
            for c in insp.get_columns(table)
        ]
        schema[table] = {"description": SCHEMA_DESCRIPTIONS[table], "columns": columns}
    return schema


def run_readonly(sql: str, params: dict | None = None, row_limit: int = 500) -> list[dict]:
    """Execute SQL and return rows as a list of dicts, capped at row_limit."""
    with get_engine().connect() as conn:
        result = conn.execute(text(sql), params or {})
        cols = list(result.keys())
        rows = result.fetchmany(row_limit)
        return [dict(zip(cols, row)) for row in rows]


if __name__ == "__main__":
    print(f"backend = {DB_BACKEND}")
    for table, meta in get_schema().items():
        n = run_readonly(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        print(f"  {table:10s} {n:>5d} rows  -- {meta['description']}")
