"""Chunk per-page text into retrieval units, each carrying an exact file + page citation.

Chunking strategy (justified in docs/INTERVIEW_NOTES.md Phase 3):
  - Chunks never cross a page boundary. A chunk that spanned pages 4 and 5 would force
    picking one page number for text that actually came from two, making the citation
    wrong roughly half the time. Keeping chunks inside one page means every citation is
    exactly verifiable against the source PDF.
  - Target size ~800 characters (~130-160 words) with ~150 characters of overlap between
    consecutive chunks on the same page. Large enough that each chunk is a coherent unit
    of meaning (not a fragment stranded mid-sentence), small enough that a retrieval hit
    points at a specific clause rather than dumping a whole page on the reader.
  - A page shorter than the chunk size becomes a single chunk -- most guideline-PDF pages
    in this corpus are well under 800 characters per page already (see rag/parse.py
    output), so the overlap/splitting logic mostly matters for the longer pages.
"""
from __future__ import annotations

from dataclasses import dataclass

from .parse import Page

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


@dataclass
class Chunk:
    id: str
    file: str
    page: int
    text: str


def _split_page(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def chunk_pages(pages: list[Page], size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        for i, piece in enumerate(_split_page(page.text, size, overlap)):
            chunks.append(
                Chunk(id=f"{page.file}::p{page.page}::c{i}", file=page.file, page=page.page, text=piece)
            )
    return chunks


if __name__ == "__main__":
    from .parse import load_all

    pages = load_all()
    chunks = chunk_pages(pages)
    lens = [len(c.text) for c in chunks]
    print(f"{len(pages)} pages -> {len(chunks)} chunks")
    print(f"chunk length: min={min(lens)} mean={sum(lens)/len(lens):.0f} max={max(lens)}")
    print("sample chunk:", chunks[0].id, "->", chunks[0].text[:120].replace("\n", " "))
