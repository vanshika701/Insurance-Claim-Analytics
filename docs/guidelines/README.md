# Guideline documents

Real, public documents, downloaded and indexed for the RAG layer (`rag/`). Both have
substantive extractable text (verified with `python -m rag.parse`) and are tracked in git
so the corpus is reproducible without re-downloading.

| File | Source | Pages w/ text |
|---|---|---|
| `irdai_fraud_monitoring_guidelines_2025.pdf` | Insurance Regulatory and Development Authority of India (IRDAI), *(Insurance Fraud Monitoring Framework) Guidelines, 2025*, Ref: IRDAI/IID/GDL/MISC/112/10/2025, dated 9 Oct 2025. | 13 |
| `ca_doi_siu_annual_report_sample.pdf` | California Department of Insurance, Fraud Division — *SIU Annual Report* sample/template (the report every licensed insurer's Special Investigative Unit must file). | 20 |

A third candidate, a 1-page California DOI fraud-division infographic, was downloaded but
dropped — too little extractable text (538 characters) to be a useful retrieval source.

## Sources attempted and blocked

Several other well-known documents (the NAIC *Insurance Fraud Prevention Model Act*,
NAIC's *Antifraud Plan Guideline*) were found via search but `content.naic.org` serves a
Cloudflare JS challenge to non-browser clients, so automated download failed (confirmed
both with `curl` and with the WebFetch tool — same block). **Needs my action, optional:**
if you want the NAIC model act in the corpus, download it yourself from a browser at
<https://content.naic.org/sites/default/files/inline-files/MDL-680.pdf> and drop it in
this folder, then re-run `python -m rag.build_index`. Not a blocker — the two documents
above are a sufficient real corpus for Phase 3/6.

## Rebuilding the index

```bash
python -m rag.build_index
```
Regenerates `docs/guidelines/chroma/` (gitignored, regenerable) from whatever PDFs are in
this folder.
