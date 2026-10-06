"""Evaluation: retrieval quality (BM25 vs vector vs hybrid) + a full MCP-protocol
end-to-end check of every tool.

The retrieval-vs-ground-truth comparison connects to the MCP server AS AN MCP CLIENT over
stdio for the hybrid method -- that's the method actually shipped as the
`search_guidelines` tool, so its numbers are measured through the real protocol path
(exactly how Claude Desktop would see it), not just the library function. BM25-only and
vector-only aren't separately exposed as MCP tools (only hybrid is, by design -- see
docs/INTERVIEW_NOTES.md Phase 3), so those two comparison arms call rag/retrieve.py
directly; hybrid is *also* computed directly as a same-process sanity check that it
matches the MCP-protocol numbers.

Run:  python -m eval.run_eval
Writes: results/retrieval_metrics.json
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Callable

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from copilot.config import PROJECT_ROOT, RESULTS_DIR
from rag.retrieve import bm25_search, hybrid_search, vector_search

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
K_RETRIEVE = 10  # retrieve this many for ranking; hit@5 checks rank <= 5 within it
HIT_AT = 5


def _rank(citations: list[tuple[str, int]], expected_file: str, expected_page: int) -> int | None:
    for i, (file, page) in enumerate(citations, start=1):
        if file == expected_file and page == expected_page:
            return i
    return None


def _score(ranks: list[int | None]) -> dict[str, float]:
    hits = sum(1 for r in ranks if r is not None and r <= HIT_AT)
    mrr = sum((1.0 / r) if r is not None else 0.0 for r in ranks) / len(ranks)
    return {"hit_at_5": hits / len(ranks), "mrr": mrr, "n": len(ranks)}


def evaluate_direct(questions: list[dict], search_fn: Callable[[str, int], list]) -> dict:
    ranks = []
    per_question = []
    for q in questions:
        results = search_fn(q["question"], K_RETRIEVE)
        citations = [(r.file, r.page) for r in results]
        rank = _rank(citations, q["expected_file"], q["expected_page"])
        ranks.append(rank)
        per_question.append({"id": q["id"], "rank": rank})
    return {**_score(ranks), "per_question": per_question}


async def evaluate_hybrid_via_mcp(questions: list[dict]) -> dict:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(PROJECT_ROOT)
    )
    ranks = []
    per_question = []
    tool_checks: dict[str, Any] = {}

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool_names = {t.name for t in (await session.list_tools()).tools}
            tool_checks["tools_listed"] = sorted(tool_names)

            for q in questions:
                result = await session.call_tool(
                    "search_guidelines", {"query": q["question"], "k": K_RETRIEVE}
                )
                payload = json.loads(result.content[0].text)
                citations = [(r["file"], r["page"]) for r in payload["results"]]
                rank = _rank(citations, q["expected_file"], q["expected_page"])
                ranks.append(rank)
                per_question.append({"id": q["id"], "rank": rank})

            # --- end-to-end check: call every tool through the SAME MCP client ---
            schema_result = await session.call_tool("get_schema", {})
            schema = json.loads(schema_result.content[0].text)
            tool_checks["get_schema"] = {"ok": set(schema.keys()) == {"policies", "vehicles", "incidents", "claims"}}

            good_q = await session.call_tool("run_query", {"sql": "SELECT COUNT(*) AS n FROM claims"})
            good_payload = json.loads(good_q.content[0].text)
            tool_checks["run_query_valid"] = {"ok": good_payload.get("ok") is True and good_payload["rows"][0]["n"] == 1000}

            bad_q = await session.call_tool("run_query", {"sql": "SELECT 1; DROP TABLE claims"})
            bad_payload = json.loads(bad_q.content[0].text)
            tool_checks["run_query_blocked_injection"] = {"ok": bad_payload.get("ok") is False}

            score_result = await session.call_tool("score_claim", {"claim_id": 1})
            score_payload = json.loads(score_result.content[0].text)
            tool_checks["score_claim"] = {"ok": score_payload.get("found") is True}

    return {**_score(ranks), "per_question": per_question, "end_to_end_tool_checks": tool_checks}


def main() -> None:
    questions = json.loads(QUESTIONS_PATH.read_text())
    print(f"Loaded {len(questions)} eval questions.")

    print("\n--- BM25-only (direct) ---")
    bm25_result = evaluate_direct(questions, bm25_search)
    print(bm25_result["hit_at_5"], bm25_result["mrr"])

    print("--- Vector-only (direct) ---")
    vector_result = evaluate_direct(questions, vector_search)
    print(vector_result["hit_at_5"], vector_result["mrr"])

    print("--- Hybrid (direct, same-process sanity check) ---")
    hybrid_direct_result = evaluate_direct(questions, hybrid_search)
    print(hybrid_direct_result["hit_at_5"], hybrid_direct_result["mrr"])

    print("--- Hybrid (via real MCP client over stdio) + full tool end-to-end check ---")
    hybrid_mcp_result = asyncio.run(evaluate_hybrid_via_mcp(questions))
    print(hybrid_mcp_result["hit_at_5"], hybrid_mcp_result["mrr"])
    print("end-to-end tool checks:", hybrid_mcp_result["end_to_end_tool_checks"])

    out = {
        "n_questions": len(questions),
        "hit_at": HIT_AT,
        "k_retrieved": K_RETRIEVE,
        "methods": {
            "bm25_only": bm25_result,
            "vector_only": vector_result,
            "hybrid_direct": hybrid_direct_result,
            "hybrid_via_mcp_client": hybrid_mcp_result,
        },
        "note": (
            "bm25_only and vector_only call rag/retrieve.py directly -- only hybrid is "
            "exposed as the search_guidelines MCP tool, by design. hybrid_direct and "
            "hybrid_via_mcp_client should (and do) agree; hybrid_via_mcp_client is the "
            "one measured through the actual protocol a client like Claude Desktop uses."
        ),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "retrieval_metrics.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
