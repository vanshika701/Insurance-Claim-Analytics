# PROJECT GUIDE — Understand This Project From Zero

This file assumes you know **nothing** about the project and walks you through every part in
plain language, so you can explain it confidently in an interview and survive follow-up
("cross") questions.

Read it top to bottom once. Then re-read Sections 9 and 10 the night before the interview.

---

## Table of contents

1. The 30-second version (say this first)
2. Why this project exists
3. What "insurance claims fraud" even means
4. The dataset — what it is and where it came from
5. The columns, explained in English
6. The big picture: what the project actually does (the pipeline)
7. Step 1 — Cleaning and **normalizing** the data
8. Step 2 — The database schema (the 4 tables)
9. Step 3 — Loading the data into MySQL
10. Step 4 — The 10 SQL queries, one by one
11. Step 5 — The Python analysis notebook (the charts)
12. Step 6 — The z-score "anomaly detection" (and why it failed)
13. Step 7 — The machine-learning models (logistic regression + decision tree)
14. The findings, in plain English (F1–F9)
15. The one story that ties it all together
16. SQL concepts glossary (CTE, window function, RANK, NTILE, LAG, etc.)
17. Every file in the repo and what it does
18. How to run the whole thing
19. **Cross-question bank** — hard questions + strong answers
20. Known weaknesses (be honest about these)

---

## 1. The 30-second version (say this first)

> "I took a real auto-insurance dataset from Kaggle — 1,000 claims in one flat table, with a
> real `fraud_reported` Yes/No label. I cleaned it, **normalized it into 4 related tables** in
> MySQL, and wrote 10 analytical SQL queries using window functions, CTEs, and subqueries to
> find where fraud concentrates. Then I did a Python analysis layer with charts and a couple
> of models to validate the findings.
>
> The headline result: **one field — incident severity — explains almost all the fraud.**
> Claims marked 'Major Damage' are fraudulent about 60% of the time versus roughly 11%
> everywhere else. That one category is 28% of all claims but contains 68% of all fraud.
> Several 'obvious' fraud signals — claim size, customer age, region, time of year — turned
> out to carry **no useful signal**, and I can show that with the queries."

That paragraph is the whole project. Everything below is detail to back it up.

---

## 2. Why this project exists

- **Goal:** a compact, resume-ready project that proves two skills — **SQL** (especially the
  harder parts: window functions, CTEs, subqueries) and **Python data analysis** (pandas,
  matplotlib/seaborn, a little scikit-learn).
- **Framing:** act like an insurance-company data analyst investigating claims fraud. Not
  building an app — building an *analysis*.
- **Why fraud?** It's a real, money-driven business problem with a clear yes/no outcome, so
  every finding can be checked against reality.

---

## 3. What "insurance claims fraud" even means

- You buy an **insurance policy** and pay a **premium** (a regular fee).
- When something bad happens (a crash, a theft), you file a **claim** — a request for the
  insurer to pay you.
- The insurer investigates and either **approves** or **denies** the claim, then makes a
  **payout**.
- **Claims fraud** = lying to get money you're not owed: staging an accident, exaggerating
  the damage, claiming for a pre-existing dent, inventing injuries, etc.
- Insurers can't investigate every claim deeply — it's too expensive and slow. So they need
  **triage**: quickly decide which claims look risky enough to investigate. This project is
  about finding the signals that make triage smart.

**Key jargon you might be asked:**
| Term | Plain meaning |
|---|---|
| Premium | The fee the customer pays for the policy |
| Deductible (`policy_deductable`) | Amount the customer pays out of pocket before insurance kicks in |
| CSL / `policy_csl` (e.g. "250/500") | "Combined Single Limits" — max the policy pays: \$250k per injured person / \$500k per accident |
| Umbrella limit | Extra liability coverage stacked on top of the normal policy limit |
| SIU | Special Investigations Unit — the fraud team inside an insurer |
| Loss ratio | Claims paid ÷ premiums collected. Above ~1.0 means the insurer is losing money on that group |
| Subrogation | Insurer recovering money from the at-fault party afterward (not in this dataset) |

---

## 4. The dataset — what it is and where it came from

- **Name:** "Auto Insurance Claims Data", uploaded by **Bunty Shah** on Kaggle.
- **Size:** 1,000 rows (each row = one claim), 39 useful columns + 1 junk column (`_c39`,
  created by a stray comma in the file).
- **Time span:** every incident happened between **1 January and 1 March 2015**. Policies
  were *bought* (bound) anywhere from 1990 to 2015.
- **The gold feature:** `fraud_reported` — `Y` or `N`. This is the **ground truth**: someone
  already determined whether each claim was fraud. That's rare and valuable — it means we can
  *measure* how good any fraud signal is, not just guess.
- **Fraud base rate:** 247 of 1,000 claims are fraud = **24.7%**.

### Important honesty point about the data

24.7% fraud is **absurdly high** for real insurance (real life is ~1–2%). This is a
**curated teaching dataset** — someone built it so that patterns would be findable. Some
demographic columns (`insured_occupation`, `insured_education_level`, `capital_gains`,
`capital_loss`, `insured_relationship`) look borrowed from the classic US Census "Adult"
dataset, i.e. bolted on synthetically.

**So:** treat every number as a *relative comparison* ("Major Damage is 5x riskier than
Minor"), never as a real-world forecast ("expect 60% fraud"). Say this out loud in the
interview — it shows maturity.

---

## 5. The columns, explained in English

The raw flat table has these 39 columns. Grouped by what they describe:

**About the customer / policy**
| Column | Meaning |
|---|---|
| `policy_number` | Unique ID for the policy (we use it as the primary key) |
| `months_as_customer` | How long they've been with the insurer |
| `age` | Customer age |
| `policy_bind_date` | Date the policy started |
| `policy_state` | State the policy is registered in (only OH, IL, IN appear) |
| `policy_csl` | Coverage limits, e.g. "250/500" |
| `policy_deductable` | Deductible amount |
| `policy_annual_premium` | Yearly fee |
| `umbrella_limit` | Extra liability coverage (one row is negative — a data error) |
| `insured_zip`, `insured_sex` | ZIP code, sex |
| `insured_education_level`, `insured_occupation` | Education, job |
| `insured_hobbies`, `insured_relationship` | Hobby, household relationship |
| `capital_gains`, `capital_loss` | Investment gains/losses of the insured |

**About the incident (the event)**
| Column | Meaning |
|---|---|
| `incident_date` | When it happened |
| `incident_type` | Multi-vehicle Collision / Single Vehicle Collision / Vehicle Theft / Parked Car |
| `collision_type` | Front / Rear / Side (or `?` if not a collision) |
| `incident_severity` | **Trivial / Minor / Major Damage / Total Loss** — the key field |
| `authorities_contacted` | Police / Fire / Ambulance / Other / none |
| `incident_state`, `incident_city`, `incident_location` | Where |
| `incident_hour_of_the_day` | 0–23 |
| `number_of_vehicles_involved` | Count |
| `property_damage` | YES / NO / `?` |
| `bodily_injuries` | Count of injured people |
| `witnesses` | Count |
| `police_report_available` | YES / NO / `?` |

**About the vehicle**
| Column | Meaning |
|---|---|
| `auto_make`, `auto_model`, `auto_year` | e.g. Mercedes / E400 / 2007 |

**About the money and the label**
| Column | Meaning |
|---|---|
| `total_claim_amount` | Total \$ claimed |
| `injury_claim`, `property_claim`, `vehicle_claim` | The 3 parts. They **always add up to** `total_claim_amount` (we verified: 100% of rows) |
| `fraud_reported` | **Y / N** — the answer we're studying |

---

## 6. The big picture: what the project actually does (the pipeline)

```
   Kaggle CSV (1 flat table, messy)
            │
            ▼
   [ data/normalize_data.py ]   ← clean + split into 4 tables + load
            │
            ▼
   MySQL database "insurance_claims"
   (policies, vehicles, incidents, claims)
            │
            ├──────────────► [ queries/analysis_queries.sql ]  ← 10 SQL queries
            │                       │  run via queries/run_queries.py
            │                       ▼
            │                 business findings → ANALYSIS.md (F1–F9)
            │
            ├──────────────► [ analysis/analysis.ipynb ]  ← pandas + 7 charts
            │                       + z-score anomaly check
            │
            └──────────────► [ analysis/fraud_model.py ]  ← logistic reg + decision tree
                                    (validation step, not a product)
```

Everything reads from the **same MySQL database**, so the SQL layer and the Python layer
agree with each other.

---

## 7. Step 1 — Cleaning and normalizing the data

File: [`data/normalize_data.py`](data/normalize_data.py)

### 7a. What "normalize" means (the interview definition)

**Normalization = organizing data into multiple related tables so each fact is stored
exactly once, with no repetition and no contradictions.**

The raw file is one giant table where, if a customer had two claims, all their policy
details would be copied on both rows. That's called an **un-normalized** or "flat" table.
Problems with flat tables:
- **Redundancy:** same info stored many times → wastes space.
- **Update anomalies:** change a customer's address on one row but forget another → the
  data now disagrees with itself.
- **Unclear structure:** you can't tell which columns describe the *person* vs the *event*.

**Normalizing** splits it into logical tables connected by **keys** (IDs). Here:
- everything about the **policy/person** → `policies` table
- everything about the **car** → `vehicles` table
- everything about the **event** → `incidents` table
- everything about the **money + fraud label** → `claims` table

This project's split is roughly **Third Normal Form (3NF)** — the standard target: every
non-key column depends on the key, the whole key, and nothing but the key.

### 7b. The cleaning steps (what the script does, in order)

1. **Fix column names:** the raw file has hyphens (`capital-gains`). Renamed to underscores
   (`capital_gains`) so SQL doesn't choke on them.
2. **Drop the junk column** `_c39` (all empty — caused by a trailing comma in the CSV).
3. **Handle missing values.** This dataset hides missing data as the string `"?"`:
   - `collision_type`: 178 `"?"`
   - `property_damage`: 360 `"?"`
   - `police_report_available`: 343 `"?"`
   - `authorities_contacted`: 91 genuine blanks
   All of these → proper `NULL`. **We kept the rows** — deleting 400+ rows would bias the
   analysis. A `?` in "collision type" often just means "this wasn't a collision" (it was a
   theft or parked-car incident), so it's *informative*, not garbage.
4. **Fix the bad `umbrella_limit`:** one row is `-1,000,000` (impossible). Set to `NULL`
   and made the column nullable.
5. **Parse dates** into real date types.
6. **Create surrogate keys:** the raw data has no ID for incidents, vehicles, or claims. We
   generate `incident_id`, `vehicle_id`, `claim_id` = 1, 2, 3, … in file order. ("Surrogate
   key" = an artificial ID we invent, as opposed to a "natural key" like `policy_number`
   that already exists in the data.)
7. **Split into the 4 tables** by picking the relevant columns for each.
8. **Validate before loading:**
   - `policy_number` is unique ✔
   - every `policy_number` in vehicles/incidents/claims exists in policies (no broken
     foreign keys) ✔
   - `injury_claim + property_claim + vehicle_claim == total_claim_amount` for every row ✔
     (this is a data-quality assertion — if it failed, something is wrong with the data)

### 7c. The honest caveat about the schema

In *this* dataset there is exactly **one incident and one claim per policy** — so the
relationships are all **1-to-1**. That makes the normalization a bit artificial (you could
argue it should stay one table).

**Why do it anyway?** Because a *real* insurer's database looks like this — one customer,
many policies; one policy, many claims over the years. Modeling it as 1-to-**many** makes
the SQL realistic (real joins, real `GROUP BY`) and it's a skill worth demonstrating. Just
be upfront that the current data doesn't exercise the "many" side.

---

## 8. Step 2 — The database schema (the 4 tables)

File: [`db/schema.sql`](db/schema.sql)

```
  policies                          vehicles
  --------                          --------
  policy_number (PK) ───────1:1────< policy_number (FK, UNIQUE)
  age, months_as_customer           vehicle_id (PK)
  policy_bind_date, policy_state     auto_make, auto_model, auto_year
  policy_csl, policy_deductable
  policy_annual_premium
  umbrella_limit (nullable)          incidents
  insured_sex / education /          ---------
    occupation / hobbies /     ┌───< policy_number (FK)
    relationship               │     incident_id (PK)
  capital_gains, capital_loss  │     incident_date, incident_type
                               │     collision_type (nullable)
  claims                       │     incident_severity  ★ the key field
  ------                       │     authorities_contacted (nullable)
  claim_id (PK)                │     incident_city / state / location
  policy_number (FK) ──────────┘     incident_hour_of_the_day
  incident_id (FK, UNIQUE) ────1:1──< number_of_vehicles_involved
  total_claim_amount                 property_damage (nullable)
  injury_claim / property_claim /    bodily_injuries, witnesses
    vehicle_claim                    police_report_available (nullable)
  fraud_reported (Y/N)  ★ the label
```

- **PK = Primary Key:** the column that uniquely identifies a row. `policies.policy_number`
  is a *natural* PK (it came with the data); the others are *surrogate* PKs we invented.
- **FK = Foreign Key:** a column that points to a PK in another table. `claims.incident_id`
  points to `incidents.incident_id`. The database *enforces* that you can't insert a claim
  for an incident that doesn't exist — that's **referential integrity**.
- **NOT NULL constraints:** on columns that must always have a value.
- **Indexes:** on the columns queries filter/join on (`policy_state`, `incident_severity`,
  `incident_date`, `fraud_reported`, `auto_make`) — an index is like a book's index, it
  makes lookups fast without scanning every row.
- **`UNIQUE` on the FKs** (`vehicles.policy_number`, `claims.incident_id`) — this is what
  encodes "1-to-1" in the current data.

---

## 9. Step 3 — Loading the data into MySQL

- Credentials live in a **`.env` file** (git-ignored, never committed). `db/connection.py`
  reads them and builds a **SQLAlchemy engine** (SQLAlchemy = a Python library that talks
  to databases; the "engine" is the connection object).
- `normalize_data.py` runs `schema.sql` (drops old tables, recreates them), then uses
  pandas' `DataFrame.to_sql()` to bulk-insert each table.
- After loading it **re-counts the rows in the database** (1,000 each) as a final check.
- A dedicated MySQL user `insurance_app` was created with privileges *only* on this one
  database — not using `root`. Small thing, but it's the "least privilege" principle and
  interviewers like to see it.

**Why MySQL and not Postgres/SQLite?** MySQL is what the target role uses and it was already
installed. The SQL here (CTEs, window functions) is ANSI-standard and would run on Postgres
with basically no changes.

---

## 10. Step 4 — The 10 SQL queries, one by one

File: [`queries/analysis_queries.sql`](queries/analysis_queries.sql).
Run them all with `python queries/run_queries.py` (it prints each result as a table).

**First, one trick used everywhere:** in MySQL, a condition like `fraud_reported = 'Y'`
evaluates to **1 or 0**. So:
- `SUM(fraud_reported = 'Y')` = **count** of fraud claims
- `AVG(fraud_reported = 'Y')` = **fraction** that are fraud (multiply by 100 → percentage)

That's why you see `ROUND(100.0 * AVG(fraud_reported = 'Y'), 1)` — it's "fraud rate %".

---

### Q1 — Fraud rate by incident severity × incident type, ranked

- **Business question:** which *combination* of severity and incident type has the most
  fraud?
- **SQL techniques:** a **CTE** (`WITH combo AS (...)`) to compute the rates, `HAVING
  COUNT(*) >= 10` to throw away tiny groups, then **`DENSE_RANK() OVER (ORDER BY
  fraud_rate_pct DESC)`** to rank them.
- **Result:**
  | Severity × Type | Claims | Fraud rate |
  |---|---|---|
  | Major Damage · Single Vehicle Collision | 132 | **62.9%** |
  | Major Damage · Multi-vehicle Collision | 144 | **58.3%** |
  | Total Loss · Multi-vehicle Collision | 145 | 13.1% |
  | … everything else … | | 6–13% |
- **Takeaway:** the two "Major Damage" rows tower over everything. Fraud isn't spread out —
  it's concentrated.

---

### Q2 — Fraud rate by age bracket × education level

- **Business question:** are certain age/education groups more fraud-prone?
- **SQL techniques:** **`CASE WHEN`** to bucket `age` into bands (<25, 25–34, …); a second
  CTE + **`CROSS JOIN`** to attach the overall average so each row shows "points above/below
  average"; `HAVING COUNT(*) >= 15` for sample size.
- **Result:** no stable pattern. The "worst" cell (55+ with an "MD" education, 60% fraud)
  is based on only **15 claims** — that's noise, not signal.
- **Takeaway:** demographics don't help here. (Honest negative result.)

---

### Q3 — Does filing a claim soon after buying the policy predict fraud?

- **Business question:** "claim filed right after the policy started" is a classic fraud
  red flag. Is it true here?
- **SQL techniques:** CTE computing **`DATEDIFF(incident_date, policy_bind_date)`**, then
  `CASE WHEN` buckets (0–90 days, 91–365 days, 1–3 years, 3+ years), plus a bucket for the
  impossible case (`days < 0`).
- **Result:**
  | Time from policy start to incident | Claims | Fraud rate |
  |---|---|---|
  | Incident BEFORE policy started (data error!) | 1 | 0% |
  | 0–90 days | 7 | 14.3% |
  | 91–365 days | 36 | 27.8% |
  | 1–3 years | 70 | 28.6% |
  | 3+ years | 886 | 24.4% |
- **Takeaway:** barely a blip (27.8% vs 24.4%) and on tiny samples. The "new policy" red
  flag does **not** show up in this data. Also caught a data bug — one incident is dated
  *before* its policy existed.
- **Story point:** the *first* version of this query defined "early" as "less than half the
  state's average gap." But policies were bought as far back as 1990 while all incidents are
  in early 2015, so the average gap is ~3 years and that filter matched a quarter of the
  data — useless. I noticed the row count was wrong and rewrote it with fixed calendar
  buckets. **Lesson: always sanity-check query output against expected row counts.**

---

### Q4 — Do fraudulent claims cost more money? (fraud vs honest, same severity)

- **Business question:** if we hold severity constant, do fraudsters ask for bigger payouts?
- **SQL technique:** **conditional aggregation** (a.k.a. "pivot"):
  `AVG(CASE WHEN fraud_reported='Y' THEN total_claim_amount END)` gives the average for
  fraud only; another `CASE` for honest only; subtract.
- **Result:**
  | Severity | Avg (fraud) | Avg (honest) | Difference |
  |---|---|---|---|
  | Total Loss | 64,041 | 61,792 | +2,249 |
  | Major Damage | 64,116 | 63,993 | **+123** |
  | Minor Damage | 48,726 | 48,633 | **+93** |
  | Trivial Damage | 5,038 | 5,320 | −282 |
- **Takeaway:** basically **no difference**. Fraud here is about *faking the incident /
  getting a worse severity code*, not about inflating the dollar amount. **This is the most
  important finding after Q1** — it tells you *where* to look for fraud (incident
  validation) and where *not* to (invoice review).

---

### Q5 — Is fraud concentrated in the most expensive claims?

- **Business question:** if we could only investigate the priciest 10% of claims, how much
  fraud would we catch?
- **SQL techniques:** **`NTILE(10) OVER (ORDER BY total_claim_amount)`** splits claims into
  10 equal-sized "deciles" by cost. Then a second CTE aggregates fraud rate per decile, plus
  a **running total** — `SUM(fraud_claims) OVER (ORDER BY amount_decile DESC)` — to show
  "what % of all fraud is at or above this decile."
- **Result:** fraud rate is roughly **flat (~27–37%) for the top 8 deciles**, and only
  drops (8–11%) for the cheapest 20% of claims. The most expensive 10% of claims hold only
  **11% of all fraud**.
- **Takeaway:** "chase the big claims" is a weak strategy. Expensive and mid-priced claims
  are equally fraud-prone. This *confirms Q4 from another angle*.

---

### Q6 — Which states are worst for fraud and cost?

- **SQL techniques:** CTE aggregating per state, then **`RANK() OVER (ORDER BY …)`** twice
  (once for fraud rate, once for average cost), plus **`AVG(...) OVER ()`** (a window with
  no `PARTITION`/`ORDER` = the grand average) to show each state vs the overall average.
- **Result:** OH 25.9%, IN 25.5%, IL 22.8%. A 3-point spread across the only 3 states in the
  data.
- **Takeaway:** geography is not a useful lever here.

---

### Q7 — Where does the claim money go, by incident type?

- **Business question:** for each kind of incident, what share of the payout is injury vs
  property vs vehicle damage?
- **SQL technique:** **ratio of sums** —
  `100.0 * SUM(injury_claim) / SUM(total_claim_amount)`.
- **Result:** astonishingly uniform. For *every* incident type, `vehicle_claim` is ~72% of
  the total, injury ~14%, property ~14%. Single-vehicle and multi-vehicle collisions each
  account for ~\$26M of the ~\$52.8M total; theft and parked-car incidents are tiny.
- **Takeaway:** the cost *mix* doesn't vary by incident type — another dimension with no
  differentiation. (Also hints the payout amounts were generated by a simple formula.)

---

### Q8 — Monthly trend, with month-over-month change

- **SQL techniques:** **`DATE_FORMAT(incident_date, '%Y-%m')`** to group by month, then
  **`LAG(incidents) OVER (ORDER BY incident_month)`** to get the previous month's value and
  compute the change.
- **Result:** Jan (516 incidents, 135 fraud), Feb (472, 108), **Mar (only 12)** — the data
  is cut off at 1 March 2015.
- **Takeaway:** can't say anything about seasonality — only ~2 usable months. `LAG` is
  demonstrated, but the honest read is "not enough time span."

---

### Q9 — Fraud rate by vehicle make

- **SQL techniques:** join to `vehicles`, `HAVING COUNT(*) >= 30` to only keep makes with a
  usable sample, and a **weighted portfolio baseline** using nested aggregates in a window:
  `SUM(SUM(fraud='Y')) OVER () / SUM(COUNT(*)) OVER ()`.
- **Result:** a real gradient — **Mercedes 33.9%**, Ford 30.6%, Audi 30.4% … down to
  **Jeep 16.4%**, Nissan 18.0%, Toyota 18.6%. About an 18-point spread. European premium
  makes high, Japanese makes + Jeep low.
- **Takeaway:** make *is* a usable signal, but weaker than severity, and almost certainly
  **confounded** (premium-car owners differ in lots of ways). Use it as a model feature, not
  a standalone rule — and watch for discrimination risk.

---

### Q10 — Running cumulative claim cost over time

- **SQL techniques:** CTE summing cost per day, then **`SUM(day_claim_amount) OVER (ORDER BY
  incident_date)`** = a **running total**, and dividing by `SUM(...) OVER ()` (grand total)
  to get "% of the period's total reached by this date."
- **Result:** liability piles up at a steady ~\$0.9M/day; by 1 Feb the insurer is halfway
  (54.5%) to the full-period total of ~\$52.8M.
- **Takeaway:** mostly a demonstration of running totals; the line is steady (no shocks).

---

### SQL technique coverage (what to claim on the resume)

| Technique | Where |
|---|---|
| CTE (`WITH`) | Q1, Q2, Q3, Q5, Q6, Q8, Q10 |
| `RANK` / `DENSE_RANK` | Q1, Q6 |
| `NTILE`, `PERCENT_RANK` | Q5 |
| `LAG` (previous row) | Q8 |
| `SUM() OVER (ORDER BY …)` running total | Q5, Q9, Q10 |
| `AVG() OVER ()` / `OVER (PARTITION BY …)` | Q6, Q9 |
| Scalar / correlated subquery | Q2, Q3 |
| Conditional ("pivot") aggregation | Q1, Q4 |
| `CASE WHEN` bucketing | Q2, Q3 |
| `HAVING` sample-size floor | Q1, Q2, Q9 |
| Ratio of sums | Q7, Q10 |

---

## 11. Step 5 — The Python analysis notebook

File: [`analysis/analysis.ipynb`](analysis/analysis.ipynb). It connects to the same MySQL
DB, pulls query results into **pandas** DataFrames, and draws 7 charts (saved to
[`charts/`](charts/)):

1. **Fraud rate by severity × type** (bar) — visual version of Q1.
2. **Fraud rate by state** (bar) — visual Q6.
3. **Claim amount box plots, fraud vs honest, by severity** — visual Q4. The fraud and
   honest boxes sit almost exactly on top of each other. This is the "picture that proves
   fraud isn't about money."
4. **Fraud rate by age bracket** (bar) — visual Q2, flat.
5. **Fraud rate by vehicle make** (bar) — visual Q9, the gradient.
6. **Cumulative claim cost** (line) — visual Q10.
7. **Z-score anomaly scatter** — see next section.

Charts use a colorblind-safe palette (blue = honest/normal, red = fraud/above-average), a
reference line for the portfolio average, and direct value labels.

---

## 12. Step 6 — The z-score "anomaly detection" (and why it failed)

### What a z-score is (simple)

A **z-score** tells you how unusual a number is compared to the rest of the group:

```
z = (value − group average) / group standard deviation
```

- z = 0 → exactly average
- z = 2 → two standard deviations above average (fairly rare)
- **|z| > 3 → very rare** (in a normal distribution, ~0.3% of values)

"Standard deviation" = the typical spread of the data around the average.

### What we did

For each `incident_severity` group, compute the z-score of `total_claim_amount`, and
**flag any claim with |z| > 3** as an "anomaly." The idea being tested: *maybe weirdly
large claims are fraud.*

Then — because we have the real `fraud_reported` label — we checked the flag against truth.

### The result

- Flagged **4 claims** out of 1,000.
- Of those 4, exactly **1** was actually fraud.
- **Precision = 1/4 = 25%** (barely better than randomly guessing, since 24.7% of all
  claims are fraud anyway).
- **Recall = 1/247 = 0.4%** (it caught almost none of the fraud).

Compare to the dumb one-line rule "flag every Major Damage claim": that flags 276 claims
and catches ~68% of fraud at ~61% precision.

### Why it failed

Because of **Q4/F3**: fraud in this data is *not* about the dollar amount. So a detector
that only looks at dollar amounts is looking in the wrong place. This is a *good* thing to
have in the project — lots of student projects stop at "I did anomaly detection" without
ever checking whether it worked. We checked, and reported that it didn't.

---

## 13. Step 7 — The machine-learning models

File: [`analysis/fraud_model.py`](analysis/fraud_model.py). Run: `python analysis/fraud_model.py`.

### Why we built models at all

**Not to ship a fraud detector.** The purpose was to **stress-test the main finding.**

The SQL analysis said: "incident severity is basically the whole signal; the other columns
don't add much." A fair challenge to that is: *maybe the other 19 columns contain signal
that only shows up in combination, which simple `GROUP BY` queries can't see.* A machine
learning model *can* see combinations. So: give a model everything, and check whether it
beats a rule that uses only severity.

### What the models are (simple)

- **Logistic regression:** draws the best straight-line boundary between "fraud" and "not
  fraud" in feature space. Output: for each feature, a **coefficient** — a number saying
  "this feature pushes the prediction toward fraud (+) or away (−), by this much." Great for
  *explaining* what matters.
- **Decision tree (depth 4):** a flowchart of yes/no questions ("Is severity = Major
  Damage? → if yes, is auto_make European? → …"). Depth 4 = at most 4 questions deep, so it
  stays simple and readable. Good at capturing *interactions* between features.

### What we fed them (features)

Incident fields (severity, type, collision type, authorities contacted, property damage,
police report, vehicles involved, injuries, witnesses, hour), a few policy fields (sex,
education, relationship, state, tenure, age, premium), the vehicle make, and the raw claim
amount. Categorical fields were **one-hot encoded** (turned into 0/1 columns), rare
categories folded together (`min_frequency=15`) to avoid overfitting.

### How we tested them properly

- **Stratified train/test split:** 70% of claims to train on (700), 30% held back to test
  on (300). "Stratified" = both halves keep the same 24.7% fraud rate.
- The model **never sees the test set during training**, so test performance is an honest
  estimate of real performance.

### The metrics (what the words mean)

- **Precision:** of the claims the model flagged as fraud, what % actually were?
  (High precision = few false alarms.)
- **Recall:** of all the real fraud, what % did the model catch?
  (High recall = few misses.)
- **ROC-AUC:** a single 0–1 score for how well the model *ranks* fraud above non-fraud
  across all thresholds. 0.5 = coin flip, 1.0 = perfect. ~0.7 = mediocre, ~0.8 = decent,
  0.9+ = strong.
- **Confusion matrix:** the 2×2 table of (predicted vs actual) — true negatives, false
  positives, false negatives, true positives.

### The results (held-out test set of 300 claims)

| Model | ROC-AUC | Precision | Recall |
|---|---|---|---|
| Baseline: "flag all Major Damage" (no training) | 0.77 | 0.63 | 0.68 |
| Logistic regression | 0.77 | 0.56 | 0.68 |
| Decision tree (depth 4) | 0.77 | 0.57 | 0.69 |

**The trained models tied the one-line rule.** ROC-AUC ~0.77 for all three.

Logistic regression's biggest coefficient by a mile: **`incident_severity = Major Damage`
(1.9)**. Everything else (European makes, a couple of demographic flags) had tiny weights.

Logistic confusion matrix on the test set: 186 true-negative, 40 false-positive, 24
false-negative, **50 true-positive**.

### What this means / how to say it

> "I trained a logistic regression and a decision tree on 20 features. Both landed at
> ROC-AUC ~0.77 — the same as a one-line rule that only uses incident severity. The honest
> conclusion is that severity carries the signal and the extra features add almost nothing
> on this dataset. The one thing the model gives you that a fixed rule doesn't is a
> **tunable threshold** — the precision-recall curve lets you trade recall for precision
> depending on how much investigator capacity you have. So the recommendation is: ship the
> simple rule now, build a model later only if you get richer data (adjuster notes,
> claimant history) or you need that threshold control."

**Do not oversell 0.77.** It's a mediocre AUC. The *finding* ("a model can't beat a
one-liner here") is the valuable part, not the model.

---

## 14. The findings, in plain English (F1–F9)

These are in [`ANALYSIS.md`](ANALYSIS.md) with full "so what / recommended action / caveats."

| # | Finding (plain English) |
|---|---|
| **F1** | Fraud rate by severity: Major Damage **60.5%**, everything else 7–13%. Major Damage ≈ half of all fraud. |
| **F2** | Drill into severity × type: Major Damage **collisions** are 58–63% fraud. 28% of claims → 68% of fraud. |
| **F3** | At the same severity, fraud claims cost the **same** as honest ones (within ~\$120). Fraud is in the incident, not the invoice. |
| **F4** | Fraud rate is flat across the top 8 cost deciles. Screening by claim size barely helps; only the cheapest 20% is low-risk. |
| **F5** | Vehicle make has a real ~18-point spread (Mercedes 34% → Jeep 16%), but it's confounded — model feature only, not a rule. |
| **F6** | **No usable signal** in: policy age, state, age/education demographics, or month. (Honest negatives — worth stating.) |
| **F7** | Two data bugs: one incident dated before its policy started; one negative umbrella limit. Recommend ingestion checks. |
| **F8** | Z-score claim-amount anomaly detector: 0.4% recall, ~base-rate precision. Useless here — because of F3. |
| **F9** | Logistic regression + decision tree both tie the one-line severity rule (ROC-AUC ~0.77). Extra features add ~nothing. |

---

## 15. The one story that ties it all together

Tell it as a narrative, not a list:

> "I started by asking the obvious questions — is it the big claims? certain regions?
> younger customers? new policies? For each one I wrote a query, and one after another they
> came back flat. What *did* jump out was **incident severity**: 'Major Damage' claims are
> fraudulent 60% of the time versus about 11% for everything else.
>
> Then I asked the natural follow-up: *within* Major Damage, do the fraudsters at least ask
> for more money? No — fraud and honest claims cost the same once you fix the severity. So
> the fraud isn't in the dollar figure; it's in *how the incident gets classified*. That
> completely changes the recommendation: don't waste investigators on 'this invoice looks
> high' — put them on incident validation, and audit how the 'Major Damage' label gets
> assigned in the first place, because that label is what unlocks the big payout.
>
> Finally I checked whether I was missing hidden signal by throwing everything at a
> logistic regression and a decision tree. They couldn't beat the one-line severity rule.
> So the deliverable is almost embarrassingly simple: route every Major Damage claim to the
> fraud team. That one rule catches roughly two-thirds of the fraud while touching a quarter
> of the claims."

---

## 16. SQL concepts glossary

**JOIN** — combine rows from two tables where a key matches. `claims c JOIN incidents i ON
c.incident_id = i.incident_id` = "attach each claim's incident details to it."

**GROUP BY** — collapse many rows into one per group, so you can `COUNT`, `SUM`, `AVG` per
group. "Fraud rate *by state*" = `GROUP BY policy_state`.

**WHERE vs HAVING** — `WHERE` filters rows *before* grouping; `HAVING` filters *after*
grouping (so it can use `COUNT(*)`). "Only keep makes with ≥30 claims" = `HAVING COUNT(*)
>= 30`.

**CTE (Common Table Expression)** — a named temporary result you define with `WITH x AS
(...)` and then use like a table in the same query. Makes complex queries readable by
breaking them into steps. Alternative to nested subqueries.

**Subquery** — a query inside another query. **Scalar subquery** returns one value
(`WHERE amount > (SELECT AVG(amount) FROM …)`). **Correlated subquery** references the outer
query and re-runs per row.

**Window function** — a calculation across a set of rows *related to the current row*,
**without collapsing them** (unlike `GROUP BY`). Syntax: `FUNC(...) OVER (PARTITION BY ...
ORDER BY ...)`.
- `PARTITION BY` = the group to calculate within (like `GROUP BY` but keeps all rows)
- `ORDER BY` inside `OVER` = the order for running/ranking functions

**RANK / DENSE_RANK / ROW_NUMBER** — numbering rows by some order.
- `ROW_NUMBER`: 1,2,3,4 (always unique)
- `RANK`: 1,2,2,4 (ties share a rank, then skip)
- `DENSE_RANK`: 1,2,2,3 (ties share, no skip)

**NTILE(n)** — split the ordered rows into `n` equal-sized buckets and label each row 1..n.
`NTILE(10)` = deciles, `NTILE(4)` = quartiles.

**PERCENT_RANK** — where a row sits as a fraction 0–1 (0 = smallest, 1 = largest).

**LAG(col) / LEAD(col)** — the value of `col` in the previous / next row (by the `OVER
... ORDER BY`). Used for "change vs last month."

**SUM(col) OVER (ORDER BY date)** — a **running (cumulative) total**: each row = sum of all
rows up to and including this one.

**AVG(col) OVER ()** — with an empty `OVER ()`, this is just the grand average, attached to
every row so you can compare each row to it.

**Conditional aggregation / "pivot"** — `SUM(CASE WHEN condition THEN value END)` to compute
separate totals for sub-groups in one pass, producing columns instead of rows.

---

## 17. Every file in the repo and what it does

```
data/
  insurance_claims.csv     the raw Kaggle dataset (the only tracked data file)
  normalize_data.py        clean the CSV, split into 4 tables, validate, load into MySQL
  policies.csv, vehicles.csv, incidents.csv, claims.csv
                           the normalized tables as CSVs (git-ignored — regenerable)

db/
  schema.sql               CREATE TABLE statements: the 4 tables, PKs, FKs, indexes
  connection.py            builds a SQLAlchemy engine from .env (no hardcoded passwords)

queries/
  analysis_queries.sql     the 10 analytical queries, each with a comment block
  run_queries.py           parses that .sql file, runs each query, prints results as tables

analysis/
  analysis.ipynb           pandas + 7 charts + the z-score anomaly check
  fraud_model.py           logistic regression + decision tree vs the one-line rule

charts/                    the 8 exported PNGs (7 from the notebook + 1 from the model)

.env                       DB credentials (GIT-IGNORED — never committed)
.env.example               template showing which variables are needed
.gitignore                 ignores .env, .venv, __pycache__, derived CSVs, etc.
requirements.txt           pinned Python dependencies
Makefile                   make setup / db / load / queries / analyze / model / all

README.md                  recruiter-facing overview
ANALYSIS.md                business findings F1–F9 (analyst voice: finding → so what → action)
EXPLANATION.md             build journal: every step, decisions, bugs, insights (dated)
INTERVIEW_NOTES.md         short spoken-answer prep
PROJECT_GUIDE.md           this file
CLAUDE.md                  working agreement used while building (not part of the deliverable)
```

**Why 4 doc files?** They have different jobs: README sells it, ANALYSIS.md is the client
briefing, EXPLANATION.md is the lab notebook, INTERVIEW_NOTES.md / PROJECT_GUIDE.md are your
prep. In the interview, mention that keeping a decision journal (EXPLANATION.md) is a habit —
interviewers like that.

---

## 18. How to run the whole thing

```bash
# one-time setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# database (MySQL must be running)
mysql -u root -e "CREATE DATABASE insurance_claims;
                  CREATE USER 'insurance_app'@'localhost' IDENTIFIED BY 'somepassword';
                  GRANT ALL PRIVILEGES ON insurance_claims.* TO 'insurance_app'@'localhost';"
cp .env.example .env        # edit .env, set DB_PASSWORD

# run it
python data/normalize_data.py     # clean + load  (add --no-db to only write CSVs)
python queries/run_queries.py      # the 10 SQL queries
jupyter notebook analysis/analysis.ipynb   # charts + anomaly check
python analysis/fraud_model.py     # the models

# or just:  make all
```

---

## 19. Cross-question bank — hard questions + strong answers

**Q: Walk me through your normalization. Why these 4 tables?**
> The flat table mixes three different "things": the person/policy, the event, and the
> money. I split along those lines — `policies` for everything that describes the insured
> and their contract, `incidents` for the event, `claims` for the payout and the fraud
> label, and `vehicles` for the car. Keys connect them: `policy_number` is a natural primary
> key; I generated surrogate keys for incidents, vehicles, and claims because the raw data
> had none. It's roughly third normal form. The caveat I'd flag: in this dataset it's all
> 1-to-1, so the normalization is more about demonstrating the modeling than about removing
> real redundancy.

**Q: Isn't `incident_severity` basically leaking the answer?**
> Possibly, yes — it might be part of how this teaching dataset was generated, and severity
> is assigned by a human adjuster who could be influenced. That's exactly why I don't
> present 60% as a real-world number. In production I'd (a) re-measure the signal on real
> claims, and (b) audit how the severity code gets assigned, because if that's gameable,
> that's the actual control point.

**Q: Your fraud rate is 24.7%. That's not realistic.**
> Correct. Real auto insurance is 1–2%. This is a curated Kaggle dataset built for
> learning, so it's dense with signal. I treat every number as a relative comparison, not a
> forecast, and I say so in the README and the analysis doc.

**Q: What's the difference between RANK and DENSE_RANK? Why did you use DENSE_RANK in Q1?**
> Both give tied rows the same rank. RANK then skips (1,2,2,4); DENSE_RANK doesn't
> (1,2,2,3). I used DENSE_RANK because I wanted a clean 1..N ranking of fraud rates without
> gaps — I'm ranking categories, not running a competition where skipped places matter.

**Q: Why NTILE for the "top 10%" instead of `ORDER BY ... LIMIT 100`?**
> `LIMIT` just gives you the rows. `NTILE(10)` labels *every* claim with its decile, so I
> can then aggregate fraud rate *per decile* and see the whole distribution — which is what
> showed the fraud rate is flat across the top 8 deciles. `LIMIT` would have hidden that.

**Q: Explain a window function to me like I'm not technical.**
> `GROUP BY` squashes 100 rows into 1 summary row. A window function computes a summary
> *but keeps all 100 rows*, adding the summary as a new column. So I can show each state's
> fraud rate *and* how far it is from the national average, on the same row, without a
> self-join.

**Q: The z-score anomaly detector failed. Why include it?**
> Two reasons. One, it directly confirms the main finding — fraud isn't about claim size,
> so an amount-based detector can't work. Two, most projects claim "I did anomaly detection"
> and never check if it caught anything. I checked it against the real labels and reported
> that it didn't. Knowing when a technique *doesn't* apply is a skill.

**Q: Your models only hit 0.77 AUC. That's not great.**
> Agreed, it's mediocre. But the point of the models wasn't performance — it was to test
> whether the 19 features I wasn't using contained hidden signal. They don't: the models
> tie a one-line rule. That negative result is the finding. If I wanted to actually improve
> detection I'd need better data — adjuster notes, prior claim history, photos — not a
> fancier algorithm on these columns.

**Q: What would you do differently / with more time?**
> Get a longer time window (this is 2 months) to check seasonality and confirm the severity
> signal is stable. Get process metadata — who set the severity, how many people touched
> the claim, time to assign — since the fraud lives in the classification step. Add a cost
> model so triage weights expected loss, not just claim count. And a fairness review before
> anything demographic or make-based goes near production.

**Q: How did you handle missing data?**
> The dataset uses `"?"` as a missing marker in three columns and real blanks in a fourth.
> I converted all of them to proper NULL and kept the rows — dropping 400+ rows would bias
> everything. A missing `collision_type` is often meaningful anyway: it means the incident
> wasn't a collision.

**Q: Show me you can write a window function on the whiteboard.**
> Practice this one — fraud rate per state vs the overall average:
> ```sql
> SELECT policy_state,
>        ROUND(100.0 * AVG(fraud_reported='Y'), 1) AS state_rate,
>        ROUND(100.0 * AVG(AVG(fraud_reported='Y')) OVER (), 1) AS overall_rate
> FROM policies p JOIN claims c ON c.policy_number = p.policy_number
> GROUP BY policy_state;
> ```
> And a running total:
> ```sql
> SELECT incident_date,
>        SUM(daily_total) OVER (ORDER BY incident_date) AS running_total
> FROM (SELECT incident_date, SUM(total_claim_amount) AS daily_total
>       FROM incidents i JOIN claims c ON c.incident_id = i.incident_id
>       GROUP BY incident_date) d;
> ```

**Q: Why is `total_claim_amount = injury + property + vehicle` important?**
> It's a data-quality assertion. If those don't add up, the data is corrupted or I've
> misunderstood the columns. I check it in `normalize_data.py` — it holds for 100% of rows,
> which gives me confidence the money columns are trustworthy.

**Q: What's a CTE and why not just use subqueries?**
> A CTE is a named temporary result set defined with `WITH`. Functionally similar to a
> subquery, but you can name it, reference it multiple times, and read the query top to
> bottom as a series of steps. My Q5 uses two stacked CTEs — first assign deciles, then
> aggregate per decile — which would be an ugly nested subquery otherwise.

---

## 20. Known weaknesses (say these before they ask)

- **Only 1,000 rows and 2 usable months.** Small; no seasonality possible.
- **Curated dataset, 24.7% fraud** — not real-world rates.
- **`incident_severity` may be label-leaked** — the strongest finding rests on a field that
  might be circular.
- **Relationships are 1-to-1**, so the normalization doesn't get truly exercised.
- **`auto_make` and demographic signals are confounded** — correlation, not cause.
- **The models are lightly tuned on a single split** — no cross-validation, small test set.
- **No true "loss ratio" analysis** — the data has annual premiums and one-time claims, not
  a comparable time series, so a proper premiums-vs-payouts loss ratio isn't well supported.

Being able to list your own project's limitations, unprompted, is one of the strongest
signals you can give in an interview.
```
