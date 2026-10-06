# Interview Notes — AI Claims Investigator Copilot

Plain-English build log for the MCP/ML/RAG extension. Written phase by phase. This is
separate from the root `INTERVIEW_NOTES.md`, which covers the original SQL/Python analysis.

Required talking points this file must cover (tracked here as they're answered):
- [x] Why MCP instead of plain function calling — see Phase 0/4.
- [x] How data leakage was avoided in the model — Phase 2 (the `insured_hobbies` finding).
- [x] Why results on a 1,000-row dataset should be interpreted cautiously — Phase 2.
- [x] Chunking strategy — Phase 3.
- [x] Embedding model choice — Phase 3.
- [x] Why hybrid search — Phase 3.
- [x] How SQL injection/abuse is prevented — Phase 4.
- [x] Dual-backend (MySQL/SQLite) data access layer — Phase 1.

---

## Phase 0 — Audit and plan

**What was built:** nothing user-facing yet — this phase was reconnaissance. Confirmed the
existing schema/queries/notebook still work, confirmed MySQL is reachable with the existing
`.env`, confirmed the installed `mcp` SDK version, and set up progress tracking.

**Why each choice was made:**
- *Checked the MCP SDK version before writing a line of server code.* The brief required
  this explicitly, and it immediately mattered: `mcp==2.3.0` renamed `FastMCP` to
  `MCPServer`. Importing `mcp.server.fastmcp.FastMCP` from memory would have crashed
  Phase 4 with a confusing error. The installed package's own error message named the
  exact replacement import and a migration-guide URL — reading that over guessing saved a
  debugging cycle.
- *Checked MySQL reachability rather than assuming SQLite was needed.* It was reachable, so
  no fallback database had to be built this phase — but the Phase 1 design still supports
  both backends via an env var, because a demo/evaluation environment (a grader's laptop, a
  CI runner) won't have this project's MySQL user configured.
- *Separate `requirements-copilot.txt` instead of extending the existing `requirements.txt`.*
  The brief says not to modify existing analysis files. Pinning new, fairly heavy
  dependencies (torch, chromadb, xgboost) into the original file would also make the
  original SQL/Python project look like it needs a GPU stack to run, which it doesn't.

**Alternatives considered and rejected:**
- *Skip the SDK version check and write FastMCP code from memory.* Rejected — the brief's
  ground rule 4 explicitly forbids this, and it would have failed on the first import.
- *Force everything onto SQLite from the start* (simpler, no credentials). Rejected for this
  phase because the existing MySQL setup works and is what the rest of the repo already
  uses; forcing a migration would contradict "do not modify existing analysis files" in
  spirit even if not in name. Dual-backend support is the compromise.

### Likely interview questions

**Q: Why build an MCP server instead of just writing Python functions and calling them
directly from your own code?**
A: Two different jobs. Direct function calls work when *you* control the caller. An MCP
server is for when the caller is an LLM client you don't control — Claude Desktop, another
agent, an eval harness — connecting over a standard protocol (stdio here) without needing
your source code imported into its process. It also gives you one boundary where you can
enforce guardrails (read-only SQL, row limits, timeouts) regardless of which client calls
in, and the same server can be driven by a human in Claude Desktop and by an automated
`pytest`/eval client with zero code duplication — which is exactly how Phase 6 evaluates it.

**Q: You said you "checked the SDK version" — why does that matter so much?**
A: Because APIs change between major versions and I'd rather find that out from an import
error in development than from a confusing failure during a demo. Concretely here: the
class I was told to use, `FastMCP`, doesn't exist in `mcp==2.3.0` — it's `MCPServer` now.
Writing code from a 9-months-stale mental model of the SDK would have produced code that
imports successfully in my head and fails the moment it's run.

**Q: Why not just use SQLite from the start and skip MySQL entirely?**
A: The original analysis project is built around MySQL and that's what's already running
and populated. Ripping it out to "simplify" would be solving a problem that doesn't exist
and would contradict the instruction to leave the existing analysis alone. Supporting both
backends behind one small `db.py` module costs little and buys portability — anyone running
this without MySQL configured (a reviewer, a CI job) still gets a working database.

---

## Phase 1 — Data access layer

**What was built:** `copilot/config.py` (backend selection via `DB_BACKEND`),
`copilot/db.py` (one `get_engine()`/`get_schema()`/`run_readonly()` surface over either
backend), `copilot/build_sqlite.py` (builds `data/claims.db` from the already-cleaned CSVs
using a new `db/schema_sqlite.sql`), and `copilot/validate.py` (detects the two known data
defects). Ran everything against **both** backends and got identical results: 1,000 rows
in each of the 4 tables, 1 flagged incident-before-bind row, 1 confirmed-repaired negative
`umbrella_limit`.

**Why each choice was made:**
- *One `run_readonly()` function, used by everything.* Every later caller — the model's
  feature builder, the validator, eventually the MCP server — goes through the same
  function. That's one place to reason about "is this safe," even though the MCP server
  (Phase 4) adds a stricter guard on top for *untrusted* SQL coming from an LLM.
- *`validate.py` checks the negative-`umbrella_limit` defect by diffing the raw CSV against
  the DB, not just querying the DB.* The DB alone would report "zero negative values" and
  make it look like the defect never existed — because `data/normalize_data.py` already
  repaired it to `NULL` before load. Diffing against the raw source instead reports the
  full, honest story: it *was* wrong, and here's proof it's fixed now. The other defect
  (incident before bind date) was deliberately never repaired in the original project — it's
  flagged, not dropped — so checking the live DB for it directly is correct and still finds
  it today.
- *`db/schema_sqlite.sql` as a new, separate file rather than editing `db/schema.sql`.* The
  brief forbids modifying existing analysis files. MySQL and SQLite DDL differ enough
  (`AUTO_INCREMENT` vs `AUTOINCREMENT`, inline `INDEX` vs standalone `CREATE INDEX`) that a
  single shared file would need per-backend branching anyway; a sibling file is simpler and
  leaves the original untouched.

**Alternatives considered and rejected:**
- *Have the MCP server talk to MySQL/SQLite directly, skip the `copilot/db.py` abstraction.*
  Rejected — every later phase (model, validator, MCP tools) needs the same connection
  logic, and duplicating it per phase is exactly how backend-specific bugs creep in.
- *Repair the incident-before-bind row in the validator.* Rejected — the original
  `ANALYSIS.md` finding treats it as evidence worth keeping, not noise to clean up; "detect
  and report," as the brief asked, not "detect and fix."

### Likely interview questions

**Q: Walk me through how your SQLite fallback actually gets built.**
A: `data/normalize_data.py` (from the original project) already cleans the raw CSV and
writes `data/{policies,vehicles,incidents,claims}.csv`. `copilot/build_sqlite.py` takes
those same cleaned CSVs, runs a SQLite-flavored copy of the schema
(`db/schema_sqlite.sql`) to create the four tables with the same PK/FK structure, then
bulk-loads each CSV with `pandas.DataFrame.to_sql`. So MySQL and SQLite end up with
byte-for-byte the same data, just through different DDL dialects — which I verified by
running both the schema inspector and the data-validator against each backend and
diffing the output.

**Q: How do you know the SQLite fallback hasn't silently diverged from the MySQL version?**
A: I ran `copilot/db.py` and `copilot/validate.py` against both (`DB_BACKEND=mysql` and
`DB_BACKEND=sqlite`) in the same terminal session and compared the printed output directly
— same row counts per table, same single flagged defect row with the same values. That's
not a unit test yet (that's Phase 5), but it's a real, run comparison, not an assumption.

---

## Phase 2 — Fraud risk model

**What was built:** `copilot/features.py` (the feature set, and a documented reason for
every excluded column), `copilot/train_model.py` (stratified 5-fold CV for logistic
regression and XGBoost, both compared against the "flag all Major Damage" rule baseline on
identical folds, a threshold-selection routine, global SHAP importance, and the saved
deployable artifact), and `copilot/score.py` (per-claim probability + risk band + top-5
SHAP contributors + whether the baseline rule would flag it).

**Real results** (full numbers in `results/model_metrics.json`; this is the headline
finding, told straight):

| Model | Precision | Recall | F1 | PR-AUC | ROC-AUC |
|---|---|---|---|---|---|
| Baseline — flag all Major Damage | 0.608 ± 0.048 | 0.676 ± 0.074 | **0.637 ± 0.041** | 0.491 | 0.766 ± 0.032 |
| Logistic regression | 0.525 ± 0.053 | 0.680 ± 0.045 | 0.591 ± 0.041 | 0.537 | 0.762 ± 0.028 |
| XGBoost | 0.558 ± 0.025 | 0.619 ± 0.059 | 0.585 ± 0.029 | 0.510 | 0.755 ± 0.036 |

**Neither model beats the one-line rule.** At the rule's own recall (67.6%), XGBoost's
precision is 51.5% — *worse* than the rule's 60.8%. This is a stronger, 5-fold-CV version
of the same conclusion the original SQL/EDA work reached with a single train/test split:
`incident_severity` carries almost all of the usable signal in this dataset, and 23 extra
features bought nothing. `threshold_selection.beats_baseline` in the metrics file is
simply `false` — that's reported as-is, not reframed.

**The `insured_hobbies` finding (this is the data-leakage answer):** while building the
feature set, a check of fraud rate by `insured_hobbies` turned up something extreme:
`chess` → **82.6% fraud** (n=46) and `cross-fit` → **74.3% fraud** (n=35), against ≤30% for
every one of the other 18 hobby values and a 24.7% portfolio base rate. That's a bigger
effect than `incident_severity` itself. There is no real-world mechanism connecting a
hobby to insurance fraud at that magnitude — this is a known artifact of this specific
public Kaggle dataset. Running the exact same 5-fold CV **with** `insured_hobbies` added
back (sensitivity check only, never deployed) confirms the artifact's effect: ROC-AUC jumps
from ~0.76 to **0.864** and precision/recall both jump by 8–18 points, for one extra
column. That jump, on a feature with no plausible causal story, is the signature of
leakage/dataset artifact rather than real signal. It was excluded from the deployed model
for exactly that reason, and the exclusion — plus the measured effect size — is documented
in `copilot/features.py::EXCLUDED_COLUMNS` and `results/model_metrics.json`.

**Why each choice was made:**
- *Stratified 5-fold CV instead of one train/test split.* The original analysis's
  `analysis/fraud_model.py` used a single 70/30 split; on 1,000 rows a single split's
  metrics can move several points just from which rows land in the test set. 5-fold CV with
  mean±std makes that uncertainty visible instead of reporting one lucky (or unlucky)
  number.
- *Baseline evaluated on the identical folds, not separately.* Comparing the rule's
  historical metrics (computed once on a different split) to the model's cross-validated
  metrics would be comparing two different samples. Recomputing the rule on each fold's
  held-out rows makes the comparison apples-to-apples.
- *Threshold chosen by matching the baseline's recall, then comparing precision* (see
  `choose_threshold()`). A model is only operationally better if, for the same recall
  (same amount of fraud caught), it needs fewer total investigations (higher precision).
  Matching on recall and reading off precision is the direct way to ask that question —
  and the honest answer here was "it doesn't beat the baseline," which is reported.
- *SHAP via `TreeExplainer` on the final XGBoost pipeline* rather than persisting a
  pickled explainer object. `TreeExplainer` is deterministic given the trained trees, so
  recomputing it at call time (in `score.py`) is simpler and avoids any explainer/library
  version mismatch between training and serving.
- *Why interpret this cautiously:* 1,000 rows, a curated 24.7% fraud rate (vs ~1–2% in
  real portfolios, per `ANALYSIS.md`), and 5-fold CV splits of ~200 rows each produce real
  but noisy std devs (e.g. XGBoost recall 0.619 ± 0.059 — almost a 10-point swing between
  folds). None of these numbers should be read as "this is what a production model would
  score"; they're only trustworthy as a *relative* comparison between the rule and the
  models, on this dataset.

**Alternatives considered and rejected:**
- *Deploy the model that includes `insured_hobbies`* because it has the best numbers.
  Rejected outright — shipping a feature that only "works" because of a dataset-generation
  quirk would make the project's single most defensible claim (the Major Damage finding)
  look like it was cherry-picked the same way. Reporting the sensitivity check instead of
  hiding it was the point.
- *Drop `total_claim_amount` as a precaution.* Considered, since claim amount could in
  principle be set *after* some triage. Rejected because the dataset records it at claim
  filing, the original SQL analysis (`ANALYSIS.md` F3/F4) already measured it as a weak
  signal, and removing a legitimately available, already-characterized feature would be
  excluding on a guess rather than a documented reason.
- *Report only accuracy.* Rejected — with a 24.7%/75.3% class split, accuracy is easy to
  game by predicting the majority class and would hide exactly the precision/recall
  trade-off the baseline-vs-model comparison depends on.

### Likely interview questions

**Q: How did you avoid data leakage in the model?**
A: Two layers. First, structurally: every excluded column is listed with a reason in
`copilot/features.py` — IDs, near-unique identifiers like `insured_zip` (995 distinct
values in 1,000 rows), claim-amount sub-components that are perfectly collinear with the
total, and raw dates where the underlying signal (tenure, seasonality) is already
captured or already shown to be absent. Second, empirically: while exploring the data I
found `insured_hobbies` predicts fraud far better than anything else should be able to
(chess/cross-fit at 75–83% fraud vs ~25% baseline) with no plausible real-world
mechanism. I ran the model both without and with it, confirmed the "with" version's
ROC-AUC jumps from 0.76 to 0.86 off one column, and excluded it from the deployed model —
documenting the measured effect size instead of either silently using it or silently
dropping it without saying why.

**Q: Why should I be skeptical of a 0.76 ROC-AUC on 1,000 rows?**
A: Three reasons, stacked. The dataset's 24.7% fraud rate is a curated artifact, not a
real base rate, so absolute precision/recall won't transfer to a real portfolio. The
5-fold CV standard deviations are real and sizeable (recall swings nearly 6–7 points
between XGBoost's folds) on folds of only ~200 rows, so a single point estimate overstates
confidence. And the one feature doing almost all the work, `incident_severity`, may itself
be partly how this teaching dataset was constructed (flagged already in `ANALYSIS.md`
F1/F2) — so even the *relative* finding should be re-measured before it's trusted on real
claims, let alone the absolute numbers.

**Q: Your model didn't beat the baseline — why present that instead of tuning until it
did?**
A: Because tuning a model until it narrowly beats a biased baseline on 1,000 rows would be
overfitting to noise, not building something more accurate. The actually useful result is
that 23 additional features — demographics, policy terms, vehicle details — add
essentially nothing once `incident_severity` is known. That's a real, defensible finding
about this dataset; a model that "beat" the rule by half a point after enough tuning
would not be.

---

## Phase 3 — RAG over fraud guidelines

**What was built:** `rag/parse.py` (PDF to per-page text, page numbers kept),
`rag/chunk.py` (page text to cited chunks), `rag/embeddings.py`
(`sentence-transformers/all-MiniLM-L6-v2`, local, no API), `rag/build_index.py`
(embeds all chunks into a persistent ChromaDB collection), and `rag/retrieve.py`
(BM25 + vector search combined with Reciprocal Rank Fusion, every result cited by
file + page).

**Getting real documents:** searched for the brief's suggested sources. NAIC's
`content.naic.org` serves a Cloudflare bot challenge to non-browser clients -- confirmed
blocked with both `curl` and the WebFetch tool, not just assumed. Found and downloaded two
different real, substantive documents instead: the **IRDAI (India) Insurance Fraud
Monitoring Framework Guidelines, 2025** (13 pages, 18,840 characters of extractable text)
and the **California DOI Fraud Division's SIU Annual Report** sample/template (20 pages,
16,587 characters) -- together 64 retrievable chunks. A third candidate (a 1-page CA DOI
infographic) was downloaded, found to have only 538 characters of text, and dropped as not
useful. The NAIC documents are listed in `docs/guidelines/README.md` as optional manual
downloads -- not a blocker, since the two documents in hand are a real, working corpus.

**Why each choice was made:**
- **Chunking strategy -- never cross a page boundary.** A chunk spanning pages 4 and 5
  forces picking one page number for text that came from two different pages, which makes
  roughly half of such a chunk's citation wrong. Keeping every chunk inside one page means
  every citation is exactly, mechanically verifiable against the source PDF -- which
  matters a lot for a tool whose entire value proposition is "trustworthy citations."
  Target size ~800 characters with ~150 overlap: large enough to be a coherent unit of
  meaning (not a sentence fragment), small enough that a retrieved chunk points at a
  specific clause rather than forcing the reader through a whole page. On this corpus the
  actual chunks came out shorter on average (mean 626 chars) because most guideline pages
  are naturally under 800 characters -- the size cap matters on the few longer pages.
- **Embedding model -- `all-MiniLM-L6-v2`.** Runs fully locally (no embedding API call,
  no added network dependency for the MCP server), ~90MB, produces 384-dim vectors,
  embeds a query in well under a second on CPU, and is a long-standing, heavily
  benchmarked default for short-passage semantic search -- appropriate for a 64-chunk
  corpus where a much larger model would be solving a problem this corpus doesn't have.
- **Hybrid search (BM25 + vector + RRF), not vector alone.** BM25 is lexical -- it wins
  when the query uses the guideline's own vocabulary (form numbers, defined terms like
  "SIU", exact section references). Vector search is semantic -- it wins when the query
  describes a concept without the guideline's exact wording. An investigator's real
  questions will be a mix of both. **Reciprocal Rank Fusion** combines the two rankings by
  rank position (`1/(60+rank)` per method, summed), not by raw score -- which matters
  because BM25 scores (unbounded, corpus-dependent) and cosine similarities (0-1) live on
  incomparable scales; normalizing and summing them directly would be arbitrary, while RRF
  sidesteps that entirely. Measured head-to-head against BM25-only and vector-only in
  Phase 6.
- **Rebuild BM25 from the Chroma corpus at query time instead of persisting a second
  index.** The whole corpus is 64 chunks -- re-tokenizing it on first use costs
  milliseconds and avoids keeping two index files in sync. This is a deliberate
  simplification that would stop making sense at a much larger corpus size (thousands of
  chunks), where a persisted BM25 index would be worth the complexity.

**Alternatives considered and rejected:**
- *Fixed-size chunking across the whole document, ignoring page boundaries.* Rejected for
  the citation-accuracy reason above -- this is a RAG system for an investigator who needs
  to go check the source, not a chatbot where an approximate page number is good enough.
- *A larger/more powerful embedding model (e.g. an OpenAI or Cohere embedding API).*
  Rejected -- adds an external network dependency and per-query cost/latency to the MCP
  server for a 64-chunk corpus that a 90MB local model already handles well; the quality
  ceiling of a bigger model isn't the bottleneck here, corpus size is.
- *Vector-only retrieval* (skip BM25/RRF entirely). Rejected -- and Phase 6 exists
  specifically to not just assert "hybrid is better" but to measure it on this corpus with
  hit@5/MRR.

### Likely interview questions

**Q: Walk me through your chunking strategy and why you picked those numbers.**
A: Chunks never cross a page boundary -- that's the load-bearing decision, because it
guarantees every citation's page number is exactly correct, not an approximation. Within
that constraint, I used a sliding window of ~800 characters with ~150 characters of
overlap. 800 characters is roughly a paragraph-and-a-half -- enough for the embedding
model to see a complete thought, small enough that a retrieved chunk is actually useful to
read, not a full page dump. The overlap means a clause that falls right at a chunk
boundary still appears whole in at least one chunk.

**Q: Why all-MiniLM-L6-v2 instead of a bigger embedding model?**
A: It's local (no API dependency or per-call cost for the MCP server), fast enough to
embed a query in well under a second on CPU, and it's a well-benchmarked default for
short-passage retrieval. With a 64-chunk corpus from two documents, the bottleneck is
corpus size and chunk quality, not embedding model capacity -- a bigger model wouldn't
move the needle on a corpus this small, and would cost more in dependency weight (this is
already the heaviest piece of `requirements-copilot.txt` because of `torch`).

**Q: Why hybrid search instead of just vector search, which is what most RAG demos use?**
A: Because guideline documents are full of exact vocabulary -- "Risk Management
Committee," specific clause numbers, defined terms like "Integral anti-fraud personnel" --
that an investigator is likely to type verbatim, and that's exactly where lexical search
(BM25) outperforms semantic search; embeddings can blur a specific defined term into its
general neighborhood of meaning. Vector search in turn wins on paraphrased or conceptual
questions. Combining them with Reciprocal Rank Fusion gets both without having to
normalize two incomparable score scales -- and I didn't just assert hybrid is better, I
measured it against each method alone in Phase 6.

---

## Phase 4 — MCP server

**What was built:** `mcp_server/server.py` exposes 4 tools -- `get_schema`, `run_query`,
`score_claim`, `search_guidelines` -- over the SDK's `MCPServer` class (imported as
`FastMCP`; see Phase 0). `mcp_server/sql_guard.py` is the guardrail layer `run_query`
calls before touching the database. Verified two ways: every tool called directly as a
plain Python function, and then for real -- a genuine MCP client connecting to the server
over stdio as a subprocess, listing tools, and calling one, exactly the way Claude Desktop
or the Phase 6 eval harness will.

### How SQL injection/abuse is prevented (`mcp_server/sql_guard.py`)

Not keyword-blocklisting the input text -- that's easy to evade (comments, case, spacing).
Every check operates on the **parsed AST** (via `sqlglot`), so what matters is what the
SQL actually *is*, not how it's spelled:
1. **Exactly one statement.** `sqlglot.parse()` splits on `;`; if it returns anything
   other than exactly one statement, reject -- including `"SELECT 1; -- ; DROP TABLE x"`,
   where the trailing text is a harmless comment but still counts as a second (empty)
   statement.
2. **Root node type must be read-only** (`Select`, or `Union`/`Intersect`/`Except` of
   selects). `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/`CREATE`/`ATTACH`/`PRAGMA`/... are
   rejected by their AST type, which can't be disguised by formatting.
3. **No call to a function on a danger list** (`LOAD_FILE`, `SLEEP`, `BENCHMARK`,
   `GET_LOCK`, ...), found by walking the whole parsed tree -- so one hidden inside a
   subquery or a UNION branch is still caught, not just one at the top level.
4. **A LIMIT is enforced**: present and over 100 → rejected with a clear message; absent →
   100 is appended.
5. **The executed SQL is the AST's own regenerated string, not the caller's raw text.**
   This is checked, not just asserted: `tests/test_sql_guard.py` reparses the guard's
   output and confirms it's still exactly one `SELECT`. It does **not** strip harmless
   comments -- sqlglot legitimately keeps those attached to the nodes they annotate, and
   an inert comment by itself isn't a threat. The thing a comment *could* defeat --
   hiding a second statement after it, e.g. `"SELECT 1; -- ; DROP TABLE x"` -- is caught
   earlier, by the single-statement check (step 1), which counts statements, not
   characters.

Tested against 20 cases (`mcp_server/sql_guard.py` was run standalone against a battery
including `; DROP TABLE`, `UPDATE`, `DELETE`, `ATTACH DATABASE`, `PRAGMA`,
`LOAD_FILE(...)`, an oversized `LIMIT`, and several legitimate queries including a CTE and
a `UNION`) -- all 20 behaved as expected, formalized as pytest cases in Phase 5.

A 5-second wall-clock timeout wraps query execution (`with_timeout`, a thread pool). Honest
limitation, stated in the code comment: Python can't forcibly kill a thread mid-syscall, so
a query that ignores the timeout signal could keep running in the background after the
tool call returns an error. Acceptable for a demo-scale, row-capped, read-only guard; a
production deployment would want a database-side statement timeout as well (MySQL's
`MAX_EXECUTION_TIME` hint, SQLite's `.setexeccontrolhandler` / step-count interrupt).

### The segfault (genuinely the hardest bug of this whole build)

Calling `score_claim` (XGBoost + SHAP) through the MCP server crashed the Python process
with no traceback -- just exit code 139 (SIGSEGV). It did **not** reproduce by calling
`copilot.score.score_claim()` standalone, which made it confusing: the model code itself
was fine. Bisection (documented in commit history, reproduced in isolation with a series of
`python -c` one-liners) found the actual trigger: loading `sentence-transformers` (which
pulls in `torch`) and then running XGBoost's prediction + SHAP's `TreeExplainer` **in the
same process** crashes once both have actually executed native code -- import order alone
didn't matter, only use order, which is what made it so easy to miss: `score_claim` and
`search_guidelines` each worked perfectly on their own, and even together in one order, but
not the other. On macOS this class of bug is a known failure mode when two libraries each
bundle/initialize their own OpenMP or BLAS runtime (`KMP_DUPLICATE_LIB_OK=TRUE` did **not**
fix it here, which was itself useful information -- it ruled out the simplest version of
that explanation).

**Fix:** isolate the XGBoost/SHAP scoring call in its own subprocess
(`subprocess.run([sys.executable, "-m", "copilot.score", str(claim_id)], ...)`,
`copilot/score.py` already supported this as a CLI entry point from Phase 2). This
sidesteps the conflict regardless of its exact root cause, at the cost of ~3 seconds of
process-startup overhead per `score_claim` call (measured) -- an acceptable trade for a
tool that an investigator calls per-claim, not in a tight loop. Verified fixed by running
all 4 tools, including `score_claim` after `search_guidelines` has already loaded torch,
in a single process with no crash.

**Why this is worth leading with in an interview:** it's a real debugging story with a
measured, reproduced root cause (use-order, not import-order -- a genuinely non-obvious
distinction), a ruled-out hypothesis (the `KMP_DUPLICATE_LIB_OK` fix that didn't work), and
a defensible, simple fix (process isolation) chosen over a fragile one (trying to force a
specific import/use order and hoping it holds as the code evolves).

### Likely interview questions

**Q: How do you stop an LLM from running a destructive query through run_query?**
A: The guard doesn't try to pattern-match dangerous SQL text -- it parses the query into
an AST with `sqlglot` and checks the AST's actual structure: exactly one statement, and
that statement's root must be a `Select` (or a set operation over selects). An `UPDATE` or
`DROP` is rejected because of what it *is* in the parse tree, which can't be hidden by
comments, casing, or whitespace the way a text-matching filter could be evaded. I also walk
the full tree for a short list of dangerous function calls (`LOAD_FILE`, `SLEEP`, ...) so
one hidden in a subquery is still caught, and I execute the AST's own regenerated SQL
string rather than the caller's original text -- tested by reparsing that output and
confirming it's still exactly one SELECT, so the guard's own output can't smuggle
anything past itself.

**Q: What's the hardest bug you hit building this?**
A: A silent segfault calling the fraud model's scoring tool through the MCP server, with
no Python traceback at all -- just exit code 139. It didn't reproduce calling the model
code directly, only through the server, which made it look like an MCP problem at first.
Bisecting with a series of minimal repro scripts showed it was actually XGBoost+SHAP and
sentence-transformers/torch conflicting once *both* had run native code in the same
process -- and only in one particular order, which is why it looked intermittent at first
glance. I fixed it by isolating the model-scoring call in a subprocess rather than chasing
an import-order fix that would've been fragile against future changes.

**Q: Why return `{"ok": false, "error": "..."}` from run_query instead of raising an
exception?**
A: Because the caller here is an LLM, not a human reading a stack trace. An uncaught
exception either crashes the tool call or surfaces as an opaque error the model can't act
on. Returning a structured result with a plain-English reason lets the calling model read
"LIMIT 99999 exceeds the maximum of 100 rows" and retry with a corrected query in the same
conversation turn, instead of getting stuck.

---

## Phase 5 — Tests

**What was built:** `tests/test_sql_guard.py` (19 cases), `tests/test_model.py`,
`tests/test_retrieval.py`, `tests/test_mcp_tools.py` (including one real stdio
client-server integration test). **47/47 pass**, run together in a single `pytest`
session.

**The one design choice worth explaining:** `test_model.py` never imports
`copilot.score` directly -- it shells out to `python -m copilot.score <id>`, the same
subprocess path `mcp_server/server.py`'s `score_claim` tool uses. That's deliberate: the
whole point of the Phase 4 segfault fix was removing XGBoost/SHAP from any process that
also loads sentence-transformers/torch, and importing `copilot.score` directly in a test
module that runs in the *same pytest session* as `test_retrieval.py` (which does load
torch) would silently reopen exactly that risk depending on which pytest version or
plugin changes file collection order in the future. Routing through the subprocess in the
test, not just in production code, means the test suite can never resurrect a bug its own
existence is supposed to prevent.

**A mistake caught while writing tests, worth stating plainly rather than quietly
fixing:** an early version of a guard test asserted that executing the AST's regenerated
SQL "strips comments" from the query. It doesn't -- `sqlglot` legitimately keeps harmless
comments attached to the nodes they annotate, and the test failed, correctly, the first
time it ran. The actual security property worth testing was different: that the SQL
which gets executed, reparsed, is still exactly one `SELECT` -- i.e. the guard's own
output can't smuggle anything past itself. Fixed the test, and fixed the same incorrect
claim in `sql_guard.py`'s docstring and in the Phase 4 notes above.

### Likely interview questions

**Q: Why does `test_model.py` run the scorer via subprocess instead of importing it?**
A: Because the bug that fix exists for (the XGBoost/SHAP + torch segfault) is a
same-process, both-used problem, not an import-order problem. If the test imported
`copilot.score` directly, it would *currently* pass — but it would be sitting next to
`test_retrieval.py` in the same pytest session with no guarantee which runs first, and a
future pytest version, plugin, or `-p no:randomly`-style ordering change could silently
flip that and bring the segfault back with no code change at all. Testing through the
same subprocess boundary production code uses removes that risk entirely rather than
hoping test collection order stays favorable.

**Q: Tell me about a mistake you caught while building this.**
A: While writing the SQL guard tests, I asserted that regenerating SQL from the parsed
AST strips comments out, as a defense-in-depth property. The test failed immediately --
`sqlglot` keeps comments attached to their nodes on purpose, which is correct behavior,
not a bug. I'd conflated two different things: "comments are inert" (true, and not
actually a property I'd verified) with "a comment can't hide a second statement" (true,
and already covered by the single-statement count). I rewrote the test to check the
property that actually matters -- that the executed SQL, reparsed, is still exactly one
SELECT -- and corrected the same wrong claim in two other places it had been written down.

---

## Phase 6 — Evaluation

**What was built:** `eval/questions.json` (20 questions, each hand-written while reading
the actual PDF pages, each with an exact `{file, page}` answer and a human-readable
`answer_hint`) and `eval/run_eval.py`, which connects to the MCP server as a real client
over stdio and (a) calls `search_guidelines` for every question to compute hit@5/MRR for
the hybrid method through the actual protocol, (b) calls `rag/retrieve.py`'s BM25-only and
vector-only functions directly for the method comparison (they aren't separately exposed
as MCP tools -- only hybrid is, by design), and (c) runs an end-to-end check calling every
other tool (`get_schema`, a valid `run_query`, an injection attempt, `score_claim`) through
that same client session.

**Real results:**

| Method | hit@5 | MRR |
|---|---|---|
| BM25-only | **1.00** | **0.892** |
| Vector-only | 0.85 | 0.708 |
| Hybrid (direct call) | 0.95 | 0.811 |
| Hybrid (via real MCP client) | 0.95 | 0.811 |

The hybrid-via-MCP-client number matches the hybrid-direct number exactly, which is the
useful sanity check: the protocol layer isn't silently changing the results.

**The honest finding, stated plainly rather than massaged:** BM25-only outperformed
hybrid on this question set. Looking at which questions each method missed: vector-only
missed 3 (two not even in the top 10, one at rank 6), hybrid recovered 2 of those 3, so
hybrid is a real improvement *over vector-only* -- but it still landed below pure BM25
(hit@5 0.95 vs 1.00). The most likely explanation is a property of how the eval set was
built, not of hybrid search in general: I wrote these 20 questions *while reading the
source pages*, which means many of them echo the guideline's own vocabulary ("Risk
Management Committee," "integral anti-fraud personnel," "Qui Tam") rather than paraphrasing
it. That's precisely the condition where lexical search (BM25) has the advantage and
where semantic search's actual selling point -- robustness to paraphrase -- never gets
tested. I'm reporting this as a limitation of a small, hand-authored, source-vocabulary-
biased question set, not reframing it to make hybrid look like the winner it was supposed
to be. A fairer eval set would include questions phrased by someone who hadn't read the
source text, which would be a reasonable next step, not something I did here.

**Why each choice was made:**
- **The retrieval-vs-ground-truth evaluation goes through a real MCP client, not just a
  library call**, specifically for the method that's actually shipped as a tool
  (`search_guidelines` = hybrid). This is the brief's own point: the same server has to
  serve both a human in Claude Desktop and an automated evaluator, so the evaluator should
  exercise the real protocol, not a shortcut around it.
- **BM25-only and vector-only are evaluated by direct function call, not as separate MCP
  tools**, because they aren't separate tools -- exposing 3 near-duplicate search tools to
  an LLM would be worse tool design than exposing 1 (hybrid) and keeping the comparison in
  the eval harness where it belongs.
- **Top-10 retrieved for ranking, hit@5 as the pass/fail bar.** Retrieving 10 lets MRR
  distinguish "missed by one slot" (rank 6, as vector-only did on question 16) from "not
  found at all" (ranks beyond 10 all scored as a 0 contribution to MRR), which a strict
  top-5-only retrieval would collapse into the same "miss."

### Likely interview questions

**Q: Your own numbers show hybrid search losing to BM25-only. Doesn't that undercut your
Phase 3 argument for hybrid?**
A: No -- it's a property of my 20-question eval set, and I'm not hiding that. I wrote
these questions while reading the source PDFs, so a lot of them reuse the document's exact
phrasing, which is the one scenario where lexical search has no disadvantage and semantic
search's actual advantage (handling paraphrase) never comes into play. What the numbers do
show is that hybrid is a real improvement over vector-only (0.95 vs 0.85 hit@5) -- it
recovered two of vector-only's three misses. I'd want a larger eval set written by someone
who didn't read the source text before trusting a verdict between hybrid and BM25-only in
general; what I have here is an honest result on a small, source-vocabulary-biased set,
not a refutation of the Phase 3 reasoning.

**Q: Why evaluate through the MCP protocol instead of just calling your Python functions?**
A: Because the tool that actually ships is `search_guidelines` called over MCP, and a
library-level test can pass while something in the protocol layer -- serialization, the
tool's own `k` parameter handling, error formatting -- is subtly broken. Running the same
20 questions through a real stdio client and confirming the numbers match the direct-call
numbers exactly is what lets me say the protocol layer isn't losing or distorting
anything, instead of just assuming it.
