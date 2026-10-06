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
- [x] `copilot/db.py` — read-only connection to MySQL or SQLite, backend chosen by `DB_BACKEND` env var.
- [x] `copilot/build_sqlite.py` + `db/schema_sqlite.sql` — builds the SQLite fallback
      (`data/claims.db`, gitignored/regenerable) from the already-cleaned `data/*.csv`.
- [x] `copilot/validate.py` — detects both known defects and reports them. **Verified
      output:** 1 incident-before-bind row (policy 794731, incident 579, flagged — not
      repaired, by design) and 1 negative `umbrella_limit` in the raw CSV (policy 526039,
      -1,000,000), confirmed repaired to NULL in the loaded DB.
- [x] Ran `copilot/db.py` and `copilot/validate.py` against **both** `DB_BACKEND=mysql` and
      `DB_BACKEND=sqlite` — identical row counts (1000/1000/1000/1000) and identical
      validation findings on both.

**Blockers:** none.

## Phase 2 — Fraud risk model
- [x] `copilot/features.py` — feature set + `EXCLUDED_COLUMNS` documenting every exclusion.
- [x] Stratified 5-fold CV (`copilot/train_model.py`): logistic regression + XGBoost.
      **Real results:** baseline (Major Damage rule) precision 0.608±0.048 / recall
      0.676±0.074 / F1 **0.637±0.041**; logistic precision 0.525±0.053 / recall
      0.680±0.045 / F1 0.591±0.041; XGBoost precision 0.558±0.025 / recall 0.619±0.059 /
      F1 0.585±0.029. **Neither model beats the baseline** (reported honestly).
- [x] Threshold selection: at the baseline's recall (67.6%), XGBoost's precision is 51.5%
      vs the baseline's 60.8% — `beats_baseline: false`.
- [x] Major finding while building features: `insured_hobbies` ('chess' 82.6% fraud n=46,
      'cross-fit' 74.3% n=35 vs ≤30% elsewhere) is a near-certain dataset artifact.
      Excluded from the deployed model; a sensitivity run confirms it alone pushes
      ROC-AUC from 0.76 → 0.864. Documented in `features.py` and `model_metrics.json`.
- [x] SHAP: global importance (top feature: `incident_severity_Major Damage`, 0.856,
      dwarfing everything else) + per-claim explanation via `copilot/score.py`
      (tested on claim_id=1 and a missing id, on both DB backends).
- [x] Artifacts saved: `models/xgboost_pipeline.joblib`, `models/model_config.json`,
      `results/model_metrics.json`.

**Blockers:** none.

## Phase 3 — RAG over fraud guidelines
- [x] `docs/guidelines/` populated with 2 real, substantive public PDFs: IRDAI (India)
      *Insurance Fraud Monitoring Framework Guidelines, 2025* (13 pages) and California
      DOI Fraud Division *SIU Annual Report* sample (20 pages) → 64 chunks total.
      NAIC's `content.naic.org` is blocked by a Cloudflare challenge for non-browser
      clients (confirmed with curl AND WebFetch) — listed as an optional manual add in
      `docs/guidelines/README.md`, not a blocker.
- [x] `rag/parse.py` — PDFs parsed per-page with page numbers kept.
- [x] `rag/chunk.py` — chunking never crosses a page boundary (exact citations); ~800
      char target / ~150 overlap. Justified in docs/INTERVIEW_NOTES.md.
- [x] `rag/embeddings.py` + `rag/build_index.py` — local `sentence-transformers/all-MiniLM-L6-v2`
      (384-dim), persistent ChromaDB collection at `docs/guidelines/chroma/` (gitignored,
      regenerable via `python -m rag.build_index`).
- [x] `rag/retrieve.py` — BM25 (rank_bm25) + vector (Chroma) + Reciprocal Rank Fusion.
      Every result carries `{file, page}`. Verified with a real query
      ("what must a board approved anti-fraud policy include") — top hit correctly
      IRDAI p.3, the Risk Management Committee clause.

**Blockers:** none (NAIC PDFs are an optional nice-to-have, not required).

## Phase 4 — MCP server
- [x] `mcp_server/server.py` using the SDK's `MCPServer` (imported as `FastMCP`) exposing
      `get_schema`, `run_query`, `score_claim`, `search_guidelines`, with clear tool
      docstrings for LLM use.
- [x] `mcp_server/sql_guard.py` — AST-based guard (sqlglot): single statement only,
      SELECT/UNION/INTERSECT/EXCEPT root only, forbidden-function walk, LIMIT<=100
      enforced, executes the AST's regenerated SQL (not the caller's raw text), 5s
      wall-clock timeout. **Verified: 20/20 adversarial + legitimate test cases behaved
      as expected** (injection via `;`, comment-trick, UPDATE/DELETE/DROP/ATTACH/PRAGMA,
      LOAD_FILE/SLEEP, oversized LIMIT — all blocked; plain SELECT, LIMIT, UNION, CTE,
      inline comment — all allowed).
- [x] **Found and fixed a real segfault**: XGBoost+SHAP and sentence-transformers/torch
      crash (SIGSEGV) when both execute native code in the same process (use-order, not
      import-order — confirmed by bisection; `KMP_DUPLICATE_LIB_OK=TRUE` did NOT fix it).
      Fixed by isolating `score_claim` in a subprocess. Documented in detail in
      docs/INTERVIEW_NOTES.md Phase 4 as the hardest bug of the build.
- [x] Verified end-to-end: all 4 tools called directly as functions in one process
      (including score_claim run after search_guidelines had already loaded torch — the
      exact scenario that used to crash), AND a real MCP client connecting over stdio to
      the server as a subprocess, `list_tools()` returning all 4, `call_tool("get_schema")`
      returning a correct result.

**Blockers:** none.

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
