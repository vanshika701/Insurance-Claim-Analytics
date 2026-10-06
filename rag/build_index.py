"""Build the persistent ChromaDB vector index from docs/guidelines/*.pdf.

Run:  python -m rag.build_index
"""
from __future__ import annotations

import shutil

import chromadb

from copilot.config import CHROMA_DIR
from .chunk import chunk_pages
from .embeddings import embed
from .parse import load_all

COLLECTION_NAME = "fraud_guidelines"


def build() -> None:
    pages = load_all()
    if not pages:
        raise FileNotFoundError(
            "No PDFs with extractable text in docs/guidelines/. "
            "See docs/guidelines/README.md for what to add."
        )
    chunks = chunk_pages(pages)
    print(f"Parsed {len(pages)} pages -> {len(chunks)} chunks from "
          f"{len({c.file for c in chunks})} document(s).")

    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    texts = [c.text for c in chunks]
    print("Embedding chunks (sentence-transformers/all-MiniLM-L6-v2)...")
    vectors = embed(texts)

    collection.add(
        ids=[c.id for c in chunks],
        embeddings=vectors,
        documents=texts,
        metadatas=[{"file": c.file, "page": c.page} for c in chunks],
    )
    print(f"Indexed {collection.count()} chunks into {CHROMA_DIR} (collection '{COLLECTION_NAME}').")


if __name__ == "__main__":
    build()
