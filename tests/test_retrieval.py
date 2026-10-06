"""Retrieval tests: every result returns a citation, and hybrid search is sane relative
to its two component methods on this real corpus."""
from __future__ import annotations

from rag.retrieve import bm25_search, hybrid_search, vector_search

QUERY = "what must a board approved anti-fraud policy include"


def _assert_valid_citations(results) -> None:
    assert len(results) > 0
    for r in results:
        assert r.file.endswith(".pdf")
        assert r.page >= 1
        assert len(r.text) > 0


def test_bm25_returns_citations() -> None:
    _assert_valid_citations(bm25_search(QUERY, k=5))


def test_vector_returns_citations() -> None:
    _assert_valid_citations(vector_search(QUERY, k=5))


def test_hybrid_returns_citations() -> None:
    _assert_valid_citations(hybrid_search(QUERY, k=5))


def test_hybrid_result_is_a_union_of_its_inputs() -> None:
    """Every hybrid hit must have been returned by at least one of the two underlying
    methods -- RRF should never invent a result neither method found."""
    bm25_ids = {r.chunk_id for r in bm25_search(QUERY, k=20)}
    vec_ids = {r.chunk_id for r in vector_search(QUERY, k=20)}
    for r in hybrid_search(QUERY, k=5):
        assert r.chunk_id in bm25_ids or r.chunk_id in vec_ids


def test_citations_point_at_real_tracked_pdfs() -> None:
    from copilot.config import GUIDELINES_DIR

    known_files = {p.name for p in GUIDELINES_DIR.glob("*.pdf")}
    for r in hybrid_search(QUERY, k=5):
        assert r.file in known_files


def test_k_is_respected() -> None:
    assert len(hybrid_search(QUERY, k=3)) <= 3
    assert len(bm25_search(QUERY, k=2)) <= 2
