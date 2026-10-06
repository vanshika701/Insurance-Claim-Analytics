"""Hybrid retrieval over the guideline chunks: BM25 (lexical) + vector (semantic),
combined with Reciprocal Rank Fusion. Every result carries a file + page citation.

Why hybrid (full rationale in docs/INTERVIEW_NOTES.md Phase 3): BM25 is strong on exact
terms an investigator would actually type -- form numbers, section references, defined
terms like "SIU" -- that an embedding can blur together with similar-meaning text. Vector
search is strong on paraphrase -- a query that describes a concept without using the
guideline's exact wording. A 64-chunk corpus from 2 regulatory documents has both kinds of
query, so combining them (via RRF, which needs no score normalization between the two very
differently-scaled ranking methods) outperforms either alone -- measured in Phase 6.

Run:  python -m rag.retrieve "your query here"
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from functools import lru_cache

import chromadb
from rank_bm25 import BM25Okapi

from copilot.config import CHROMA_DIR
from .build_index import COLLECTION_NAME
from .embeddings import embed

RRF_K = 60  # standard Reciprocal Rank Fusion constant (Cormack et al. 2009)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class Result:
    chunk_id: str
    file: str
    page: int
    text: str
    score: float


@lru_cache(maxsize=1)
def _collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(COLLECTION_NAME)


@lru_cache(maxsize=1)
def _corpus() -> tuple[list[str], list[str], list[dict]]:
    """All chunk ids/documents/metadatas, fetched once and cached -- the corpus is tiny
    (dozens of chunks), so rebuilding the BM25 index from it on first use is cheap and
    avoids maintaining a second persisted index alongside Chroma's."""
    got = _collection().get(include=["documents", "metadatas"])
    return got["ids"], got["documents"], got["metadatas"]


@lru_cache(maxsize=1)
def _bm25() -> BM25Okapi:
    _, docs, _ = _corpus()
    return BM25Okapi([_tokenize(d) for d in docs])


def vector_search(query: str, k: int = 5) -> list[Result]:
    vec = embed([query])
    got = _collection().query(query_embeddings=vec, n_results=k, include=["documents", "metadatas", "distances"])
    results = []
    for cid, doc, meta, dist in zip(got["ids"][0], got["documents"][0], got["metadatas"][0], got["distances"][0]):
        results.append(Result(chunk_id=cid, file=meta["file"], page=meta["page"], text=doc, score=1 - dist))
    return results


def bm25_search(query: str, k: int = 5) -> list[Result]:
    ids, docs, metas = _corpus()
    scores = _bm25().get_scores(_tokenize(query))
    order = sorted(range(len(ids)), key=lambda i: scores[i], reverse=True)[:k]
    return [
        Result(chunk_id=ids[i], file=metas[i]["file"], page=metas[i]["page"], text=docs[i], score=float(scores[i]))
        for i in order
        if scores[i] > 0
    ]


def hybrid_search(query: str, k: int = 5, pool: int = 20) -> list[Result]:
    """Reciprocal Rank Fusion of BM25 and vector rankings. Each method contributes
    1 / (RRF_K + rank) per chunk it returns (rank is 1-indexed); chunks found by both
    methods accumulate both contributions. This needs no score normalization, which
    matters because BM25 scores and cosine similarities live on unrelated scales."""
    bm25_hits = bm25_search(query, k=pool)
    vec_hits = vector_search(query, k=pool)

    rrf_scores: dict[str, float] = {}
    by_id: dict[str, Result] = {}
    for hits in (bm25_hits, vec_hits):
        for rank, hit in enumerate(hits, start=1):
            rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
            by_id[hit.chunk_id] = hit

    ranked = sorted(rrf_scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    return [
        Result(chunk_id=cid, file=by_id[cid].file, page=by_id[cid].page, text=by_id[cid].text, score=score)
        for cid, score in ranked
    ]


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "what must an insurer's anti-fraud plan include"
    print(f"query: {q!r}\n")
    for name, fn in (("BM25", bm25_search), ("Vector", vector_search), ("Hybrid (RRF)", hybrid_search)):
        print(f"--- {name} ---")
        for r in fn(q, k=3):
            snippet = r.text[:140].replace("\n", " ")
            print(f"  [{r.file} p.{r.page}] score={r.score:.4f}  {snippet}...")
        print()
