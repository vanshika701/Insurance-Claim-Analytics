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
