"""
Execute every query in queries/analysis_queries.sql against MySQL and print
the results as tidy tables. Lets a reviewer see outputs without a SQL client.

Usage:
    python queries/run_queries.py            # print all
    python queries/run_queries.py 3 6        # print only Q3 and Q6
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.connection import get_engine  # noqa: E402

SQL_FILE = Path(__file__).resolve().parent / "analysis_queries.sql"


def split_statements(sql_text: str) -> list[tuple[str, str]]:
    """Return [(title, statement), ...], title taken from the leading -- Qn. comment."""
    # strip the file header (everything before the first "-- Qn.")
    body = re.split(r"(?=-- -+\n-- Q\d+\.)", sql_text)
    out: list[tuple[str, str]] = []
    for chunk in body:
        m = re.search(r"-- (Q\d+\.[^\n]*)", chunk)
        if not m:
            continue
        # drop comment lines, keep the executable SQL up to the terminating ;
        code = "\n".join(
            line for line in chunk.splitlines() if not line.strip().startswith("--")
        ).strip().rstrip(";")
        if code:
            out.append((m.group(1).strip(), code))
    return out


def main() -> None:
    wanted = {int(a) for a in sys.argv[1:] if a.isdigit()}
    engine = get_engine()
    statements = split_statements(SQL_FILE.read_text())

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 160)

    for idx, (title, code) in enumerate(statements, start=1):
        if wanted and idx not in wanted:
            continue
        print("\n" + "=" * 78)
        print(title)
        print("=" * 78)
        df = pd.read_sql(code, engine)
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()
