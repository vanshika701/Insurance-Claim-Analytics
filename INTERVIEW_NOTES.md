# Interview Notes — Insurance Claims Analytics

Spoken-answer prep for the ZS Associates Business Technology Solutions Associate interview.
Keep answers to 30–60 seconds; lead with the point, then the detail.

---

## 30-second pitch

> I took a real Kaggle auto-insurance dataset — 1,000 claims, one flat 39-column table with
> a ground-truth fraud label — normalized it into a 4-table MySQL schema, and wrote ten
> analytical SQL queries plus a Python analysis layer. The headline finding is that one
> feature, incident severity, carries almost all of the fraud signal: "Major Damage"
> collisions are ~60% fraudulent versus ~11% everywhere else. Several intuitive red flags —
> claim size, customer age, region, seasonality — turned out to carry no usable signal,
> and I can show that with the queries.

---

## The normalization story ("walk me through your data modeling")

- **Raw state:** one flat CSV. 39 usable columns, a junk trailing column from a stray
  delimiter, `"?"` used as a placeholder in three columns, one negative `umbrella_limit`.
- **Cleaning:** `"?"` and blank → NULL (kept the rows — dropping them would bias the
  analysis), junk column dropped, dates parsed, negative umbrella limit → NULL.
- **Schema:** split into `policies` (natural PK `policy_number`) → `vehicles`, and
  `incidents` (surrogate PK) → `claims`. FKs, NOT NULL where the data supports it, indexes
  on the columns the queries filter/join on.
- **Honest caveat I raise myself:** in this dataset the relationships are 1:1 (one incident,
  one claim per policy). I modeled them as 1:many anyway because that's how a real carrier's
  system works and it makes the queries realistic — but I don't pretend the data is richer
  than it is.
- **Verification:** row counts per table, FK integrity checks, and an arithmetic check that
  `injury + property + vehicle = total_claim_amount` (holds for 100% of rows).

---

## Walk through a query

### Q1 — fraud rate by incident severity × type, ranked
```sql
WITH combo AS (
    SELECT i.incident_severity, i.incident_type,
           COUNT(*) AS claims,
           ROUND(100.0 * AVG(c.fraud_reported = 'Y'), 1) AS fraud_rate_pct
    FROM incidents i JOIN claims c ON c.incident_id = i.incident_id
    GROUP BY i.incident_severity, i.incident_type
    HAVING COUNT(*) >= 10
)
SELECT *, DENSE_RANK() OVER (ORDER BY fraud_rate_pct DESC) AS fraud_rate_rank
FROM combo ORDER BY fraud_rate_rank;
```
- `AVG(boolean)` is the % trick — average of a 1/0 condition is a rate.
- `HAVING COUNT(*) >= 10` keeps tiny cells from topping the ranking on noise.
- `DENSE_RANK` in a window over the CTE so the ranking is a separate concern from the
  aggregation.
- **Result:** the two "Major Damage" rows are 58–63%; everything else is single digits to 13%.

### Q5 — is fraud concentrated in expensive claims?
- `NTILE(10) OVER (ORDER BY total_claim_amount)` builds cost deciles.
- Then a second pass aggregates fraud rate per decile and a
  `SUM(fraud_claims) OVER (ORDER BY decile DESC)` running total = "what share of all fraud
  is at or above this decile."
- **Result:** fraud rate is flat (~27–37%) for the top 8 deciles → chasing big claims is a
  weak filter. This is the kind of "the intuitive strategy doesn't work" answer that a
  ranking query alone wouldn't surface.

### Q3 — the CTE bug I fixed (good to volunteer)
- First version flagged "early" claims as those filed within half the state-average gap
  between policy bind date and incident. But bind dates go back to 1990 while all incidents
  are early 2015, so the average gap is ~3 years and the filter matched a quarter of the
  data. I reworked it into fixed calendar buckets. Point: I sanity-check query output
  against row counts, I don't just trust that it ran.

---

## The fraud narrative (the "so what")

1. **Where is it?** `incident_severity = 'Major Damage'` — 60% vs 11%. 28% of claims hold
   68% of fraud.
2. **Is it about money?** No. At equal severity, fraudulent and honest claims are within
   ~$120 on average. The fraud is in *how the incident is classified*, not the dollar
   figure. → Investigation effort belongs at incident validation (police report, photos,
   inspection), not invoice review.
3. **What's the cheap win?** A single rule — route every "Major Damage" claim to special
   investigations — gets ~61% precision at ~68% recall on held-out data.
4. **Weak/no signal:** claim size, age, education, `policy_state`, month, policy age. I ran
   the queries; the differences are within a few points and mostly small-sample.

---

## "You built a model — did it help?"

> I trained an L2 logistic regression and a depth-4 decision tree on incident + policy +
> vehicle features, with a stratified 70/30 split. Both land at ROC-AUC ~0.77 — essentially
> tied with the one-line "all Major Damage" rule. The honest read is that severity is doing
> the work and the extra features add very little. Where the model *does* earn its keep is
> the tunable threshold: the precision–recall curve shows I can trade recall for higher
> precision, which a fixed rule can't. The top coefficients are exactly what the EDA
> predicted — Major Damage dominates, then European makes and a few demographic flags with
> small weights.

Discipline point: I didn't inflate the result. A model that ties a one-liner *is* the
finding.

---

## "What would you do with more data / more time?"

- **Time dimension:** the data is 3 months. I'd want 2–3 years to say anything about
  seasonality or trend, and to validate the severity signal isn't an artifact.
- **Adjuster + process data:** who set the severity, time-to-assign, number of touches —
  since the fraud lives in the classification step, the process metadata is probably the
  richest untapped signal.
- **Claimant history:** prior claims, prior denials — not in this dataset, standard in a
  real one.
- **Cost model:** weight the triage by expected loss (recall on high-value claims matters
  more), not just raw precision/recall.
- **Fairness review:** `auto_make` and demographic features correlate with fraud here but
  are proxies; I'd check disparate impact before anything demographic went into production.

---

## SQL technique cheat-sheet (what's demonstrated, and where)

| Technique | Query |
|---|---|
| CTE (`WITH`) | Q1, Q2, Q3, Q5, Q6, Q8, Q10 |
| `RANK` / `DENSE_RANK` | Q1, Q6 |
| `NTILE`, `PERCENT_RANK` | Q5 |
| `LAG` (period-over-period) | Q8 |
| `SUM() OVER (ORDER BY …)` running total | Q9, Q10 |
| `AVG() OVER (PARTITION BY …)` for a baseline column | Q6, Q9 |
| Correlated / scalar subquery | Q2, Q3 |
| Conditional ("pivot") aggregation | Q1, Q4 |
| `CASE WHEN` bucketing | Q2, Q3 |
| `HAVING` sample-size floor | Q1, Q2, Q9 |
| Ratio-of-sums | Q7, Q10 |

---

## Likely gotcha questions

- **"Why MySQL and not Postgres?"** It's what the role uses and it was already running.
  The SQL here (CTEs, window functions) is standard and ports to Postgres with near-zero
  changes.
- **"Your fraud rate is 24.7% — that's absurd for insurance."** Correct — it's a curated
  teaching dataset. That's why I report every number as a *relative* comparison, not a
  forecast, and say so in the README and ANALYSIS.md.
- **"Isn't `incident_severity` leaking the label?"** Possibly — it may be part of how the
  dataset was generated. I flag that explicitly. In production I'd re-measure the signal on
  real claims before hard-wiring a rule, and I'd audit how the severity code is assigned.
- **"One incident is dated before its policy started — did you drop it?"** No, I kept it and
  flagged it as a data-quality finding (F7). One row. I also recommend an ingestion check
  (`incident_date >= policy_bind_date`).
