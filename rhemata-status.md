# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-09 (trigger-teeth proof + 239-quote snapshot
determination + full review of the remaining 247-document Prince batch;
Prince non-book curation now complete across all 496 documents). No push to
origin; `serving_enabled` untouched.

**Session close:** `.agents/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**Derek Prince non-book quote curation — COMPLETE, all 496 documents
attempted (2026-08-09).** Two extraction batches (249 docs, then the
remaining 247, after the snapshot fix below), each independently
re-verified against live chunk content and manually screened for the two
defect classes the automated verifier can't catch (majority-verbatim-
Scripture content; incoherent dangling fragments). **Combined: 477
approved** (240 + 237), **20 rejected** (10 + 10, logged to
`quote_verification_log`, left `pending` — schema has no `rejected`
state), **1 untracked pre-run row** (`bc3f71fd…`) still out of scope and
`pending`. Live re-query: Prince `approved`=477, `pending`=21 (20 rejects +
1 untracked), system-wide approved=478. **Coverage gap, stated
explicitly: 476/496 documents have ≥1 approved quote; 20 do not** — each
of those 20's only extracted candidate was one of the 20 rejects.
Extraction reached all 496; approval did not clear all 496.

**Snapshot-capture fix, proven with teeth (2026-08-09).** Last session
flagged that the extractor stored `quote_source_revisions.passage_text` as
just the candidate span, not the full chunk — making the DB trigger's
substring check a no-op. Fixed in commit `4e3a0d1` (now stores
`chunks.content` verbatim). **Proof the fix has real teeth:** a rollback-
only transaction test inserted a completely fabricated quote_text against
a real, cleared document — under the OLD convention (`passage_text` =
`quote_text`) the trigger let it through with no exception; under the
FIXED convention (`passage_text` = real chunk content) the trigger
correctly raised `quotes: quote_text is not an exact substring of its
captured source passage`. Everything rolled back; zero residue confirmed
by a follow-up query for the test marker string.

**The 239 pre-fix approved quotes — determination: do not need
regenerating, Alex's call if he wants the hygiene fix anyway.** Factually,
their snapshots ARE vacuous (passage_text=quote_text trivially self-
matches, so the trigger would validate nothing if it ever re-fired on
these rows). But their underlying correctness was already established
through last session's independent re-verification against LIVE
`chunks.content` via `verify_quote_candidate()` — a real, robust check,
not a rubber stamp, done moments before each approval. The trigger's
"immutable snapshot" purpose only matters for *future* drift (an admin
later editing the source chunk) — not an active capability in this
product today (no chunk-reuse/re-chunk mechanism is enabled). So: content
correctness for these 239 does not depend on the snapshot fix; only their
resistance to a hypothetical future edit does. Regenerating is a cheap,
safe, optional consistency improvement — not fixed this session.

**Batch 2 review (247 candidates, `logs/extract_prince_20260809_160803.log`).**
Same method as batch 1: `verify_quote_candidate()` re-run fresh against
live chunk content for all 247 (247/247 passed), then a full systematic
read of every double-newline candidate (71) plus a regex scan of every
remaining single-paragraph candidate (176) for embedded-quotation spans,
plus a genuine ~17% stratified side-by-side sample — found nothing beyond
the two known classes. **10 rejected**: 6 majority-Scripture (e.g. an
unmarked near-verbatim 1 John 5:6, and two full verses of 1 Thessalonians
5:23 chained together with only connective words of Prince's own), 4
incoherent-fragment (2 dangling open-quote fragments, 1 literal `"..."`
ellipsis, 1 unmarked opener). **237 approved** — `document_quote_clearance`
inserted per document (237 new), then `status→'approved'` through the
real (now-fixed) DB trigger, 237/237 succeeded on first attempt (last
session's `approved_at` bug did not recur).

**Two flagged findings, still not fixed, Alex's call:** (1) `pending` vs
`draft` — two status values doing the same job (`create_and_approve_quote()`
never creates a `draft` row since 2026-08-08's auto-approval change). (2)
The snapshot-capture bug above is now fixed for future writes; the 239
pre-fix rows' snapshots are the residual, addressed above.

**Confirmed this session:** no push to origin; `serving_enabled` untouched;
no teacher other than Derek Prince touched; no book-type document touched.

**Still live (product).** ONE answer path (async; `serving_enabled` TRUE).
Quote rail live. Hidden-teacher visibility flip (Ravenhill/Savchuk/Poonen,
2026-08-09) verified against the real serving path. Position one-hop live
on origin. Book chapter extraction still 8/53; Open Decision #21 not
decided.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at 100-dial.

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- `five_fold_ministry.md` editorial marker — needs Alex.
- 20 Prince documents with zero approved quotes (coverage gap above).

---

## Next

1. **`five_fold_ministry.md` editorial decision.**
2. Async concurrency proof at 100-dial (before speed work).
3. Decide extractor hardening (majority-Scripture + unbalanced-quote-mark
   checks) before any next teacher batch — informed by 20 rejects now,
   not 10. Savchuk/Ravenhill/Poonen are eligible next (unhidden 2026-08-09).
4. Decide the 1 untracked pending row (`bc3f71fd…`).
5. Decide whether to regenerate the 239 pre-fix snapshots (optional
   hygiene, not required — see determination above).
6. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction attempt.
7. **Human review of chapter-boundary proposals** (18 books) — Open
   Decision #21 still open.
8. **Trail / Brooks one-offs** — review then decide visibility.
9. Decide `pending` vs `draft` quote-status consolidation.
10. `jewish_perspectives` drop — needs Alex's explicit approval + a
    dedicated DB-write session.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
