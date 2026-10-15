# SQL Study Checklist

Everything you need to learn to fully understand the 10 queries in
[`queries/analysis_queries.sql`](queries/analysis_queries.sql). Tick each box when you can
explain it out loud **and** write a small example without looking.

Tier 1 (SELECT, JOIN, GROUP BY, ORDER BY, basic aggregates) is assumed — this list starts
at Tier 2.

---

## Tier 2 — Intermediate

### [ ] 1. `CASE WHEN` — SQL's if/else
Two uses:
- **Bucketing** a continuous value into labels:
  ```sql
  CASE WHEN age < 25 THEN '<25'
       WHEN age < 35 THEN '25-34'
       ELSE '35+' END
  ```
- **Conditional aggregation** (see #3).
Used in: Q2 (age buckets), Q3 (time buckets), Q4.

### [ ] 2. Boolean-as-1/0 trick (MySQL)
A condition like `fraud_reported = 'Y'` evaluates to **1 or 0**.
- `SUM(fraud_reported = 'Y')` → **count** of fraud rows
- `AVG(fraud_reported = 'Y')` → **fraction** that are fraud (× 100 = percentage)
Note: in PostgreSQL you'd write `COUNT(*) FILTER (WHERE fraud_reported = 'Y')` or
`AVG((fraud_reported = 'Y')::int)`.
Used in: almost every query.

### [ ] 3. Conditional / "pivot" aggregation
Compute separate totals for sub-groups **as columns**, in one pass:
```sql
SELECT
  incident_severity,
  AVG(CASE WHEN fraud_reported = 'Y' THEN total_claim_amount END) AS avg_fraud,
  AVG(CASE WHEN fraud_reported = 'N' THEN total_claim_amount END) AS avg_legit
FROM claims c JOIN incidents i ON i.incident_id = c.incident_id
GROUP BY incident_severity;
```
Why it works: aggregates skip NULLs, and `CASE` with no `ELSE` returns NULL for the rows
you don't want.
Used in: Q1, Q4.

### [ ] 4. Ratio of sums vs average of ratios
To get a group-level percentage, divide the **sums**, not the average of per-row ratios:
```sql
100.0 * SUM(injury_claim) / SUM(total_claim_amount)   -- correct
AVG(injury_claim / total_claim_amount)                 -- WRONG (over-weights small claims)
```
Used in: Q7, Q10.

### [ ] 5. Date functions
- `DATEDIFF(later_date, earlier_date)` → number of days between (MySQL).
- `DATE_FORMAT(d, '%Y-%m')` → `'2015-01'`, used to `GROUP BY` month.
- PostgreSQL equivalents: `later - earlier`, `TO_CHAR(d, 'YYYY-MM')`.
Used in: Q3 (`DATEDIFF`), Q8 (`DATE_FORMAT`).

### [ ] 6. Subqueries — the three kinds
- **Scalar subquery** — returns one value, usable anywhere a value goes:
  `WHERE amount > (SELECT AVG(amount) FROM claims)`
- **Derived table** — a subquery in `FROM`, used like a table:
  `FROM (SELECT ... GROUP BY ...) AS t`
- **Correlated subquery** — references the outer query, re-runs per row:
  `WHERE amount > (SELECT AVG(amount) FROM claims c2 WHERE c2.state = c.state)`
Used in: Q2, Q3.

### [ ] 7. `CROSS JOIN`
Combines every row of A with every row of B. Practical use here: B is a **single-row**
aggregate (the overall average), so cross-joining attaches that one number to every row for
comparison.
```sql
FROM bucketed b
CROSS JOIN (SELECT AVG(fraud_reported = 'Y') AS base_rate FROM bucketed) o
```
Used in: Q2.

### [ ] 8. `HAVING` for sample-size floors
`HAVING COUNT(*) >= 30` — drop groups too small to trust. Runs *after* `GROUP BY`, so it can
see `COUNT(*)`; `WHERE` cannot.
Used in: Q1, Q2, Q9.

---

## Tier 3 — Window functions (the core skill this project demonstrates)

### [ ] 9. The `OVER()` concept
A window function computes across a set of rows **related to the current row** but **does not
collapse them** — unlike `GROUP BY`, you keep every row and get an extra column.
General form: `FUNC(...) OVER (PARTITION BY ... ORDER BY ...)`

### [ ] 10. `PARTITION BY` vs `GROUP BY`
`PARTITION BY state` = "do the calculation separately within each state" — but all rows stay.
`GROUP BY state` = one row per state.

### [ ] 11. `ORDER BY` **inside** `OVER`
Defines the order for ranking and for running totals. `SUM(x) OVER (ORDER BY date)` means
"sum of x from the first row up to this one."

### [ ] 12. Ranking functions — know the tie behaviour
| Function | Ties get | Example (values 10,20,20,30) |
|---|---|---|
| `ROW_NUMBER()` | different numbers | 1,2,3,4 |
| `RANK()` | same number, then a gap | 1,2,2,4 |
| `DENSE_RANK()` | same number, no gap | 1,2,2,3 |
```sql
DENSE_RANK() OVER (ORDER BY fraud_rate_pct DESC) AS rank
```
Used in: Q1 (`DENSE_RANK`), Q6 (`RANK`).

### [ ] 13. `NTILE(n)`
Splits the ordered rows into `n` equal-sized buckets, labels each row 1..n.
`NTILE(10)` = deciles, `NTILE(4)` = quartiles.
```sql
NTILE(10) OVER (ORDER BY total_claim_amount) AS amount_decile
```
Used in: Q5.

### [ ] 14. `PERCENT_RANK()`
Relative position of a row as a fraction 0–1 (0 = smallest value, 1 = largest).
Used in: Q5 (mentioned).

### [ ] 15. `LAG()` / `LEAD()`
Value from the previous / next row, by the window's `ORDER BY`.
```sql
incidents - LAG(incidents) OVER (ORDER BY month) AS mom_change
```
The first row's `LAG` is NULL (nothing before it).
Used in: Q8.

### [ ] 16. Running (cumulative) total
```sql
SUM(day_amount) OVER (ORDER BY incident_date) AS running_total
```
Each row = sum of all rows up to and including this one.
Used in: Q5, Q9, Q10.

### [ ] 17. Global aggregate via empty `OVER ()`
`SUM(x) OVER ()` with nothing inside = grand total over the whole result, attached to every
row. Lets you compute "this row vs the overall total/average" without a self-join.
```sql
100.0 * SUM(fraud_claims) OVER (ORDER BY decile DESC) / SUM(fraud_claims) OVER ()
```
Used in: Q5, Q6 (`AVG(...) OVER ()`), Q10.

### [ ] 18. Aggregate nested inside a window
```sql
SUM(SUM(fraud_reported = 'Y')) OVER () / SUM(COUNT(*)) OVER ()
```
Evaluates in two steps: first the inner `SUM(...)` / `COUNT(*)` per group (because of
`GROUP BY`), then the outer `SUM(...) OVER ()` across those grouped rows. This gives a
**sample-weighted** portfolio average.
Used in: Q9.

---

## Tier 4 — Query structure

### [ ] 19. CTE (`WITH ... AS`)
A named temporary result you define up front and then use like a table.
```sql
WITH combo AS (
    SELECT ... GROUP BY ... HAVING ...
)
SELECT *, DENSE_RANK() OVER (ORDER BY fraud_rate_pct DESC)
FROM combo;
```
Why: readability (read top-to-bottom), reuse (reference it twice), and it lets you filter
or rank on a window-function result (which you can't do directly — see #21).
Used in: Q1, Q2, Q3, Q5, Q6, Q8, Q10.

### [ ] 20. Stacking multiple CTEs
```sql
WITH ranked AS (
    SELECT ..., NTILE(10) OVER (ORDER BY total_claim_amount) AS amount_decile
    FROM claims
),
by_decile AS (
    SELECT amount_decile, COUNT(*) AS claims, ...
    FROM ranked
    GROUP BY amount_decile
)
SELECT * FROM by_decile ORDER BY amount_decile DESC;
```
Step 1 assigns the decile, step 2 aggregates per decile. As one nested subquery this would
be hard to read.
Used in: Q5.

### [ ] 21. Logical query evaluation order
```
FROM / JOIN  →  WHERE  →  GROUP BY  →  HAVING  →  SELECT (incl. window functions)
             →  ORDER BY  →  LIMIT
```
Consequences to understand:
- You **can't** put a window function in `WHERE` or `GROUP BY` — they run *after*. Wrap the
  query in a CTE/subquery and filter in the outer query.
- `HAVING` can use aggregates; `WHERE` can't.
- Aliases defined in `SELECT` aren't visible in `WHERE` (but are in `ORDER BY` in MySQL).

---

## Also required: the schema

### [ ] 22. Know the tables and how they join
```
policies.policy_number  (PK)
   ├── vehicles.policy_number   (FK)
   ├── incidents.policy_number  (FK)
   └── claims.policy_number     (FK)
incidents.incident_id   (PK)
   └── claims.incident_id       (FK)
```
- `policies` — customer + policy terms
- `vehicles` — the car
- `incidents` — the event (has `incident_severity`, the key field)
- `claims` — the money + `fraud_reported` (the label)

You must be able to say which table a column lives in and write the `JOIN` to connect them.

---

## Suggested order to learn

1. #1–#4 (CASE, boolean trick, conditional aggregation, ratio of sums) — used everywhere
2. #19–#21 (CTEs + evaluation order) — the scaffolding
3. #9–#12 (window basics + ranking) — the headline skill
4. #16–#18 (running totals + global aggregates) — the "senior" touches
5. #13–#15 (NTILE, PERCENT_RANK, LAG) — quick once you have #9
6. #5–#8 (dates, subqueries, CROSS JOIN, HAVING) — fill-ins
7. #22 (schema) — read once, refer back

## How to practise

Run each concept against the live database:
```bash
mysql -u insurance_app -p insurance_claims
```
Then take each of the 10 queries, cover the code, read only the comment (the business
question), and try to rewrite it. Compare. Repeat until fluent.
