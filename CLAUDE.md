# CLAUDE.md — Working Agreement for This Project

This file defines how Claude Code must work on the **Insurance Claims Analytics (SQL + Python)** project.
The full project brief lives in [README.md](README.md) (it is currently a brief; it will be rewritten into a
proper README as the final step). Follow the brief for *what* to build; follow this file for *how* to work.

## 1. Keep the user in the loop — always

- **After completing any step, feature, or task, stop and report back to the user before moving on.**
  Summarize: what was done, what the result was, what comes next. Wait for confirmation on anything
  non-trivial or ambiguous.
- Do not chain multiple major steps (schema → data → queries → analysis) silently. One step, then check in.
- Before destructive or hard-to-reverse actions (dropping tables, rewriting files, force-installing
  software, committing), explain first and get a go-ahead.
- If MySQL / credentials / environment decisions are needed, ask — never assume defaults.

## 2. Maintain two running logs continuously

Two files are kept up to date at every step. They have different jobs — do not merge them.

### 2a. [EXPLANATION.md](EXPLANATION.md) — the process journal

- **At every step**, append a new dated entry. Never overwrite earlier entries — this is a chronological journal.
- Each entry should cover, as relevant:
  - **What we are analysing / building** in this step and why.
  - **Insights found** — concrete findings from the data or queries (numbers, patterns, anomalies).
  - **Difficulties faced** — bugs, environment issues, data-modeling tradeoffs, and how they were resolved.
  - **Decisions made** — schema choices, assumptions, parameters (e.g. "5% of claims seeded as suspicious").
  - **Next step**.
- Keep it readable by a recruiter or interviewer — it doubles as the story behind the project.

### 2b. [ANALYSIS.md](ANALYSIS.md) — the insights log (analyst / solution-associate voice)

- Whenever a query, chart, or check surfaces a **business insight**, add a numbered finding
  (F1, F2, …) using the file's template: **Finding** (with numbers) → **So what** →
  **Recommended action** → **Confidence & caveats**.
- This file is about *conclusions a stakeholder would care about*, not how we got there.
- Write it as if briefing an insurance client: fraud risk, loss ratios, regional patterns,
  process bottlenecks, demographic skews. Always quantify. Always note sample size / caveats.

## 3. Remind the user to push after every small feature

- After **each small, self-contained piece of work** (e.g. schema written, data generator done, one batch
  of queries, analysis notebook section, README), explicitly remind the user:
  **"This is a good point to commit and push to GitHub."**
- Suggest a concrete commit message and the exact commands, but **do not run `git commit` or `git push`
  yourself unless the user says to.**
- Aim for the intentional, incremental commit history described in the brief:
  data generation → schema → queries → analysis → README.

## 4. General conventions

- Never hardcode credentials. Use `.env` (git-ignored) and keep `.env.example` current.
- Keep the project runnable end-to-end in under an hour by a reviewer.
- Prioritize SQL query depth (window functions, CTEs, subqueries) and README clarity over code volume.
- Update `requirements.txt` whenever a new dependency is introduced.
