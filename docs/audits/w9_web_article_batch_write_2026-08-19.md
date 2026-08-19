# W9 First Small Web-Article Batch — Write + Release (2026-08-19)

## Outcome

**PASS (write + reconcile + shown + eligibility).** Eligibility applied
2026-08-19 after Alex approved the proposed 12 KEEP set.

## Active trio (Vlad bylines only)

| # | URL | Queue row | Document | Chunks | Props | Queue accounting |
|---|---|---|---|---|---|---|
| 1 | tenways/ | `2f18306f-…` | `3d261c1d-…` | 3 | 10 | 1/1/0/0 |
| 2 | planted-not-buried… | `c2f52424-…` | `9ab8961a-…` | 3 | 6 | 1/1/0/0 |
| 3 | signs-the-enemy… | `fbcc5a42-…` | `f0450315-…` | 5 | 8 | 1/1/0/0 |

**Batch hard reconcile:** attempted=**3** stored=**3** skipped=**0** errored=**0**.

Staging source `33cfa6b5-…` now has **4** documents (W5 prayer-language + 3).
All new props landed `eligible=false` (expected). Zero quotes written.

## Quarantines

| Row | URL | Disposition |
|---|---|---|
| `fd16372d-…` | intrusive-thoughts… | `needs_attention` — byline **Lana Savchuk**; never cleared/written |
| (never enqueued) | strongholds-in-the-mind… | Also Lana byline; rejected as replacement |

## Visibility

1. Staging flipped `shown` → `hidden` for write window.
2. After writes: Alex chose show-now / eligibility later.
3. Staging flipped **`hidden` → `shown`** (live Vlad unchanged `shown`).
4. `safe_mode=off`; staging `unlicensed` + `shown` → servable under license gate.

## Integrity check (retrieval)

Question: *What does Vlad Savchuk teach about signs the enemy is attacking your mind?*

`match_chunks` top-40: mind-attack doc chunks at ranks **0, 6, 14, 15**
(similarity peak ~0.646). Article is live in retrieval.

Async answer smoke **not** run this pass (retrieval accepted as the light check).

## Artifacts

- Manifest: `docs/audits/w9_web_article_batch_manifest_2026-08-19.md`
- Preview summary: `docs/audits/w9_preview_summary_2026-08-19.json`
- Resume log: `docs/audits/w9_batch_log_2026-08-19.jsonl`
- Eligibility worksheet (all false for now): `docs/audits/w9_eligibility_worksheet_2026-08-19.json`
- Scripts: `scripts/w9_enqueue_batch_2026-08-19.py`, `scripts/w9_preview_batch_2026-08-19.py`

## Eligibility (Alex-approved proposal)

W5 taste pattern. **12 KEEP / 12 DROP** across 24 props. W5 prayer-language
doc left at 4 eligible (unchanged).

| Doc | KEEP | Eligible now |
|---|---|---|
| tenways `3d261c1d-…` | P1–P4 | 4/10 |
| planted `9ab8961a-…` | P1–P4 | 4/6 |
| mind `f0450315-…` | P1, P3, P4, P5 | 4/8 |

## Still open (non-blocking)

- [ ] Optional async smoke on a teacher-named question for one new article
- [ ] Optional rename away from “Vlad Savchuk (web staging)”
- [ ] CLAUDE.md stack table still names old Groq model (docs hygiene)
