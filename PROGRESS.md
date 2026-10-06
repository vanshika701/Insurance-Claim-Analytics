# PROGRESS — AI Claims Investigator Copilot

Tracks the build described in the autonomous build brief (Phases 0–7). Update this file at
the end of every phase: tick items, add a "what was done" note, list blockers. **If this
session is ever resumed, read this file first and continue from the first unchecked phase.**

Legend: `[x]` done & verified by running code · `[~]` partially done / blocked · `[ ]` not started.

---

## Phase 0 — Audit and plan
- [x] Inspected repo: `db/schema.sql` (4 tables), `queries/analysis_queries.sql` + `run_queries.py`,
      `analysis/analysis.ipynb`, `ANALYSIS.md`, `.env` via python-dotenv.
- [x] Checked MySQL reachability with the existing `.env` — **reachable** (all 4 tables present,
      1,000 rows each). Built the dual-backend design anyway (Phase 1) so the copilot and eval
      don't hard-depend on a running MySQL server.
- [x] Checked the installed MCP Python SDK version before writing any server code: `mcp==2.3.0`.
      **Important finding:** in SDK v2, `FastMCP` was renamed to `MCPServer`
      (`from mcp.server.mcpserver import MCPServer`); the old `mcp.server.fastmcp` import path
      raises `ModuleNotFoundError` with a migration pointer. Verified the new class's `__init__`,
      `.tool()`, `.run()` signatures and the client-side `StdioServerParameters` /
      `ClientSession.call_tool` signatures by introspection, not memory. Noted in
      `docs/INTERVIEW_NOTES.md`.
- [x] Created `PROGRESS.md` (this file) and `docs/INTERVIEW_NOTES.md`.
- [x] Fixed `.gitignore`: added ignores for `.pytest_cache/`, the regenerable SQLite fallback DB,
      and the regenerable Chroma vector store. `.env` was already ignored with `.env.example`
      tracked (pre-existing from the original project) — confirmed, not re-done.
- [x] Pinned new dependencies in `requirements-copilot.txt` (separate from the original
      `requirements.txt`, which is untouched): mcp, sqlglot, xgboost, shap, chromadb,
      sentence-transformers, rank-bm25, pypdf, pytest, torch.

**Blockers:** none.

---

## Phase 1 — Data access layer
- [ ] `copilot/db.py` — read-only connection to MySQL or SQLite, backend chosen by `DB_BACKEND` env var.
- [ ] `copilot/build_sqlite.py` — builds the SQLite fallback from the already-cleaned `data/*.csv`.
- [ ] Data-validation check that detects the two known defects (incident before policy bind;
      negative `umbrella_limit`) and reports them.

## Phase 2 — Fraud risk model
- [ ] Feature set built from the joined tables, with every excluded/leaky column documented.
- [ ] Stratified 5-fold CV: logistic regression + XGBoost, precision/recall/F1/PR-AUC mean±std.
- [ ] Both compared against the "flag all Major Damage" rule baseline on the same folds.
- [ ] Decision threshold chosen deliberately and explained.
- [ ] SHAP explanations per claim.
- [ ] Artifacts saved to `models/`, metrics to `results/model_metrics.json`.

## Phase 3 — RAG over fraud guidelines
- [ ] `docs/guidelines/` populated (downloaded or listed as a blocker for the user).
- [ ] PDFs parsed with page numbers kept.
- [ ] Chunking strategy chosen and justified.
- [ ] Embeddings via local `sentence-transformers` into a persistent ChromaDB collection.
- [ ] Hybrid retrieval: BM25 + vector + Reciprocal Rank Fusion, citations with file + page.

## Phase 4 — MCP server
- [ ] `mcp_server/server.py` using the SDK's `MCPServer` (the current name for `FastMCP`) exposing
      `get_schema`, `run_query` (guarded read-only SQL), `score_claim`, `search_guidelines`.

## Phase 5 — Tests
- [ ] `tests/` pytest suite: SQL guardrails (incl. injection/bypass attempts), model
      loading/scoring, retrieval citations, each MCP tool. All passing.

## Phase 6 — Evaluation
- [ ] `eval/questions.json` — 20 real questions grounded in the actual guideline documents.
- [ ] `eval/run_eval.py` — MCP client over stdio; hit@5 and MRR.
- [ ] BM25-only vs vector-only vs hybrid comparison → `results/retrieval_metrics.json`.
- [ ] End-to-end check calling every tool through the MCP client.

## Phase 7 — Demo, docs, wrap-up
- [ ] Claude Desktop config snippet (macOS + Windows).
- [ ] `docs/DEMO_SCRIPT.md` — 3 demo prompts.
- [ ] `README.md` — new Copilot section (Mermaid architecture diagram, setup, real results),
      existing analysis content left intact.
- [ ] `docs/RESUME_BULLETS.md` — bullets built only from `results/` numbers.
- [ ] Final PROGRESS.md update + final chat summary.

---

## Running log of chat updates

(Appended after each phase, newest last.)
