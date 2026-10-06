"""Read-only SQL guardrails for untrusted (LLM-generated) SQL.

Rules enforced, in order:
  1. Must parse as SQL at all.
  2. Exactly ONE statement -- `sqlglot.parse` splits on `;`, so "SELECT 1; DROP TABLE x"
     parses as two statements and is rejected outright, including the comment-trick
     variant ("SELECT 1; -- ; DROP TABLE x") where the trailing text is a harmless
     comment but still counts as a second (empty) statement.
  3. The one statement's root must be a read-only form: SELECT, or a set operation over
     SELECTs (UNION/INTERSECT/EXCEPT). Anything else -- INSERT, UPDATE, DELETE, DROP,
     ALTER, CREATE, ATTACH, PRAGMA, TRUNCATE, REPLACE, MERGE, CALL -- is rejected by type,
     not by keyword-matching the input text (which is easy to evade; matching the parsed
     AST's node type is not).
  4. No call to a function on the danger list anywhere in the parsed tree (LOAD_FILE,
     SLEEP, BENCHMARK, GET_LOCK, ...), whether written as a normal call or hidden in a
     subquery/CASE/UNION branch -- the AST walk finds it regardless of where it's nested.
  5. A LIMIT is enforced: if the query already has one, it must be <= MAX_ROWS (an
     oversized LIMIT is rejected with a clear message rather than silently clamped, so the
     caller knows their request was capped); if it has none, MAX_ROWS is appended.
  6. **The query that actually gets executed is sqlglot's regenerated SQL from the parsed
     AST, not the caller's raw text.** This is deliberate defense in depth: what gets
     executed is the parser's own, guaranteed-reparseable rendering of exactly the single
     statement it validated (checked in tests/test_sql_guard.py by reparsing the guard's
     output and confirming it's still exactly one SELECT) -- not whatever raw bytes the
     caller sent. It does NOT strip harmless comments (sqlglot legitimately keeps those
     attached to nodes); the protection a comment could actually defeat -- hiding a second
     statement after it -- is caught earlier, by the single-statement check.

`run_query` in mcp_server/server.py also wraps execution in a wall-clock timeout (see
`with_timeout` below) and returns guard failures as a normal (non-crashing) tool result so
an LLM caller can read the reason and retry with a corrected query.
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

MAX_ROWS = 100
QUERY_TIMEOUT_SECONDS = 5.0

READONLY_ROOT_TYPES: tuple[type[exp.Expression], ...] = (exp.Select, exp.Union, exp.Intersect, exp.Except)

# Functions that read/write the filesystem, leak timing info, or stall the connection.
# Checked both as recognized sqlglot function nodes and as exp.Anonymous (unrecognized)
# calls, case-insensitively, since a function sqlglot doesn't have a dedicated class for
# (most MySQL-specific ones) comes through as Anonymous.
FORBIDDEN_FUNCTIONS = {
    "load_file", "sleep", "benchmark", "get_lock", "release_lock",
    "master_pos_wait", "sys_exec", "sys_eval", "load_extension",
}
# Belt-and-suspenders textual check for clauses sqlglot might represent in ways the AST
# walk above doesn't catch in some dialect/version combination (e.g. INTO OUTFILE, which
# this sqlglot version already refuses to parse under the mysql dialect -- checked here
# too in case a future/other dialect parses it successfully).
FORBIDDEN_SUBSTRINGS = ("into outfile", "into dumpfile", "attach database")


class SQLGuardError(Exception):
    """Raised when untrusted SQL fails a guardrail. The message is safe to show the
    caller (including an LLM) -- it never echoes back raw exception internals."""


@dataclass
class GuardedQuery:
    sql: str  # the AST-regenerated SQL that will actually be executed
    row_limit: int


def _function_name(node: exp.Expression) -> str | None:
    if isinstance(node, exp.Anonymous):
        return str(node.this).lower()
    if isinstance(node, exp.Func):
        name = node.sql_name()
        return name.lower() if name else None
    return None


def _check_forbidden_functions(stmt: exp.Expression) -> None:
    for node in stmt.walk():
        item = node[0] if isinstance(node, tuple) else node
        name = _function_name(item)
        if name and name in FORBIDDEN_FUNCTIONS:
            raise SQLGuardError(f"Function '{name}()' is not allowed in queries.")


def _enforce_limit(stmt: exp.Expression, dialect: str) -> str:
    existing = stmt.args.get("limit")
    if existing is not None:
        try:
            n = int(existing.expression.this)
        except (AttributeError, ValueError, TypeError):
            raise SQLGuardError("Could not parse the LIMIT value; use a plain integer.")
        if n > MAX_ROWS:
            raise SQLGuardError(
                f"LIMIT {n} exceeds the maximum of {MAX_ROWS} rows for this tool. "
                f"Lower the LIMIT and, if you need more data, narrow the WHERE clause."
            )
        return stmt.sql(dialect=dialect)
    return f"{stmt.sql(dialect=dialect)} LIMIT {MAX_ROWS}"


def validate_select(sql: str, dialect: str = "mysql") -> GuardedQuery:
    sql = (sql or "").strip()
    if not sql:
        raise SQLGuardError("Empty query.")
    if any(bad in sql.lower() for bad in FORBIDDEN_SUBSTRINGS):
        raise SQLGuardError("This query contains a disallowed clause (file I/O or ATTACH).")

    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except Exception as e:  # sqlglot raises several different error types
        raise SQLGuardError(f"Could not parse SQL: {e}") from e

    if len(statements) != 1:
        raise SQLGuardError(
            f"Exactly one SQL statement is allowed; found {len(statements)}. "
            "Multiple statements separated by ';' (including a trailing comment after "
            "one) are rejected."
        )

    stmt = statements[0]
    if not isinstance(stmt, READONLY_ROOT_TYPES):
        raise SQLGuardError(
            f"Only SELECT (or UNION/INTERSECT/EXCEPT of SELECTs) is allowed; got "
            f"{type(stmt).__name__}. INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/ATTACH/"
            f"PRAGMA and similar statements are rejected."
        )

    _check_forbidden_functions(stmt)
    guarded_sql = _enforce_limit(stmt, dialect)
    return GuardedQuery(sql=guarded_sql, row_limit=MAX_ROWS)


def with_timeout(fn, *args, timeout: float = QUERY_TIMEOUT_SECONDS, **kwargs):
    """Run fn(*args, **kwargs) with a wall-clock timeout. Honest limitation: Python
    cannot forcibly kill a thread mid-syscall, so a DB call that ignores cancellation may
    keep running in the background after this raises -- acceptable for a demo-scale,
    row-limited, read-only guard (the query is capped at MAX_ROWS regardless), but not a
    substitute for a database-side statement timeout in a production deployment."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as e:
            raise SQLGuardError(f"Query exceeded the {timeout:.0f}s timeout.") from e
