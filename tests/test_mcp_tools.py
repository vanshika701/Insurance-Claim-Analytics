"""Tests for each of the 4 MCP tools: direct function calls (fast, exercises the tool
logic) plus one real stdio integration test (slower, exercises the actual MCP protocol
the way Claude Desktop or eval/run_eval.py will use it)."""
from __future__ import annotations

import asyncio
import sys

from copilot.config import PROJECT_ROOT
from mcp_server.server import get_schema, run_query, score_claim, search_guidelines


def test_get_schema() -> None:
    schema = get_schema()
    assert set(schema.keys()) == {"policies", "vehicles", "incidents", "claims"}
    for table, meta in schema.items():
        assert meta["description"]
        assert len(meta["columns"]) > 0


def test_run_query_good() -> None:
    result = run_query("SELECT COUNT(*) AS n FROM claims")
    assert result["ok"] is True
    assert result["rows"][0]["n"] == 1000


def test_run_query_blocked() -> None:
    result = run_query("SELECT 1; DROP TABLE claims")
    assert result["ok"] is False
    assert result["rows"] is None
    assert "one sql statement" in result["error"].lower()


def test_run_query_caps_rows() -> None:
    result = run_query("SELECT * FROM claims")
    assert result["ok"] is True
    assert result["row_count"] <= 100


def test_score_claim_known() -> None:
    """Exercises the exact in-process path the MCP server uses (subprocess-isolated
    internally) -- this is the scenario that used to segfault before the Phase 4 fix,
    now running safely alongside everything else in this same pytest session."""
    result = score_claim(1)
    assert result["found"] is True
    assert 0.0 <= result["fraud_probability"] <= 1.0


def test_score_claim_missing() -> None:
    result = score_claim(999999)
    assert result["found"] is False


def test_search_guidelines() -> None:
    result = search_guidelines("anti-fraud policy", k=3)
    assert len(result["results"]) > 0
    for r in result["results"]:
        assert r["file"].endswith(".pdf")
        assert r["page"] >= 1


def test_mcp_stdio_end_to_end() -> None:
    """A real MCP client connects to the server as a subprocess over stdio, lists tools,
    and calls one -- the actual protocol path, not just calling Python functions."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def run() -> list[str]:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(PROJECT_ROOT)
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool("get_schema", {})
                assert result.content and result.content[0].text
                return [t.name for t in tools.tools]

    names = asyncio.run(run())
    assert set(names) == {"get_schema", "run_query", "score_claim", "search_guidelines"}
