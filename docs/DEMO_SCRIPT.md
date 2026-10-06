# Demo Script — AI Claims Investigator Copilot

Three example investigation prompts to run live in Claude Desktop once the server is
connected (see [Claude Desktop setup](#claude-desktop-setup) below). Each is chosen to
exercise a different tool, or a combination.

## 1. "Is this claim suspicious? Check it against the guidelines and explain."

> **Prompt:** "Look at claim 1 in the database. Is it suspicious? Score its fraud risk,
> explain what's driving that score, and check whether our anti-fraud policy guidelines
> say anything relevant about how a claim like this should be handled."

**What happens:** Claude calls `get_schema` (if it hasn't already), `score_claim(1)` (gets
a probability, a risk band, the top SHAP features, and whether the simple "flag all Major
Damage" rule would flag it), and `search_guidelines` for something like "anti-fraud policy
claim investigation requirements" — returning a cited passage from the IRDAI guidelines
about the Board-approved Anti-Fraud Policy and the Fraud Monitoring Committee's role.
Claude then combines the model's explanation with the regulatory citation into one answer.

## 2. "Which claims should we prioritize for investigation this week?"

> **Prompt:** "I can only investigate a handful of claims this week. Using the database,
> find the claims most worth investigating, and tell me why — I want both the data-driven
> reasoning and the actual rule I should be following."

**What happens:** Claude writes a `run_query` SELECT (e.g. filtering
`incident_severity = 'Major Damage'`, possibly ordered or limited), explains the 28%
claims / 68% fraud finding from `results/model_metrics.json`/`ANALYSIS.md`, and can
`score_claim` on a few specific ids from that result set to show the SHAP explanation
per claim. This demonstrates `run_query`'s guardrails in the background — if Claude ever
drafts a query with too high a `LIMIT` or something structurally wrong, it gets a plain
error back and retries, which is worth narrating during the demo.

## 3. "What does California require if we outsource fraud investigation to a TPA?"

> **Prompt:** "We're thinking about outsourcing some claims fraud investigation to a
> third-party administrator licensed in California. What does the regulatory guidance say
> we're required to do?"

**What happens:** Pure `search_guidelines` call against the California DOI SIU Annual
Report corpus — returns cited passages (with page numbers) about TPA/MGA written
procedures, anti-fraud orientation timelines (90 days), and quality-control requirements.
No database or model tool needed here, which is useful to show the server doesn't force
every question through the same tool.

---

## Claude Desktop setup

Config file location:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add (or merge into an existing `mcpServers` object):

```json
{
  "mcpServers": {
    "claims-investigator-copilot": {
      "command": "/absolute/path/to/Insurance Claim Analytics/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/Insurance Claim Analytics"
    }
  }
}
```

On Windows, use the venv's `python.exe` and Windows-style paths, e.g.:
```json
{
  "mcpServers": {
    "claims-investigator-copilot": {
      "command": "C:\\path\\to\\Insurance Claim Analytics\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "C:\\path\\to\\Insurance Claim Analytics"
    }
  }
}
```

Notes:
- `cwd` matters because `python -m mcp_server.server` needs the project root on
  `sys.path`; if your Claude Desktop version doesn't support `cwd`, set
  `"env": {"PYTHONPATH": "/absolute/path/to/Insurance Claim Analytics"}` instead.
- Use the **venv's** Python (the one with `requirements.txt` +
  `requirements-copilot.txt` installed), not the system Python.
- Before first connecting, make sure the one-time setup has run: MySQL populated (or
  `DB_BACKEND=sqlite` + `python -m copilot.build_sqlite`), `python -m copilot.train_model`,
  and `python -m rag.build_index`. See the README's Copilot section for the full sequence.
- Restart Claude Desktop after editing the config.
