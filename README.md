# Project Brief: Insurance Claims Analytics (SQL + Python)

## Context
I'm a Computer Science student preparing for a placement interview for the **Business Technology Solutions Associate** role at **ZS Associates**. The role's primary requirements are **SQL** and **Python**. I need a small, complete, resume-ready project built tonight that demonstrates strong SQL query-writing skills (joins, window functions, CTEs, subqueries) and Python-based data analysis (pandas, matplotlib/seaborn).

## Project Overview
Build an **Insurance Claims Analytics** project using a **real-world dataset**: the "Auto Insurance Claims Data" dataset from Kaggle (39 columns, 1,000 rows, includes a real `fraud_reported` label). Load it into MySQL, analyze it with business-relevant SQL queries, and visualize it with Python. The goal is to simulate how an analyst would investigate claim patterns and fraud risk for an insurance company.

**Dataset source:** https://www.kaggle.com/datasets/buntyshah/auto-insurance-claims-data
File name: `insurance_claims.csv`

**Note:** This is a single flat table (not pre-split into normalized relational tables). Part of this project is to properly **normalize it into a relational schema** (separate customers, policies, incidents, claims tables) as a data modeling exercise before running the analysis — this is itself a good thing to be able to explain in an interview ("I normalized a flat dataset into a relational schema").

## Tech Stack
- **Database:** MySQL (assume a local MySQL server is running; use `mysql-connector-python` or `sqlalchemy` with the `mysql+mysqlconnector` dialect to connect)
- **Python:** pandas, numpy, matplotlib, seaborn, faker (for synthetic data), mysql-connector-python / sqlalchemy
- **Output:** Jupyter notebook or well-commented .py scripts, plus a polished README.md

**Note for Claude Code:** Before running any DB code, check if MySQL is installed and running locally (`mysql --version`, `mysql.server status` or `service mysql status` depending on OS). If it's not installed, install it first (or guide me through installing it) and create a dedicated database (e.g. `CREATE DATABASE insurance_claims;`) and user before proceeding. Ask me for MySQL root/user credentials if needed rather than assuming defaults.

## Folder Structure to Create
```
insurance-claims-analytics/
├── data/
│   └── insurance_claims.csv    # Downloaded from Kaggle (manual download, place here)
│   └── normalize_data.py       # Splits flat CSV into normalized tables (customers, policies, incidents, claims)
├── db/
│   └── schema.sql              # CREATE TABLE statements
│   └── connection.py           # MySQL connection helper (reads credentials from .env)
├── queries/
│   └── analysis_queries.sql    # All 10+ SQL queries, commented
├── analysis/
│   └── analysis.ipynb          # Python analysis + charts
├── charts/
│   └── (exported PNGs of key charts)
├── README.md
└── requirements.txt
```

## Step-by-Step TODO

### 1. Download the Dataset & Design the Schema
Download `insurance_claims.csv` manually from https://www.kaggle.com/datasets/buntyshah/auto-insurance-claims-data (requires a free Kaggle login) and place it in `data/`.

The raw CSV is one flat table (~39 columns). **Normalize it into these related tables** (primary/foreign keys, NOT NULL constraints, sensible data types) — this normalization step is itself something to be able to explain in an interview:

- **policies**: policy_number (PK), policy_bind_date, policy_state, policy_csl, policy_deductable, policy_annual_premium, umbrella_limit, insured_zip, insured_sex, insured_education_level, insured_occupation, insured_hobbies, insured_relationship, capital_gains, capital_loss, months_as_customer, age
- **vehicles**: vehicle_id (PK, generate a surrogate key), policy_number (FK), auto_make, auto_model, auto_year
- **incidents**: incident_id (PK, generate a surrogate key), policy_number (FK), incident_date, incident_type, collision_type, incident_severity, authorities_contacted, incident_state, incident_city, incident_location, incident_hour_of_the_day, number_of_vehicles_involved, property_damage, bodily_injuries, witnesses, police_report_available
- **claims**: claim_id (PK, generate a surrogate key), policy_number (FK), incident_id (FK), total_claim_amount, injury_claim, property_claim, vehicle_claim, fraud_reported

Note: column names in the raw CSV use hyphens (e.g. `capital-gains`) — rename to underscores during cleaning. Drop the trailing empty/junk column (`_c39`) if present.

### 2. Clean & Normalize the Data (data/normalize_data.py)
Write a Python script (pandas) that:
- Loads `insurance_claims.csv`
- Cleans column names (hyphens → underscores, lowercase), drops any empty/junk trailing column
- Handles missing/placeholder values (this dataset uses `"?"` for some missing values, e.g. in `collision_type`, `property_damage`, `police_report_available` — replace with NULL/NaN, don't silently drop rows)
- Splits the flat table into the four normalized dataframes (policies, vehicles, incidents, claims) described above, generating surrogate keys (`vehicle_id`, `incident_id`, `claim_id`) since the raw data doesn't have them
- Exports each normalized table to its own CSV in `data/` (or loads directly into MySQL — see step 3)

This cleaning/normalization step is genuinely good interview material: "the raw dataset had placeholder nulls and no relational structure, so I cleaned it and normalized it into 4 related tables before analysis."

### 3. Load Data into MySQL
Load the generated CSVs/dataframes into the `insurance_claims` MySQL database using `sqlalchemy` (with `mysql+mysqlconnector` dialect) or `mysql-connector-python`, applying the schema from `schema.sql`. Store DB credentials in a `.env` file (never hardcode them), and add `.env` to `.gitignore`. Verify row counts and foreign key integrity after loading.

### 4. Write These SQL Queries (queries/analysis_queries.sql)
Each query should be commented with what business question it answers. Use **window functions, CTEs, and subqueries** — not just basic joins — since query depth is what will be evaluated.

1. **Fraud rate by incident severity and type** — % of claims flagged fraud_reported='Y', grouped and ranked (RANK/DENSE_RANK)
2. **Fraud rate by age bracket and education level** — bucket `age` into ranges (CASE WHEN) and compare fraud rate across buckets (CTE)
3. **Claims filed close to policy bind date** — join policies + incidents, compute days between policy_bind_date and incident_date, flag claims filed unusually early (subquery for average threshold per policy_state)
4. **Average total_claim_amount by incident_severity**, with the fraud vs non-fraud split shown side by side (conditional aggregation)
5. **Top 10% highest total_claim_amount claims** — using NTILE or PERCENT_RANK window function
6. **State/region-level fraud comparison** — fraud rate and average claim amount by policy_state, ranked (window function)
7. **Claim cost breakdown** — injury_claim vs property_claim vs vehicle_claim as % of total_claim_amount, by incident_type
8. **Monthly/seasonal incident trend** — incident_date grouped by month, count and average claim amount (date functions + GROUP BY)
9. **Vehicle-level fraud pattern** — fraud rate by auto_make/auto_model, using join to vehicles table, filtered with HAVING for makes with enough sample size
10. **Running cumulative claim cost over time** — SUM() OVER ordered by incident_date, to show cost accumulation trend

### 5. Python Analysis Layer (analysis/analysis.ipynb)
Pull query results into pandas and produce:
- Bar chart: fraud rate by incident_severity and incident_type
- Bar chart: fraud rate by policy_state (regional comparison)
- Scatter/box plot: total_claim_amount distribution, fraud vs non-fraud
- Bar chart: fraud rate by age bracket
- One simple anomaly detection pass on total_claim_amount using z-score (flag anything > 3 standard deviations from the mean per incident_severity) and compare how well this lines up with the real fraud_reported label — this is a nice touch since you can actually check your anomaly flag against ground truth, which most student projects can't do

### 6. README.md
Write a clean, recruiter-skimmable README with:
- One-paragraph problem statement ("Insurance companies need to monitor claims for fraud risk across regions, incident types, and demographics...")
- Note on the dataset: real Kaggle auto insurance claims data (39 columns, 1,000 records, with ground-truth fraud labels), and a sentence on how it was normalized from one flat table into 4 relational tables
- Simple schema diagram (can be plain text/ASCII or a markdown table of tables + relationships)
- 3-4 sample queries with a snippet of their output
- Key insights section (e.g. "Claims filed within X days of policy start had a Y% higher fraud rate", "State Z showed the highest fraud rate at N%")
- Tech stack section
- How to run instructions (including the manual Kaggle download step, since the CSV can't be auto-downloaded without API credentials)
- Attribution line crediting the dataset source and Kaggle uploader (Bunty Shah)

### 7. Git
Initialize a git repo, write a sensible `.gitignore` (exclude `.env` and any credentials, `__pycache__`, `.ipynb_checkpoints`), and make clean incremental commits (data generation → schema → queries → analysis → README) rather than one giant commit, so the commit history itself looks intentional. Also add a `.env.example` file showing the required variables (without real values) so anyone cloning the repo knows what to set up.

## Resume Bullet (for reference — don't need to generate this, just keep the project aligned with it)
"Normalized a real-world auto insurance claims dataset (1,000+ records) into a 4-table relational schema in MySQL; wrote 10+ analytical SQL queries (window functions, CTEs) with Python-based analysis to identify fraud-risk patterns across regions, incident types, and demographics."

## Important Setup Note for Claude Code
The dataset requires a Kaggle login to download and can't be fetched via a direct anonymous URL. **Do not attempt to auto-download it.** Instead, tell me (the user) to manually download `insurance_claims.csv` from https://www.kaggle.com/datasets/buntyshah/auto-insurance-claims-data and place it in `data/`, then wait for confirmation before proceeding with the normalization script. If Kaggle API credentials (`kaggle.json`) are already configured on this machine, the `kaggle datasets download` CLI can be used instead — check for that first.

## Constraints
- Keep it runnable end-to-end in under an hour of setup for anyone reviewing it
- Prioritize query quality and README clarity over volume of code
- No need for a web frontend or dashboard — this is a data analysis project, not an app