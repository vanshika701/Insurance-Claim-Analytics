# Resume Bullets — Insurance Claims Fraud Analytics & AI Copilot

Every number below is pulled directly from `results/model_metrics.json` and
`results/retrieval_metrics.json`, or from counts verified in this build (tests passing,
query/tool counts). None are estimated.

```latex
\resumeItem{Normalized a 1,000-row insurance dataset into a 4-table MySQL/SQLite schema and wrote 10 SQL queries (window functions, CTEs) isolating a fraud driver with 68\% recall at 61\% precision.}
\resumeItem{Validated the SQL finding with 5-fold cross-validated XGBoost and logistic regression models, honestly reporting neither beat the rule-based baseline (F1 0.585-0.591 vs 0.637) while a feature sensitivity test caught a dataset leak inflating ROC-AUC from 0.76 to 0.864.}
\resumeItem{Built an MCP server exposing 4 tools (schema introspection, SQL-guarded querying, SHAP-explained fraud scoring, hybrid RAG search) over real regulatory PDFs, backed by an AST-based SQL guard verified against 19 injection/bypass attempts.}
\resumeItem{Shipped a 47-test pytest suite plus an MCP-client evaluation harness measuring retrieval quality (hit@5 1.00 BM25, 0.95 hybrid, 0.85 vector-only) across 20 citation-grounded questions, and diagnosed a cross-library native-runtime crash to a process-isolation fix.}
```

**Plain text:**
- Normalized a 1,000-row insurance dataset into a 4-table MySQL/SQLite schema and wrote 10 SQL queries (window functions, CTEs) isolating a fraud driver with 68% recall at 61% precision.
- Validated the SQL finding with 5-fold cross-validated XGBoost and logistic regression models, honestly reporting neither beat the rule-based baseline (F1 0.585-0.591 vs 0.637) while a feature sensitivity test caught a dataset leak inflating ROC-AUC from 0.76 to 0.864.
- Built an MCP server exposing 4 tools (schema introspection, SQL-guarded querying, SHAP-explained fraud scoring, hybrid RAG search) over real regulatory PDFs, backed by an AST-based SQL guard verified against 19 injection/bypass attempts.
- Shipped a 47-test pytest suite plus an MCP-client evaluation harness measuring retrieval quality (hit@5 1.00 BM25, 0.95 hybrid, 0.85 vector-only) across 20 citation-grounded questions, and diagnosed a cross-library native-runtime crash to a process-isolation fix.

## Where each number comes from

| Number | Source |
|---|---|
| 1,000-row, 4-table, 10 SQL queries | original analysis (`db/schema.sql`, `queries/analysis_queries.sql`) |
| 68% recall / 61% precision | `ANALYSIS.md` F1-F2 (the "flag all Major Damage" rule) |
| F1 0.585 (XGBoost) / 0.591 (logistic) / 0.637 (baseline) | `results/model_metrics.json` → `cv_metrics.*.f1.mean` |
| ROC-AUC 0.76 → 0.864 | `results/model_metrics.json` → `cv_metrics.xgboost.roc_auc.mean` vs `hobbies_sensitivity_check.cv_metrics.xgboost.roc_auc.mean` |
| 4 MCP tools | `mcp_server/server.py` |
| 19 injection/bypass cases | `tests/test_sql_guard.py` (`SHOULD_BLOCK`) |
| 47 tests | `pytest tests/ -q` output |
| hit@5 1.00 / 0.95 / 0.85, 20 questions | `results/retrieval_metrics.json` |
| cross-library crash → process isolation | `docs/INTERVIEW_NOTES.md` Phase 4 |

If you only have room for one bullet in a shorter resume format, use the second one (the
model validation) — it's the single strongest signal of judgment: building a model *and*
reporting that it didn't beat a simpler baseline, plus catching a data leak, is more
senior than any accuracy number alone would be.
