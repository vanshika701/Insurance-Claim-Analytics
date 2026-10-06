# EXPLANATION.md — Project Journal

A chronological log of what we analysed, what we found, and what got in the way.
Newest entries go at the bottom. Entries are never overwritten.

---

## 2026-08-31 — Project setup

**What we are building**
Insurance Claims Analytics: a synthetic insurance dataset (customers, agents, policies, claims, payouts)
loaded into SQL, analysed with business-focused SQL queries (window functions, CTEs, subqueries) and
Python (pandas, matplotlib/seaborn). Goal: demonstrate SQL + Python data-analysis skills for a
ZS Associates Business Technology Solutions Associate interview.

**Done this step**
- Added `.gitignore` (ignores `.env`, `__pycache__`, `.ipynb_checkpoints`, generated CSV/DB files,
  OS/editor cruft; keeps `charts/` tracked).
- Added `CLAUDE.md` defining the working agreement: keep the user in the loop after every step,
  maintain this journal continuously, and prompt for a GitHub push after every small feature.
- Added this `EXPLANATION.md`.

**Insights found**
- None yet (no data).

**Difficulties faced**
- None yet. Open question: whether a local MySQL server is available, or whether we fall back to
  SQLite for portability. To be decided with the user before the schema step.

**Decisions made**
- Charts will be committed intentionally (recruiter-facing); everything else regenerable is ignored.

**Next step**
- Confirm the database engine (MySQL vs SQLite) and credentials, then design `db/schema.sql`.

---

## 2026-08-31 — Data cleaning, normalization & load into MySQL

**What we are building**
Taking the real Kaggle "Auto Insurance Claims" dataset (`data/insurance_claims.csv`,
1,000 rows x 39 usable columns + 1 junk column) and turning one flat table into a
4-table relational schema in MySQL, so the SQL analysis has real joins to work with.

**Done this step**
- Environment: MySQL 9.2.0 (Homebrew) confirmed running. Created a dedicated database
  `insurance_claims` and a least-privilege app user `insurance_app` (password in
  git-ignored `.env`; `.env.example` documents the vars). Python `.venv` with
  pandas/numpy/matplotlib/seaborn/SQLAlchemy/mysql-connector/jupyter; `requirements.txt` pinned.
- `db/schema.sql` — 4 tables: `policies` (natural PK `policy_number`) → `vehicles`,
  `incidents` → `claims`, with FKs, NOT NULL constraints, and helpful indexes.
- `db/connection.py` — SQLAlchemy engine built from `.env`, no hardcoded creds.
- `data/normalize_data.py` — cleans, splits, validates, writes per-table CSVs, and loads MySQL.
- Ran it: all 4 tables loaded, **1,000 rows each**, PK/FK integrity verified.
- Dedicated git repo initialized in this folder.

**Insights found**
- **Fraud base rate = 24.7%** of claims (247 / 1,000) — high because this is a curated
  ML teaching dataset, not a random sample.
- **Incident severity is already a very strong fraud signal**: "Major Damage" incidents
  are fraud **60%** of the time (167/276), vs ~11% for "Minor Damage" (38/354) and
  ~13% for "Total Loss" (36/280). Something to dig into with SQL.
- `total_claim_amount` exactly equals `injury_claim + property_claim + vehicle_claim`
  for 100% of rows — usable as a data-quality assertion.
- All incidents fall in Jan–Mar 2015, so the "seasonal trend" query only spans 3 months.

**Difficulties faced**
- Missing values come in two flavors: literal `"?"` strings (collision_type 178,
  property_damage 360, police_report_available 343) **and** genuine NaN
  (authorities_contacted 91). Handled both → NULL; kept the rows.
- One row has a negative `umbrella_limit` (-1,000,000) — clearly a data-entry error.
  Set to NULL and made the column nullable rather than dropping the row.
- The raw CSV has a trailing empty `_c39` column from a stray delimiter — dropped.
- Relationships in this dataset are effectively 1:1 (one incident, one claim per
  policy). Modeled them as 1:many anyway to mirror a real insurer's system; noted
  the caveat in `schema.sql`.

**Decisions made**
- MySQL (not SQLite) — it was already running and is what the target role uses.
- Dedicated `insurance_app` user over root, for a cleaner story.
- Surrogate keys `vehicle_id` / `incident_id` / `claim_id` assigned in file order (1..N).

**Next step**
- Write `queries/analysis_queries.sql` — the 10 analytical queries (window functions,
  CTEs, subqueries) listed in the brief.

---

## 2026-08-31 — SQL analysis layer (10 queries)

**What we are analysing**
Ten business questions against the normalized schema, aimed at where fraud concentrates
and where it doesn't: severity/type, demographics, policy age, claim size, state, cost
mix, seasonality, vehicle make, and cumulative claim cost.

**Done this step**
- `queries/analysis_queries.sql` — 10 commented queries. Techniques used: CTEs (Q1–Q3, Q5,
  Q6, Q8, Q10), window functions `DENSE_RANK`/`RANK` (Q1, Q6), `NTILE` + `PERCENT_RANK`
  (Q5), `LAG` (Q8), `SUM() OVER` running totals + ratio-to-total (Q9, Q10), correlated
  subquery / scalar subquery (Q2, Q3), conditional ("pivot") aggregation (Q1, Q4), `HAVING`
  sample-size floors (Q1, Q2, Q9).
- `queries/run_queries.py` — splits the .sql file and prints every result as a table so a
  reviewer without a SQL client can see outputs. Supports `run_queries.py 3 6` to pick queries.
- Business findings written up as F1–F7 in [ANALYSIS.md](ANALYSIS.md).

**Insights found** (full detail in ANALYSIS.md)
- **Severity is almost the whole story.** "Major Damage" collisions run 58–63% fraud;
  everything else 6–13%. 28% of claims hold 68% of fraud.
- **Fraud is not inflated in dollars.** At equal severity, fraudulent and honest claims
  average within ~$120 of each other (Major/Minor). The fraud is in the incident, not the invoice.
- **Claim size is a weak filter.** Fraud rate is ~flat across the top 8 cost deciles.
- **Vehicle make has a real ~18-point gradient** (Mercedes 34% → Jeep 16%), likely confounded.
- **Weak/no signal:** policy age, state, demographics, seasonality — honest negative results.
- Cost mix (Q7) is remarkably uniform: `vehicle_claim` ≈ 72% of every claim regardless of type.

**Difficulties faced**
- First cut of Q3 used a per-state threshold of `0.5 × AVG(days_to_incident)`. Because
  `policy_bind_date` goes back to 1990 while all incidents are in early 2015, the average
  gap is ~3 years, so the "early" filter matched ~240 claims — useless. Reworked Q3 into
  fixed calendar buckets (0–90d / 91–365d / 1–3y / 3y+) with the young-policy cutoff as a
  tunable subquery.
- Q5 originally dumped all 100 top-decile claims. Reworked into a 10-row fraud-rate-by-decile
  summary with a running "share of all fraud captured" column — far more decision-useful.
- Q9's portfolio baseline was an unweighted mean of per-make rates; switched to
  `SUM(SUM(...)) OVER () / SUM(COUNT(*)) OVER ()` for a properly weighted 24.7%.
- MySQL rejects `LIMIT` inside some subqueries; kept thresholds as bare scalar subqueries.

**Decisions made**
- `run_queries.py` parses the .sql by the `-- Qn.` comment banners rather than maintaining a
  second copy of the queries — the .sql file stays the single source of truth.
- Kept honest "no signal" queries (Q2, Q3, Q6, Q8) in the set rather than dropping them;
  being able to say "I checked and it wasn't there" is itself interview-worthy.

**Next step**
- `analysis/analysis.ipynb` — pull these query results into pandas, build the charts, and
  do the z-score anomaly pass checked against the real `fraud_reported` label.

---

## 2026-08-31 — Python analysis notebook + charts

**What we are building**
`analysis/analysis.ipynb`: pulls the SQL results into pandas, renders 7 charts to
`charts/*.png`, and runs the z-score anomaly detector against ground truth.

**Done this step**
- Notebook with 7 figures: (1) fraud rate by severity×type, (2) by state, (3) claim-amount
  box plots fraud vs legit by severity, (4) by age bracket, (5) by vehicle make,
  (6) cumulative claim cost line, (7) z-score anomaly scatter vs fraud.
- The notebook reuses `queries/run_queries.split_statements` so chart data comes straight
  from `analysis_queries.sql` — no duplicated SQL.
- Chart styling follows a CVD-safe palette (blue = legitimate / normal, red = fraud /
  above-average), recessive grid, direct value labels, portfolio-average reference line.
- Z-score anomaly result: flags 4/1000 claims, precision 25% / recall 0.4% → written up as
  **F8** in ANALYSIS.md. Contrasted with a plain "flag all Major Damage" rule (61% / 68%).
- Executed end-to-end with `jupyter nbconvert --execute`; outputs committed in the .ipynb.
- `nbformat` + `nbconvert` added to `requirements.txt`.

**Insights found**
- The charts make F2–F6 visual; the standout is chart 3 — fraud and legit box plots sit
  almost on top of each other at every severity level.
- Chart 7 visually confirms F8: the 4 amount-anomaly rings are nowhere near the red (fraud) mass.

**Difficulties faced**
- First version of the anomaly scatter called `.astype("category").cat.codes` separately on
  the fraud and non-fraud subsets, so the two could map the same severity to different
  x-positions. Fixed by computing the categorical once and indexing it — this also silently
  corrected which severity the anomaly rings were drawn under.
- Legend in chart 7 overlapped a data point at the top-left; moved it below the axis.
- Jitter used an unseeded RNG (non-reproducible runs); switched to `np.random.default_rng(0)`.
- Python 3.14 + Homebrew MySQL: needed `mysql-connector-python` (pure-Python path) rather
  than `mysqlclient`; already handled in the connection helper.

**Decisions made**
- Charts exported as PNGs and committed (recruiter-facing, per `.gitignore` note).
- Kept the anomaly section deliberately simple and let the *evaluation against ground truth*
  be the interesting part, rather than reaching for a real ML model.

**Next step**
- Rewrite `README.md` from a brief into the real recruiter-facing README (problem statement,
  schema diagram, sample queries + output, key insights, how-to-run, dataset attribution).

---

## 2026-08-31 — README rewrite + git history

**What we are building**
The final deliverable polish: turning the project brief into a recruiter-facing `README.md`
and laying down an intentional, incremental commit history.

**Done this step**
- `README.md` rewritten: problem statement, dataset + normalization note, ASCII schema
  diagram + grain table, 4 sample queries with real output snippets, 7 numbered key
  insights (including the honest negatives and the failed z-score detector), 4 embedded
  charts, tech stack, step-by-step run instructions, repo layout, dataset attribution.
- All output numbers in the README cross-checked against actual query results.

**Insights found**
- Writing the README surfaced the project's real narrative: *one feature (incident
  severity) does almost all the work, and several intuitive features do none* — which is a
  more interesting story than "found some fraud patterns."

**Difficulties faced**
- None of substance. Kept the schema diagram as ASCII so it renders anywhere on GitHub
  without an image dependency.

**Decisions made**
- Commit history split into 5 logical commits (setup → schema/normalize/load → SQL →
  notebook/charts → README + journals) rather than one dump, so `git log` reads as a
  deliberate build.
- No GitHub remote added automatically — left for the user to create and push.

**Next step**
- Project complete. Optional follow-ups: a lightweight fraud-scoring model on incident
  features; wiring `run_queries.py` output into the README automatically.

---

## 2026-08-31 — Optional polish: model, interview notes, Makefile, fresh notebook run

**What we are building**
Four extras beyond the brief to make the repo interview-ready.

**Done this step**
- `analysis/fraud_model.py` — L2 logistic regression + depth-4 decision tree on incident/
  policy/vehicle features, stratified 70/30 split, evaluated against the "all Major Damage"
  baseline. Saves `charts/08_model_vs_baseline.png` (PR curve + confusion matrix).
- `INTERVIEW_NOTES.md` — 30-sec pitch, the normalization story, three query walk-throughs
  (incl. the Q3 CTE bug), the fraud narrative, the "did the model help" answer, "what I'd
  do with more data", a SQL-technique cheat-sheet, and likely gotcha questions.
- `Makefile` — `setup / db / load / queries / analyze / model / all / clean`.
- Re-ran the analysis notebook end-to-end from a clean state: executes, exit 0.
- `scikit-learn` added to `requirements.txt`; README updated (insight #7, tech stack,
  run steps, repo layout, chart 08).

**Insights found**
- **F9: the model ties the one-line rule.** Both models land at ROC-AUC ≈ 0.77, level with
  "flag every Major Damage claim." Largest logistic coefficient by far is Major Damage
  (1.9). The extra features barely move the needle — which is the same story the SQL told,
  now confirmed with a held-out test set. The model's only real edge is a tunable
  precision/recall threshold.
- Confusion matrix at threshold 0.5: 50 TP / 24 FN / 40 FP / 186 TN on 300 test claims.

**Difficulties faced**
- `OneHotEncoder` needed `min_frequency=15` — several `auto_model` / occupation values
  appear only a handful of times and would otherwise blow up the feature count and overfit.
- Had to be careful about label leakage: `incident_severity` is such a strong predictor
  that it's worth stating out loud it may be partly label-derived in this teaching dataset.
  Noted in F2, F9, and INTERVIEW_NOTES.

**Decisions made**
- Kept the model as a standalone script, not a notebook section — easier to run in CI /
  `make model` and it keeps the EDA notebook focused.
- Deliberately did not tune hyperparameters hard or try ensembles: the honest finding is
  "a simple model ties a one-liner," and chasing 0.01 AUC would obscure that.

**Next step**
- Project complete. Nothing outstanding.
