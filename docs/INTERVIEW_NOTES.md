# Interview Notes — AI Claims Investigator Copilot

Plain-English build log for the MCP/ML/RAG extension. Written phase by phase. This is
separate from the root `INTERVIEW_NOTES.md`, which covers the original SQL/Python analysis.

Required talking points this file must cover (tracked here as they're answered):
- [x] Why MCP instead of plain function calling — see Phase 0/4.
- [x] How data leakage was avoided in the model — Phase 2 (the `insured_hobbies` finding).
- [x] Why results on a 1,000-row dataset should be interpreted cautiously — Phase 2.
- [ ] Chunking strategy — Phase 3.
- [ ] Embedding model choice — Phase 3.
- [ ] Why hybrid search — Phase 3.
- [ ] How SQL injection/abuse is prevented — Phase 4.
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
