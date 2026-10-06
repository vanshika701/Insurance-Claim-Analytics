"""Build the SQLite fallback database at data/claims.db.

Source: the already-cleaned data/{policies,vehicles,incidents,claims}.csv, produced by
data/normalize_data.py (run that first if those CSVs don't exist yet). This lets the
Copilot extension -- and anyone evaluating it -- run with zero MySQL setup via
DB_BACKEND=sqlite.

Run:  python -m copilot.build_sqlite
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from .config import PROJECT_ROOT, SQLITE_PATH

SCHEMA_SQLITE = PROJECT_ROOT / "db" / "schema_sqlite.sql"
DATA_DIR = PROJECT_ROOT / "data"
TABLES = ["policies", "vehicles", "incidents", "claims"]


def main() -> None:
    missing = [t for t in TABLES if not (DATA_DIR / f"{t}.csv").exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing normalized CSVs for {missing}. Run first: "
            f"python data/normalize_data.py --no-db"
        )

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.executescript(SCHEMA_SQLITE.read_text())

    for table in TABLES:
        df = pd.read_csv(DATA_DIR / f"{table}.csv")
        df.to_sql(table, conn, if_exists="append", index=False)

    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    conn.close()
    print(f"Built {SQLITE_PATH}")
    for t, n in counts.items():
        print(f"  {t:10s} {n:>5d} rows")


if __name__ == "__main__":
    main()
