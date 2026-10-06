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
- [x] `tests/test_sql_guard.py` — 19 cases (13 block, 6 allow) covering stacked statements,
      comment-hidden statements, every blocked DDL/DML type, ATTACH, PRAGMA, forbidden
      functions (incl. hidden in a UNION branch / subquery), oversized LIMIT, empty/garbage
      input, plus legitimate SELECT/LIMIT/UNION/CTE/join/comment cases, plus a reparse
      check that the guard's own executed output is still exactly one SELECT.
- [x] `tests/test_model.py` — artifacts exist, config shape, the "baseline not beaten"
      finding is pinned (fails loudly if a future change silently claims otherwise),
      scoring a known + missing claim via the same subprocess path the MCP server uses.
- [x] `tests/test_retrieval.py` — BM25/vector/hybrid all return valid {file,page}
      citations against real tracked PDFs; hybrid results are a subset of the union of
      its two inputs; k is respected.
- [x] `tests/test_mcp_tools.py` — all 4 tools called directly, plus **one real MCP
      client-over-stdio integration test** (server launched as a subprocess, `list_tools`,
      `call_tool`) -- the same protocol path Phase 6 and Claude Desktop use.
- [x] **47/47 tests pass**, run together in one pytest session (`pytest tests/ -q`) --
      including the model (XGBoost/SHAP, subprocess-isolated) and retrieval
      (sentence-transformers/torch, in-process) tests side by side, the exact combination
      that used to segfault before the Phase 4 fix.
- [x] Caught and fixed one incorrect claim during test-writing: a test asserted the SQL
      guard "strips comments" from the executed query; it doesn't (sqlglot legitimately
      preserves harmless comments) — fixed the test to check the property that actually
      matters (the executed SQL reparses as exactly one SELECT) and corrected the same
      incorrect claim in `sql_guard.py`'s docstring and `docs/INTERVIEW_NOTES.md`.

**Blockers:** none.

## Phase 6 — Evaluation
- [x] `eval/questions.json` — 20 questions, each hand-written from the actual PDF text
      (13 from IRDAI, 7 from CA DOI SIU report), each with an exact `{file, page}` and an
      `answer_hint` for a human reviewer.
- [x] `eval/run_eval.py` — connects to the MCP server as a real MCP client over stdio,
      calls `search_guidelines` for every question (hybrid, via the actual protocol path),
      and separately runs an end-to-end check calling `get_schema`, `run_query` (valid +
      a blocked injection attempt), and `score_claim` through the same client session.
      **All 4 tool checks passed.**
- [x] **Real results** (`results/retrieval_metrics.json`, hit@5 / MRR over 20 questions,
      top-10 retrieved):

      | Method | hit@5 | MRR |
      |---|---|---|
      | BM25-only | **1.00** | **0.892** |
      | Vector-only | 0.85 | 0.708 |
      | Hybrid (direct call) | 0.95 | 0.811 |
      | Hybrid (via MCP client) | 0.95 | 0.811 (matches direct exactly) |

      **Honest finding: BM25-only actually beat hybrid on this question set.** Hybrid
      recovered 2 of vector-only's 3 misses (questions 7 and 16), so it's not strictly
      worse than vector-only — but it didn't beat pure BM25 here. Most plausible reason,
      documented rather than hidden: these 20 questions were hand-written while reading
      the source pages, so they reuse a lot of the documents' own vocabulary — exactly
      the condition where lexical search has the advantage and semantic search's
      paraphrase-robustness doesn't get exercised. Noted as a limitation of a small,
      hand-authored eval set, not as "hybrid search doesn't work."

**Blockers:** none.

## Phase 7 — Demo, docs, wrap-up
- [x] `docs/DEMO_SCRIPT.md` — 3 demo prompts (per-claim investigation, weekly triage,
      regulatory lookup) + the Claude Desktop config snippet for macOS and Windows
      (verified the venv's python path, `cwd`-based module resolution works because
      `copilot/config.py` resolves `PROJECT_ROOT` from `__file__`, not cwd).
- [x] `README.md` — new "AI Claims Investigator Copilot" section added (Mermaid
      architecture diagram, setup commands, real results tables cross-checked against
      `results/model_metrics.json` and `results/retrieval_metrics.json`, limitations,
      extension layout). Existing analysis content above it is untouched.
- [x] `docs/RESUME_BULLETS.md` — 4 bullets, every number traced to a source
      (`results/*.json`, test counts, query/tool counts) in a table in that file.
- [x] Final PROGRESS.md update (this) + final chat summary sent.

**Blockers:** none. **All 7 phases complete.**

---

## Running log of chat updates

(Appended after each phase, newest last.)

- Phase 0+1: repo audited, MySQL confirmed reachable, MCP SDK v2 rename (FastMCP→MCPServer)
  caught before writing server code, dual-backend data access layer built and verified
  identical on MySQL/SQLite, 2 known defects detected and reported.
- Phase 2: 5-fold CV fraud model (logistic + XGBoost) honestly does not beat the "flag all
  Major Damage" baseline (F1 0.585-0.591 vs 0.637); caught a real dataset leak
  (`insured_hobbies`) via a sensitivity check and excluded it from the deployed model;
  SHAP wired up globally and per-claim.
- Phase 3: RAG built on 2 real public guideline PDFs (NAIC blocked by Cloudflare,
  documented as optional); page-bounded chunking, local embeddings, hybrid BM25+vector+RRF
  retrieval verified with real citations.
- Phase 4: MCP server with 4 tools shipped; AST-based SQL guard verified against 19
  adversarial cases; found and fixed a real SIGSEGV (XGBoost/SHAP vs torch in one process)
  via subprocess isolation -- the hardest bug of the build.
- Phase 5: 47/47 pytest tests pass together, including the segfault-prone combination
  side by side; caught and corrected an inaccurate claim in a test and in two docs while
  writing it.
- Phase 6: real MCP-client evaluation -- BM25-only actually beat hybrid on the 20-question
  set (honestly reported, with the likely reason: source-vocabulary-biased questions);
  full tool end-to-end check passed.
- Phase 7: demo script, Claude Desktop config, README Copilot section, and resume bullets
  shipped, all built only from real measured numbers. Build complete.
