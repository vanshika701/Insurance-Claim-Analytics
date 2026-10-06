# Interview Notes — AI Claims Investigator Copilot

Plain-English build log for the MCP/ML/RAG extension. Written phase by phase. This is
separate from the root `INTERVIEW_NOTES.md`, which covers the original SQL/Python analysis.

Required talking points this file must cover (tracked here as they're answered):
- [x] Why MCP instead of plain function calling — see Phase 0/4.
- [ ] Chunking strategy — Phase 3.
- [ ] Embedding model choice — Phase 3.
- [ ] Why hybrid search — Phase 3.
- [ ] How SQL injection/abuse is prevented — Phase 4.
- [ ] How data leakage was avoided in the model — Phase 2.
- [ ] Why results on a 1,000-row dataset should be interpreted cautiously — Phase 2/7.

---

## Phase 0 — Audit and plan

**What was built:** nothing user-facing yet — this phase was reconnaissance. Confirmed the
existing schema/queries/notebook still work, confirmed MySQL is reachable with the existing
`.env`, confirmed the installed `mcp` SDK version, and set up progress tracking.

**Why each choice was made:**
- *Checked the MCP SDK version before writing a line of server code.* The brief required
  this explicitly, and it immediately mattered: `mcp==2.3.0` renamed `FastMCP` to
  `MCPServer`. Importing `mcp.server.fastmcp.FastMCP` from memory would have crashed
  Phase 4 with a confusing error. The installed package's own error message named the
  exact replacement import and a migration-guide URL — reading that over guessing saved a
  debugging cycle.
- *Checked MySQL reachability rather than assuming SQLite was needed.* It was reachable, so
  no fallback database had to be built this phase — but the Phase 1 design still supports
  both backends via an env var, because a demo/evaluation environment (a grader's laptop, a
  CI runner) won't have this project's MySQL user configured.
- *Separate `requirements-copilot.txt` instead of extending the existing `requirements.txt`.*
  The brief says not to modify existing analysis files. Pinning new, fairly heavy
  dependencies (torch, chromadb, xgboost) into the original file would also make the
  original SQL/Python project look like it needs a GPU stack to run, which it doesn't.

**Alternatives considered and rejected:**
- *Skip the SDK version check and write FastMCP code from memory.* Rejected — the brief's
  ground rule 4 explicitly forbids this, and it would have failed on the first import.
- *Force everything onto SQLite from the start* (simpler, no credentials). Rejected for this
  phase because the existing MySQL setup works and is what the rest of the repo already
  uses; forcing a migration would contradict "do not modify existing analysis files" in
  spirit even if not in name. Dual-backend support is the compromise.

### Likely interview questions

**Q: Why build an MCP server instead of just writing Python functions and calling them
directly from your own code?**
A: Two different jobs. Direct function calls work when *you* control the caller. An MCP
server is for when the caller is an LLM client you don't control — Claude Desktop, another
agent, an eval harness — connecting over a standard protocol (stdio here) without needing
your source code imported into its process. It also gives you one boundary where you can
enforce guardrails (read-only SQL, row limits, timeouts) regardless of which client calls
in, and the same server can be driven by a human in Claude Desktop and by an automated
`pytest`/eval client with zero code duplication — which is exactly how Phase 6 evaluates it.

**Q: You said you "checked the SDK version" — why does that matter so much?**
A: Because APIs change between major versions and I'd rather find that out from an import
error in development than from a confusing failure during a demo. Concretely here: the
class I was told to use, `FastMCP`, doesn't exist in `mcp==2.3.0` — it's `MCPServer` now.
Writing code from a 9-months-stale mental model of the SDK would have produced code that
imports successfully in my head and fails the moment it's run.

**Q: Why not just use SQLite from the start and skip MySQL entirely?**
A: The original analysis project is built around MySQL and that's what's already running
and populated. Ripping it out to "simplify" would be solving a problem that doesn't exist
and would contradict the instruction to leave the existing analysis alone. Supporting both
backends behind one small `db.py` module costs little and buys portability — anyone running
this without MySQL configured (a reviewer, a CI job) still gets a working database.
