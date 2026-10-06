"""RAG (retrieval-augmented generation) over public insurance-fraud guideline PDFs.

Pipeline: rag/parse.py (PDF -> per-page text) -> rag/chunk.py (page text -> cited chunks)
-> rag/build_index.py (chunks -> embeddings -> persistent ChromaDB) -> rag/retrieve.py
(BM25 + vector + Reciprocal Rank Fusion, every result cited by file + page).
"""
