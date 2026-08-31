-- ===========================================================================
-- Insurance Claims Analytics — analytical SQL
--
-- Target: MySQL 8+ (tested on MySQL 9.2). Schema: db/schema.sql
--   policies (policy_number PK) --1:1-- vehicles
--        |--1:1-- incidents (incident_id PK) --1:1-- claims
--
-- Each query is standalone and answers one business question. The focus is
-- query depth: CTEs, window functions (RANK / NTILE / LAG / SUM OVER),
-- conditional aggregation, and correlated subqueries — not just joins.
--
-- Run all: python queries/run_queries.py
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- Q1. Fraud rate by incident severity x incident type, ranked.
--     Business question: which severity/type combinations concentrate fraud,
--     and how do they rank against each other?
--     Techniques: conditional aggregation, DENSE_RANK() window, HAVING.
-- ---------------------------------------------------------------------------
WITH combo AS (
    SELECT
        i.incident_severity,
        i.incident_type,
        COUNT(*)                                              AS claims,
        SUM(c.fraud_reported = 'Y')                           AS fraud_claims,
        ROUND(100.0 * AVG(c.fraud_reported = 'Y'), 1)         AS fraud_rate_pct
    FROM incidents i
    JOIN claims    c ON c.incident_id = i.incident_id
    GROUP BY i.incident_severity, i.incident_type
    HAVING COUNT(*) >= 10          -- ignore tiny cells
)
SELECT
    incident_severity,
    incident_type,
    claims,
    fraud_claims,
    fraud_rate_pct,
    DENSE_RANK() OVER (ORDER BY fraud_rate_pct DESC) AS fraud_rate_rank
FROM combo
ORDER BY fraud_rate_rank, claims DESC;


-- ---------------------------------------------------------------------------
-- Q2. Fraud rate by age bracket x education level.
--     Business question: are there demographic segments with elevated fraud?
--     Techniques: CASE WHEN bucketing, CTE, conditional aggregation,
--     comparison against the overall rate via CROSS JOIN.
-- ---------------------------------------------------------------------------
WITH bucketed AS (
    SELECT
        CASE
            WHEN p.age < 25 THEN '1: <25'
            WHEN p.age < 35 THEN '2: 25-34'
            WHEN p.age < 45 THEN '3: 35-44'
            WHEN p.age < 55 THEN '4: 45-54'
            ELSE                 '5: 55+'
        END                                          AS age_bracket,
        p.insured_education_level                     AS education_level,
        c.fraud_reported
    FROM policies p
    JOIN claims   c ON c.policy_number = p.policy_number
),
overall AS (
    SELECT AVG(fraud_reported = 'Y') AS base_rate FROM bucketed
)
SELECT
    b.age_bracket,
    b.education_level,
    COUNT(*)                                                       AS claims,
    ROUND(100.0 * AVG(b.fraud_reported = 'Y'), 1)                  AS fraud_rate_pct,
    ROUND(100.0 * (AVG(b.fraud_reported = 'Y') - o.base_rate), 1)  AS pts_vs_overall
FROM bucketed b
CROSS JOIN overall o
GROUP BY b.age_bracket, b.education_level, o.base_rate
HAVING COUNT(*) >= 15
ORDER BY fraud_rate_pct DESC
LIMIT 15;


-- ---------------------------------------------------------------------------
-- Q3. Does filing soon after the policy was bound predict fraud?
--     Business question: early claims are a classic fraud red flag. Bucket
--     each claim by how long after policy_bind_date the incident occurred,
--     and compare fraud rate / cost across buckets. The "young policy"
--     threshold (1 year) is expressed as a subquery so it is easy to tune.
--     Techniques: CTE, DATEDIFF, CASE-WHEN bucketing, subquery threshold,
--     conditional aggregation, flags a data-quality anomaly (incident before bind).
-- ---------------------------------------------------------------------------
WITH claim_timing AS (
    SELECT
        c.claim_id,
        p.policy_state,
        DATEDIFF(i.incident_date, p.policy_bind_date) AS days_to_incident,
        c.total_claim_amount,
        c.fraud_reported
    FROM policies  p
    JOIN incidents i ON i.policy_number = p.policy_number
    JOIN claims    c ON c.incident_id   = i.incident_id
)
SELECT
    CASE
        WHEN days_to_incident < 0                              THEN '0: incident BEFORE bind (data error)'
        WHEN days_to_incident <= 90                            THEN '1: 0-90 days'
        WHEN days_to_incident <= (SELECT 365)                  THEN '2: 91-365 days (young policy)'
        WHEN days_to_incident <= 1095                          THEN '3: 1-3 years'
        ELSE                                                        '4: 3+ years'
    END                                                            AS bind_to_incident_bucket,
    COUNT(*)                                                        AS claims,
    SUM(fraud_reported = 'Y')                                       AS fraud_claims,
    ROUND(100.0 * AVG(fraud_reported = 'Y'), 1)                     AS fraud_rate_pct,
    ROUND(AVG(total_claim_amount))                                  AS avg_claim_amount
FROM claim_timing
GROUP BY bind_to_incident_bucket
ORDER BY bind_to_incident_bucket;


-- ---------------------------------------------------------------------------
-- Q4. Average claim amount by severity: fraud vs non-fraud, side by side.
--     Business question: do fraudulent claims cost more, holding severity fixed?
--     Techniques: conditional (pivot-style) aggregation.
-- ---------------------------------------------------------------------------
SELECT
    i.incident_severity,
    COUNT(*)                                                                    AS claims,
    ROUND(AVG(CASE WHEN c.fraud_reported = 'Y' THEN c.total_claim_amount END))   AS avg_amount_fraud,
    ROUND(AVG(CASE WHEN c.fraud_reported = 'N' THEN c.total_claim_amount END))   AS avg_amount_legit,
    ROUND(AVG(CASE WHEN c.fraud_reported = 'Y' THEN c.total_claim_amount END)
        - AVG(CASE WHEN c.fraud_reported = 'N' THEN c.total_claim_amount END))   AS fraud_premium_abs
FROM incidents i
JOIN claims    c ON c.incident_id = i.incident_id
GROUP BY i.incident_severity
ORDER BY fraud_premium_abs DESC;


-- ---------------------------------------------------------------------------
-- Q5. Is fraud concentrated in the most expensive claims?
--     Business question: if we only had budget to investigate the top decile
--     of claims by cost, how much fraud would we catch?
--     Techniques: NTILE(10) window to build cost deciles, then aggregate
--     fraud rate per decile + the running share of all fraud captured.
-- ---------------------------------------------------------------------------
WITH ranked AS (
    SELECT
        c.claim_id,
        c.total_claim_amount,
        c.fraud_reported,
        NTILE(10) OVER (ORDER BY c.total_claim_amount) AS amount_decile
    FROM claims c
),
by_decile AS (
    SELECT
        amount_decile,
        MIN(total_claim_amount)                       AS min_amount,
        MAX(total_claim_amount)                       AS max_amount,
        COUNT(*)                                      AS claims,
        SUM(fraud_reported = 'Y')                     AS fraud_claims,
        ROUND(100.0 * AVG(fraud_reported = 'Y'), 1)   AS fraud_rate_pct
    FROM ranked
    GROUP BY amount_decile
)
SELECT
    amount_decile,
    min_amount,
    max_amount,
    claims,
    fraud_claims,
    fraud_rate_pct,
    ROUND(100.0 * SUM(fraud_claims) OVER (ORDER BY amount_decile DESC)
        / SUM(fraud_claims) OVER (), 1)               AS pct_of_all_fraud_from_here_up
FROM by_decile
ORDER BY amount_decile DESC;


-- ---------------------------------------------------------------------------
-- Q6. State-level fraud & cost comparison, ranked.
--     Business question: which states (policy_state) are the worst for fraud
--     rate and average claim cost?
--     Techniques: RANK() over multiple measures, comparison to global average.
-- ---------------------------------------------------------------------------
WITH by_state AS (
    SELECT
        p.policy_state,
        COUNT(*)                                        AS claims,
        ROUND(100.0 * AVG(c.fraud_reported = 'Y'), 1)   AS fraud_rate_pct,
        ROUND(AVG(c.total_claim_amount))                AS avg_claim_amount
    FROM policies p
    JOIN claims   c ON c.policy_number = p.policy_number
    GROUP BY p.policy_state
)
SELECT
    policy_state,
    claims,
    fraud_rate_pct,
    RANK() OVER (ORDER BY fraud_rate_pct DESC)                          AS fraud_rank,
    avg_claim_amount,
    RANK() OVER (ORDER BY avg_claim_amount DESC)                        AS cost_rank,
    ROUND(fraud_rate_pct - AVG(fraud_rate_pct) OVER (), 1)             AS fraud_pts_vs_avg
FROM by_state
ORDER BY fraud_rate_pct DESC;


-- ---------------------------------------------------------------------------
-- Q7. Claim cost breakdown (injury / property / vehicle) by incident type.
--     Business question: where does the money go for each kind of incident?
--     Techniques: ratio-of-sums aggregation.
-- ---------------------------------------------------------------------------
SELECT
    i.incident_type,
    COUNT(*)                                                                    AS claims,
    ROUND(SUM(c.total_claim_amount))                                            AS total_paid,
    ROUND(100.0 * SUM(c.injury_claim)   / SUM(c.total_claim_amount), 1)         AS injury_pct,
    ROUND(100.0 * SUM(c.property_claim) / SUM(c.total_claim_amount), 1)         AS property_pct,
    ROUND(100.0 * SUM(c.vehicle_claim)  / SUM(c.total_claim_amount), 1)         AS vehicle_pct
FROM incidents i
JOIN claims    c ON c.incident_id = i.incident_id
GROUP BY i.incident_type
ORDER BY total_paid DESC;


-- ---------------------------------------------------------------------------
-- Q8. Monthly incident trend with month-over-month change.
--     Business question: how do claim volume and average cost move month to
--     month? (Data covers Jan-Mar 2015 only.)
--     Techniques: date truncation, LAG() window for MoM deltas.
-- ---------------------------------------------------------------------------
WITH monthly AS (
    SELECT
        DATE_FORMAT(i.incident_date, '%Y-%m')  AS incident_month,
        COUNT(*)                               AS incidents,
        ROUND(AVG(c.total_claim_amount))       AS avg_claim_amount,
        SUM(c.fraud_reported = 'Y')            AS fraud_claims
    FROM incidents i
    JOIN claims    c ON c.incident_id = i.incident_id
    GROUP BY DATE_FORMAT(i.incident_date, '%Y-%m')
)
SELECT
    incident_month,
    incidents,
    incidents - LAG(incidents) OVER (ORDER BY incident_month)                    AS incidents_mom_change,
    avg_claim_amount,
    avg_claim_amount - LAG(avg_claim_amount) OVER (ORDER BY incident_month)      AS avg_amount_mom_change,
    fraud_claims
FROM monthly
ORDER BY incident_month;


-- ---------------------------------------------------------------------------
-- Q9. Vehicle-make fraud pattern (makes with a usable sample only).
--     Business question: are claims on certain auto makes more fraud-prone?
--     Techniques: join to vehicles, HAVING for min sample size, window
--     AVG for the portfolio baseline.
-- ---------------------------------------------------------------------------
SELECT
    v.auto_make,
    COUNT(*)                                                              AS claims,
    SUM(c.fraud_reported = 'Y')                                           AS fraud_claims,
    ROUND(100.0 * AVG(c.fraud_reported = 'Y'), 1)                         AS fraud_rate_pct,
    ROUND(100.0 * (AVG(c.fraud_reported = 'Y')
        - SUM(SUM(c.fraud_reported = 'Y')) OVER ()
          / SUM(COUNT(*)) OVER ()), 1)                                    AS pts_vs_portfolio
FROM vehicles v
JOIN claims   c ON c.policy_number = v.policy_number
GROUP BY v.auto_make
HAVING COUNT(*) >= 30
ORDER BY fraud_rate_pct DESC;


-- ---------------------------------------------------------------------------
-- Q10. Running cumulative claim cost over time.
--     Business question: how fast is total claim liability accumulating across
--     the period, and what share of the full-period total is reached by each day?
--     Techniques: SUM() OVER with ORDER BY (running total), ratio to grand total.
-- ---------------------------------------------------------------------------
WITH daily AS (
    SELECT
        i.incident_date,
        COUNT(*)                    AS incidents,
        SUM(c.total_claim_amount)   AS day_claim_amount
    FROM incidents i
    JOIN claims    c ON c.incident_id = i.incident_id
    GROUP BY i.incident_date
)
SELECT
    incident_date,
    incidents,
    day_claim_amount,
    SUM(day_claim_amount) OVER (ORDER BY incident_date)                       AS running_total,
    ROUND(100.0 * SUM(day_claim_amount) OVER (ORDER BY incident_date)
        / SUM(day_claim_amount) OVER (), 1)                                   AS pct_of_period_total
FROM daily
ORDER BY incident_date;
