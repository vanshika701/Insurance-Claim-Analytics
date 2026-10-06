"""Formalizes the adversarial + legitimate SQL battery run manually in Phase 4 into
pytest cases. Each is (sql, should_pass) -- should_pass=False cases are injection/bypass/
abuse attempts; should_pass=True cases are ordinary read-only queries that must not be
rejected by mistake (a guard that blocks everything isn't a guard, it's a wall)."""
from __future__ import annotations

import pytest

from mcp_server.sql_guard import SQLGuardError, validate_select

SHOULD_BLOCK = [
    ("SELECT * FROM policies; DROP TABLE policies", "stacked DROP"),
    ("SELECT 1; -- ; DROP TABLE x", "comment-hidden second statement"),
    ("SELECT * FROM policies; SELECT * FROM claims", "two legitimate SELECTs stacked"),
    ("DROP TABLE policies", "bare DROP"),
    ("UPDATE policies SET age = 0", "bare UPDATE"),
    ("DELETE FROM claims", "bare DELETE"),
    ("INSERT INTO claims (claim_id) VALUES (1)", "bare INSERT"),
    ("ALTER TABLE policies ADD COLUMN x INT", "bare ALTER"),
    ("ATTACH DATABASE '/tmp/x.db' AS x", "ATTACH (sqlite file-system abuse)"),
    ("PRAGMA table_info(policies)", "PRAGMA"),
    ("SELECT load_file('/etc/passwd')", "LOAD_FILE() file read"),
    ("SELECT sleep(10)", "SLEEP() DoS"),
    ("SELECT benchmark(1000000, MD5('x'))", "BENCHMARK() DoS"),
    ("SELECT * FROM policies INTO OUTFILE '/tmp/x.csv'", "INTO OUTFILE file write"),
    ("SELECT * FROM policies LIMIT 99999", "oversized LIMIT"),
    ("", "empty query"),
    ("not even sql", "garbage input"),
    ("SELECT * FROM policies UNION SELECT load_file('/x')", "forbidden fn hidden in a UNION branch"),
    ("SELECT * FROM (SELECT sleep(5)) t", "forbidden fn hidden in a subquery"),
]

SHOULD_ALLOW = [
    ("SELECT * FROM policies", "bare select, no limit (one gets added)"),
    ("SELECT * FROM policies LIMIT 10", "select with a reasonable limit"),
    ("SELECT * FROM policies UNION SELECT * FROM policies", "legitimate UNION"),
    ("WITH x AS (SELECT 1 AS a) SELECT * FROM x", "CTE"),
    ("SELECT * FROM policies /* note */ WHERE age > 30", "inline comment, legitimate WHERE"),
    ("SELECT p.policy_number FROM policies p JOIN claims c ON c.policy_number = p.policy_number", "join"),
]


@pytest.mark.parametrize("sql,reason", SHOULD_BLOCK, ids=[r for _, r in SHOULD_BLOCK])
def test_blocks(sql: str, reason: str) -> None:
    with pytest.raises(SQLGuardError):
        validate_select(sql, dialect="mysql")


@pytest.mark.parametrize("sql,reason", SHOULD_ALLOW, ids=[r for _, r in SHOULD_ALLOW])
def test_allows(sql: str, reason: str) -> None:
    guarded = validate_select(sql, dialect="mysql")
    assert "limit" in guarded.sql.lower()
    assert guarded.row_limit == 100


def test_limit_is_capped_not_silently_raised() -> None:
    """A LIMIT under the cap is left as-is, not bumped up to 100."""
    guarded = validate_select("SELECT * FROM policies LIMIT 5", dialect="mysql")
    assert "limit 5" in guarded.sql.lower()


def test_executed_sql_reparses_as_a_single_select() -> None:
    """The guard's output (what actually gets executed) must itself be unambiguous,
    single-statement, re-parseable SQL -- the defense-in-depth property that matters is
    not "comments are stripped" (sqlglot's regeneration legitimately keeps harmless
    comments attached to nodes), it's that the EXECUTED string, reparsed, still yields
    exactly one read-only statement. A malformed or multi-statement result here would
    mean the guard's own output could smuggle something past itself."""
    import sqlglot
    from sqlglot import exp

    guarded = validate_select("SELECT * FROM policies /* note */ WHERE age > 30", dialect="mysql")
    reparsed = [s for s in sqlglot.parse(guarded.sql, read="mysql") if s is not None]
    assert len(reparsed) == 1
    assert isinstance(reparsed[0], exp.Select)
