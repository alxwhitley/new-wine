# W5–W6 Write Reconciliation — Savchuk web article (2026-08-19)

## Identifiers

| Item | Value |
|---|---|
| Queue row | `85962adf-f4d6-440a-bd32-de414dbc4605` |
| Staging source | `33cfa6b5-ae98-4c68-a41a-e1db52914546` — **Vlad Savchuk (web staging)** — `unlicensed` + `hidden` |
| Live Vlad Savchuk | `74ed5fa1-9aac-4997-87ec-4be6724b49bd` — **unchanged** `visibility=shown` |
| Document | `c97533db-7b48-46ec-b77f-239b703b8697` |
| Preview report | `source_ingest_preview_review/1126b236e0bff0a3724618abf95595b322792c26848d946990bc9dfd0bf3e553.json` |
| Queue URL | `https://pastorvlad.org/how-to-develop-your-prayer-language-in-private/` |
| Captured final URL | path retained Mailchimp suffix from site response |

## First-write accounting (reconciled)

| Metric | Count |
|---|---|
| attempted_documents | **1** |
| stored_documents | **1** |
| skipped_documents | **0** |
| errored_documents | **0** |
| chunks | **4** |
| propositions | **12** (all `eligible=false`, all `model=openai/gpt-oss-120b`, provenance stamped) |
| quotes written | **0** |
| quote_source_revisions | **0** |

Document: `source_kind=web_article`, `citation_mode=citable`, `source_type=article`, on staging source only.

**Retrievability:** staging `visibility=hidden` → article is **not** admitted by the license/visibility gate (confirmed). Live Savchuk corpus untouched.

## Model swap (required for write)

Groq `llama-3.3-70b-versatile` returns 404 on the current API key (only non-Llama chat models available). Alex approved swapping:

- `scripts/propositions.py` `EXTRACTION_MODEL` → `openai/gpt-oss-120b`
- `backend/app/services/metadata.py` `GROQ_MODEL` → `openai/gpt-oss-120b`

`answer_toolbox.py` query-expansion model **not** changed this pass (answer path; separate decision).

## Idempotency

Reset queue to `waiting` + `cleared_to_run=true` and re-ran:

```text
scripts/source_ingest_worker.py --once --row-id 85962adf-f4d6-440a-bd32-de414dbc4605
```

Result: `stored=0`, `skipped=1`, no second document; chunks stayed 4; propositions stayed 12. **Proven.**

Queue accounting afterward restored to first-write truth; idempotency evidence kept in `notes`.

## Row-level rollback procedure (documented; not executed)

Keep the article for eligibility review. To roll back later:

1. Export snapshot:
   `python3.12 scripts/export_restore_document.py export --document-id c97533db-7b48-46ec-b77f-239b703b8697`
2. Delete footprint (9-table cascade via existing tool):
   `python3.12 scripts/export_restore_document.py delete --document-id c97533db-7b48-46ec-b77f-239b703b8697`
3. Optionally restore from the JSON snapshot with `restore`.
4. Leave staging source `hidden` (or delete staging source/alias only after no docs remain).
5. Do **not** flip live Vlad Savchuk.

Footprint if deleted now: 1 document, 4 chunks, 12 propositions, 48 `proposition_chunks` links.

## Eligibility + visibility (same session)

- Alex taste-pattern from the live article → **KEEP P1, P3, P7, P12** only
  (`docs/audits/w5_savchuk_eligibility_review_2026-08-19.md`).
- Reconcile: 12 props / **4 eligible=true** / 8 false.
- Staging source flipped **hidden → shown** (Alex). Live Savchuk unchanged.
- `safe_mode=off`; `is_source_servable(staging)=True`.
- Retrieval probe (`match_chunks`, question “How do I develop my prayer language
  in private?”): all 4 article chunks in top 50 (ranks ~2, 3, 6, 7).

## Still open

- [ ] Full answer-integrity smoke via async `/async-chat` (citations naming
  “Vlad Savchuk (web staging)” — awkward speaker label still present).
- [ ] CLAUDE.md stack table still names `llama-3.3-70b-versatile` — update on
  docs commit.
- [ ] Optional rename of staging source display / speaker attribution so answers
  don’t say “Vlad Savchuk (web staging)”.

## Preview quirks carried forward

- Proposition speaker text uses **Vlad Savchuk (web staging)** because `attribute_to` is the staging source name.
- Preview used stub metadata then live gpt-oss extraction; write used live metadata + gpt-oss (12 props vs preview’s 9 — model non-determinism / full write path).
