"""AI Claims Investigator Copilot -- MCP server.

Exposes the claims database, the fraud-risk model, and the guideline search index to any
MCP client (Claude Desktop, or eval/run_eval.py as an automated client over stdio) via 4
tools: get_schema, run_query, score_claim, search_guidelines.

The SDK's ergonomic server class is named `MCPServer` as of mcp==2.3.0 (it was `FastMCP`
in SDK v1; see docs/INTERVIEW_NOTES.md Phase 0). Imported here under the `FastMCP` alias
only because that's the name this project's brief uses -- the class itself is MCPServer.

Run directly for a local stdio smoke test:
    python -m mcp_server.server
Or point Claude Desktop at it -- see docs/DEMO_SCRIPT.md / README.md for the config snippet.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer as FastMCP

from copilot.config import DB_BACKEND, PROJECT_ROOT
from copilot.db import get_schema as _get_schema
from copilot.db import run_readonly
from rag.retrieve import hybrid_search

from .sql_guard import SQLGuardError, validate_select, with_timeout

# score_claim deliberately does NOT import copilot.score (xgboost/shap) at module level.
# See docs/INTERVIEW_NOTES.md Phase 4 "the segfault": loading XGBoost/SHAP and
# sentence-transformers/torch in the same process crashes (a native OpenMP/BLAS runtime
# conflict on macOS) once both have actually been *used* -- import order didn't matter,
# only use order, which made it a landmine for any future tool call, not a one-time
# ordering fix. Scoring is isolated in its own subprocess instead, which sidesteps the
# conflict entirely regardless of its exact native-library root cause.
SCORE_SUBPROCESS_TIMEOUT = 15.0

SQL_DIALECT = "mysql" if DB_BACKEND == "mysql" else "sqlite"

server = FastMCP(
    name="claims-investigator-copilot",
    title="AI Claims Investigator Copilot",
    instructions=(
        "Tools for investigating auto-insurance claims in the Insurance Claims Analytics "
        "database: get_schema to see the tables, run_query for read-only SQL (SELECT "
        "only, max 100 rows, single statement), score_claim for a fraud-risk probability "
        "with SHAP explanation, and search_guidelines for cited passages from real "
        "insurance-fraud regulatory guidelines. Start with get_schema if you haven't seen "
        "the schema yet. This is a small, curated 1,000-row teaching dataset with an "
        "artificial ~24.7% fraud rate -- treat results as relative findings, not "
        "real-world forecasts."
    ),
)


@server.tool()
def get_schema() -> dict[str, Any]:
    """Return the claims database's schema: all 4 tables (policies, vehicles, incidents,
    claims), their columns with types, and a short description of what each table holds
    and how it joins to the others. Call this first if you haven't seen the schema -- it
    tells you what run_query can select and join on."""
    return _get_schema()


@server.tool()
def run_query(sql: str) -> dict[str, Any]:
    """Run a READ-ONLY SQL query against the claims database and return the rows.

    Guardrails (see mcp_server/sql_guard.py): exactly one statement; must be a SELECT
    (or UNION/INTERSECT/EXCEPT of SELECTs) -- INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/
    PRAGMA and similar are rejected; dangerous functions like LOAD_FILE/SLEEP are
    rejected; results are capped at 100 rows (add your own LIMIT <= 100, or one is added
    for you); the query has a 5-second timeout. On a guardrail violation this returns
    {"ok": false, "error": "..."} instead of raising, so you can read the reason and
    retry with a corrected query. Use get_schema first if you're not sure what's
    queryable.
    """
    try:
        guarded = validate_select(sql, dialect=SQL_DIALECT)
    except SQLGuardError as e:
        return {"ok": False, "error": str(e), "rows": None, "sql_executed": None}

    try:
        rows = with_timeout(run_readonly, guarded.sql, row_limit=guarded.row_limit)
    except SQLGuardError as e:
        return {"ok": False, "error": str(e), "rows": None, "sql_executed": guarded.sql}
    except Exception as e:  # a real DB error (bad column name, etc.) -- surface it plainly
        return {"ok": False, "error": f"Database error: {e}", "rows": None, "sql_executed": guarded.sql}

    rows = [{k: (str(v) if hasattr(v, "isoformat") else v) for k, v in row.items()} for row in rows]
    return {"ok": True, "error": None, "rows": rows, "row_count": len(rows), "sql_executed": guarded.sql}


@server.tool()
def score_claim(claim_id: int) -> dict[str, Any]:
    """Score one claim's fraud risk: probability (0-1), a risk band (low/medium/high), the
    top 5 features driving that specific prediction (SHAP values -- positive pushes toward
    fraud, negative away from it), and whether the simple "flag all Major Damage" baseline
    rule would flag it. Use get_schema or run_query first to find a valid claim_id.
    NOTE: this model does not beat the baseline rule in cross-validation (see
    results/model_metrics.json) -- its value here is the per-claim explanation, not
    superior accuracy. Treat scores as relative risk signals on a small curated dataset,
    not calibrated real-world probabilities.
    """
    # Isolated in a subprocess -- see the module-level comment above.
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "copilot.score", str(int(claim_id))],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=SCORE_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"claim_id": claim_id, "found": False, "error": "Scoring timed out."}
    except Exception as e:
        return {"claim_id": claim_id, "found": False, "error": f"Could not run scorer: {e}"}

    if proc.returncode != 0:
        return {
            "claim_id": claim_id,
            "found": False,
            "error": f"Scorer process failed: {proc.stderr.strip()[-500:]}",
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"claim_id": claim_id, "found": False, "error": f"Bad scorer output: {proc.stdout[-300:]}"}


@server.tool()
def search_guidelines(query: str, k: int = 5) -> dict[str, Any]:
    """Search real public insurance-fraud regulatory guideline documents (IRDAI Insurance
    Fraud Monitoring Framework Guidelines 2025, California DOI SIU Annual Report) using
    hybrid retrieval (BM25 + semantic vector search, combined with Reciprocal Rank
    Fusion). Every result includes the source file name and the exact PDF page number, so
    you can cite it. Use this to ground an answer about fraud policy/process in an actual
    regulatory source rather than general knowledge.
    """
    hits = hybrid_search(query, k=k)
    return {
        "query": query,
        "results": [
            {"file": h.file, "page": h.page, "text": h.text, "score": round(h.score, 4)}
            for h in hits
        ],
    }


if __name__ == "__main__":
    server.run(transport="stdio")
