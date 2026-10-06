# ANALYSIS.md — Insights Log

Business-facing findings from the insurance claims data, written the way an analyst /
solution associate would brief a stakeholder: **what we found, why it matters, what to do about it.**

This file is about *conclusions*. The step-by-step process, bugs, and modeling decisions
live in [EXPLANATION.md](EXPLANATION.md).

Each finding uses this shape:

> **Finding** — the observation, with numbers.
> **So what** — the business implication.
> **Recommended action** — what an insurer should do / investigate next.
> **Confidence & caveats** — sample size, data limitations, alternative explanations.

---

## Dataset at a glance

- Source: Kaggle "Auto Insurance Claims Data" (Bunty Shah) — 1,000 auto claims, incidents in **Jan–Mar 2015**.
- Ground-truth label available: `fraud_reported` (Y/N).
- **Overall fraud rate: 24.7%** (247 of 1,000 claims). Note this is a curated teaching
  dataset, so the base rate is far higher than a real book of business (~1–2%). Treat all
  rates below as *relative* comparisons, not absolute forecasts.

---

## Findings

### F1 — Incident severity is the single strongest fraud indicator seen so far
**Finding** — Fraud rate by `incident_severity`:

| Severity | Claims | Fraud rate |
|---|---|---|
| Major Damage | 276 | **60.5%** |
| Minor Damage | 354 | 10.7% |
| Total Loss | 280 | 12.9% |
| Trivial Damage | 90 | 6.7% |

**So what** — "Major Damage" claims are ~5–6x more likely to be fraudulent than any other
severity band. A single categorical field separates a high-risk pool worth close to half
of all fraud (167 of 247 fraud cases).

**Recommended action** — Route every "Major Damage" claim to enhanced review / SIU triage
before payout. Even a coarse rule ("investigate all Major Damage") would catch ~68% of
fraud while touching only ~28% of claims.

**Confidence & caveats** — Strong effect, decent sample (276 rows). But this is likely how
the dataset was constructed, so validate against real claims before operationalizing.
Severity is adjuster-assigned and could itself be gamed.

---

### F2 — "Major Damage" collisions are the fraud hotspot (Q1)
**Finding** — The four highest-fraud severity×type cells:

| Severity × Type | Claims | Fraud rate |
|---|---|---|
| Major Damage · Single Vehicle Collision | 132 | **62.9%** |
| Major Damage · Multi-vehicle Collision | 144 | **58.3%** |
| Total Loss · Multi-vehicle Collision | 145 | 13.1% |
| Minor Damage · Single Vehicle Collision | 136 | 12.5% |

Every non-"Major Damage" cell sits between 6% and 13%.

**So what** — Fraud is not spread across incident types; it is overwhelmingly concentrated
in claims an adjuster has coded "Major Damage." 276 such claims (28% of the book) contain
167 of 247 fraud cases (**68%**).

**Recommended action** — Make "Major Damage" an automatic SIU-review trigger. Separately,
audit *how* the "Major Damage" label gets assigned — if fraud rings know it unlocks larger
payouts, the labelling step itself is the control point.

**Confidence & caveats** — Large, clean effect. But `incident_severity` is likely part of
how this teaching dataset was generated, so re-measure on real claims before hard-wiring a rule.

---

### F3 — Fraudulent claims are NOT inflated relative to honest ones (Q4)
**Finding** — Average `total_claim_amount`, fraud vs legit, at equal severity:

| Severity | Avg (fraud) | Avg (legit) | Gap |
|---|---|---|---|
| Total Loss | 64,041 | 61,792 | +2,249 |
| Major Damage | 64,116 | 63,993 | +123 |
| Minor Damage | 48,726 | 48,633 | +93 |
| Trivial Damage | 5,038 | 5,320 | −282 |

**So what** — Once severity is held fixed, fraudsters claim almost exactly the same amount
as honest claimants. The fraud in this book is about **fabricating / exaggerating the
incident** (getting into the "Major Damage" bucket), not about padding the dollar figure
within a bucket. A "claim amount looks too high" rule would miss it.

**Recommended action** — Detection effort belongs at incident validation (police report,
photos, damage inspection), not at invoice review.

**Confidence & caveats** — Consistent across all four severity bands; high confidence.

---

### F4 — Screening by claim size is a weak filter (Q5)
**Finding** — Fraud rate by claim-amount decile is essentially flat at ~27–37% for the top
8 deciles and only drops (8–11%) for the cheapest 20% of claims. Investigating the most
expensive 10% of claims would catch only **11%** of all fraud; the most expensive 50% would
catch ~72%.

**So what** — "Chase the big claims" is a poor triage strategy here — big and mid-size
claims are equally fraud-prone. The only safe deprioritisation is the bottom ~20% by cost.

**Recommended action** — Use severity (F2) and incident evidence, not dollar thresholds,
to route investigations. Fast-track the cheapest quintile for straight-through processing.

**Confidence & caveats** — 100 claims per decile; stable pattern.

---

### F5 — Vehicle make shows a real gradient (Q9)
**Finding** — Fraud rate by `auto_make` (makes with 55–80 claims each) ranges from
**Mercedes 33.9%** / Ford 30.6% / Audi 30.4% down to **Jeep 16.4%** / Nissan 18.0% /
Toyota 18.6% — an ~18-point spread. European luxury/premium makes cluster high; Japanese
makes and Jeep cluster low.

**So what** — Make is a usable secondary risk feature (worth ~±9 points vs the 24.7%
portfolio rate at the extremes), though weaker than severity.

**Recommended action** — Include `auto_make` as a feature in any fraud-scoring model, but
do not use it as a standalone rule (fair-lending / discrimination risk, and it is likely a
proxy for owner demographics or coverage type rather than a cause).

**Confidence & caveats** — Decent samples, but almost certainly confounded (premium-car
owners differ systematically). Correlational only.

---

### F6 — Signals that DON'T pan out: policy age, state, demographics, seasonality
**Finding** —
- **Early claims (Q3):** claims filed within a year of policy binding run 27.8% fraud vs
  24.4% for older policies — a marginal 3-point lift on just 43 claims. The "brand-new
  policy" red flag barely registers in this book.
- **State (Q6):** OH 25.9% / IN 25.5% / IL 22.8% — a 3-point spread across only 3 states.
  Not a useful lever.
- **Demographics (Q2):** no stable age×education pattern; the highest cell (55+ with an
  "MD" education level, 60% fraud) rests on 15 claims and is noise.
- **Seasonality (Q8):** Jan 26.2% vs Feb 22.9% fraud; March has only 12 records (the
  dataset is truncated at 2015-03-01), so no real seasonal read is possible.

**So what** — Analyst honesty point: most "intuitive" fraud dimensions add little here.
Chasing them would spend investigator time for almost no lift.

**Recommended action** — Concentrate the fraud program on incident severity + evidence
quality; treat policy-age/state/demographic flags as, at most, minor model features.

**Confidence & caveats** — Several of these are small-sample; "no signal" here does not
mean "no signal" in a full book of business.

---

### F7 — Two data-quality issues found during analysis
**Finding** — (1) One claim has an incident dated **20 days before** its policy bind date —
impossible, a data-entry error. (2) One policy has a **negative `umbrella_limit`**
(−1,000,000). Both were isolated, not systemic.

**So what** — Minor here, but in production these are the kind of records that silently
break loss-ratio and exposure reporting.

**Recommended action** — Add validation at ingestion: `incident_date >= policy_bind_date`
and `umbrella_limit >= 0`.

**Confidence & caveats** — Exhaustive check; exactly 1 row each.

---

### F8 — A z-score "claim amount anomaly" flag is near-useless for fraud (notebook §7)
**Finding** — Flagging claims whose `total_claim_amount` is >3 SD from the mean *of their
severity group* flags only **4 of 1,000** claims, of which **1** is fraud:
precision 25% (≈ the 24.7% base rate), recall **0.4%**. A one-line rule — "investigate
every Major Damage claim" — flags 276 claims at **61% precision / 68% recall**.

**So what** — Confirms F3 from the other direction: because fraud here is not about claim
size, an amount-based outlier detector cannot find it. The naive "z-score anomaly = fraud"
approach that many projects stop at would have added no value.

**Recommended action** — Skip amount-anomaly scoring for fraud triage. If a model is built,
train it on incident features (severity, type, evidence completeness, make) with fraud as
the label — do not rely on unsupervised cost outliers.

**Confidence & caveats** — Direct comparison against ground truth on the full dataset;
the z-score method itself is deliberately simple (per-group, |z|>3).

---

### F9 — A supervised model ties the one-line rule (analysis/fraud_model.py)
**Finding** — L2 logistic regression and a depth-4 decision tree, trained on incident +
policy + vehicle features (stratified 70/30 split), both reach **ROC-AUC ≈ 0.77 on
held-out data** — statistically indistinguishable from the "flag every Major Damage claim"
baseline (AUC 0.77, 62% precision / 68% recall). The logistic model's largest coefficient
by far is `incident_severity = Major Damage` (1.9); European makes and a few demographic
flags follow with small weights — exactly what the EDA predicted.

**So what** — The extra features add almost no discriminatory power on this book; severity
is the signal. The model's one genuine advantage is a **tunable threshold** — its
precision–recall curve lets you trade recall for precision, which a fixed rule cannot.

**Recommended action** — Ship the simple severity rule now. Only invest in a model if
(a) richer features become available (adjuster/process data, claimant history) or (b) the
business needs threshold control for capacity planning.

**Confidence & caveats** — Single split, small test set (300). `incident_severity` may be
partly label-derived in this dataset, which would inflate both the rule and the model.

---

_Add new findings below as the analysis progresses._
