"""Shared embedding model for indexing and querying.

Model choice: sentence-transformers/all-MiniLM-L6-v2 (justified in
docs/INTERVIEW_NOTES.md Phase 3) -- 384 dimensions, ~90MB, runs on CPU in well under a
second per query, and is a long-standing, widely-benchmarked default for exactly this kind
of short-passage semantic search. Running fully locally (no embedding API call) matters
here because the MCP server (Phase 4) needs to answer `search_guidelines` queries quickly
and without an external network dependency.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]) -> np.ndarray:
    model = get_model()
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
