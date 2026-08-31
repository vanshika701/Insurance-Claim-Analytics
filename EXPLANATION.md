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
