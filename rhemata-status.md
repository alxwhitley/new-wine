# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-09 (reconciling a corpus census + Derek Prince
pending-quote run done outside this session, then a live hidden-teacher
visibility flip done in-session).

**Session close:** `.agents/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**Corpus census (2026-08-09, read-only, Grok).** Full report:
`~/rhemata-analysis/corpus_census_2026-08-09.md`. Live-queried, corpus-wide
(3,597 total documents):
- Chunking is essentially universal — 3,595/3,597 documents have ≥1 chunk.
- `full_text` is almost entirely missing — only 58/3,597 documents have it
  (3,539 null). Supersedes Phase 5 #7's stale 2026-08-07 "56 present" probe.
- Propositions cover 864/3,597 documents corpus-wide. Looks sparse, but the
  gap is concentrated in commentary-type sources permanently excluded from
  proposition extraction by standing policy (Precept Austin's `word_study`
  alone is 2,176 of the corpus's 3,597 docs) — every teacher with real,
  curatable (non-commentary) material has complete proposition coverage.
- **Derek Prince**: 496 non-book documents, 100% chunked, 100%
  proposition-covered. Before this session, exactly 1 quote existed for him
  anywhere.
- **The three hidden teachers** (Ravenhill 117 docs, Savchuk 126, Poonen 50):
  all three already have full chunk + proposition coverage. Poonen
  additionally has full `full_text` coverage; Ravenhill and Savchuk do not.
  None have any quotes. **Flipped `hidden`→`shown` this session — see below.**

**Hidden-teacher visibility flip (2026-08-09, in-session, DB-only).**
Live re-check before the write matched the 2026-08-09 census exactly for all
three (no drift). `UPDATE sources SET visibility='shown'` for exactly
Ravenhill, Savchuk, Poonen (3 rows, confirmed by rowcount) —
`license_status` (`unlicensed`), `retrievable` (`false`), the sentinel row,
and the other 11 hidden sources were not touched. `safe_mode` is `off`, so
the license gate now admits all three. **Verified against the real serving
path**, not just the DB row — called `producer.produce()` directly (the
exact function the async worker runs) with two real questions:
- "Why does revival tarry" → real answer citing 3 distinct Ravenhill
  documents, correctly attributed (`verified_references` confirms
  `Leonard Ravenhill`).
- "Deliverance from demonic oppression and spiritual warfare" →
  independently confirmed via `match_stored_position()` that this hits the
  `deliverance from demons and spiritual warfare` stored-position topic;
  returned a real position-backed answer built entirely from Savchuk
  evidence (15/15 citations `Vlad Savchuk`) — this topic was a no-op before
  today (its sole evidence source was hidden). Also surfaced in the same
  pass: PLAN.md's Phase 3 item 5 said the evidence-injection commit
  (`eca8070`/`34f6b0b`) was "NOT pushed to origin" — that was stale; both
  are confirmed on `origin/main`. Corrected in PLAN.md.
**Rollback, if needed (seconds):** flip `visibility` back to `hidden` for
the same 3 source ids; nothing else to undo.

**Derek Prince pending-quote extraction (2026-08-09, Kimi).**
`scripts/extract_quote_candidates_derek_prince.py` (migration 086 added
`quotes.status='pending'`) inserted 250 candidates at `status='pending'`
across 249 of his 496 non-book documents — 247 unprocessed because the run's
250-quote ceiling was hit first. 0 verifier refusals, 0 errors. **Not
cleared for serving** — a future review session must add
`document_quote_clearance` rows and flip status to `approved` (DB gates
unchanged) before any reach users. Log: `logs/extract_prince_20260809_080948.log`
(gitignored).

**Known artifact, not a real signal:** ~80 early accepted-candidate rows
landed in `quote_verification_log` during dry-run testing, before dry-run
logging was disabled (current script only `logger.info`s to console on
`--dry-run`, confirmed at `extract_quote_candidates_derek_prince.py:392-402`
— no `_log_quote_decision` call in that branch). Those rows are test noise,
not real decisions; don't count them in any quote-rail accounting.

**Open flag, not resolved — `pending` vs `draft`.** Migration 086 added
`quotes.status='pending'` for "verified, awaiting human review" candidates.
The pre-existing `draft` status (migration 082's original design, "status is
draft/approved/revoked") meant exactly this before 2026-08-08's
auto-approval change orphaned it — `create_and_approve_quote()`'s docstring
confirms no code path creates a `draft` row anymore. Reusing `draft` looks
like it would have been the right call; adding `pending` instead leaves two
status values doing the same job. Recorded in PLAN.md as a flagged cleanup
item — not fixed this session, Alex's call.

**Confirmed this session:** no push to origin from either the census or the
Kimi extraction run; `async_answer_config.serving_enabled` untouched; no
teacher other than Derek Prince and no book-type document touched by either.

**Still live (product).** ONE answer path (async; `serving_enabled` TRUE).
Quote rail live; books tabled for quote extraction. Position one-hop live on
origin. Book chapter extraction still 8/53; Open Decision #21 still **not
decided**.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at 100-dial.

- Guest→account, auth CTAs, v4 props, **#14 drop `jewish_perspectives`**,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Phase 1.3: 3 of 14 hidden sources flipped (Ravenhill/Savchuk/Poonen, above).
  11 remain hidden by design (sentinel + 10 empty shells, nothing to flip).
- Admin-panel notifications — dependency of refresh (CLAUDE.md #21); no design.
- `five_fold_ministry.md` editorial marker — needs Alex.

---

## Next

1. **`five_fold_ministry.md` editorial decision.**
2. Async concurrency proof at 100-dial (before speed work).
3. Quote curation for Ravenhill/Savchuk/Poonen — now unhidden and eligible,
   not yet started (Prince curation remains the active thread).
4. **#14 drop `jewish_perspectives`** when Alex says so.
5. **Review/approve Derek Prince pending quotes** (250 candidates waiting;
   requires `document_quote_clearance`). Re-run the extractor with a higher
   ceiling for the remaining 247 docs once this batch clears.
6. **Human review of chapter-boundary proposals** (18 books) before any
   apply/wiring decision — Open Decision #21 still open.
7. **Trail / Brooks one-offs** — review then decide visibility; script still
   uncommitted if not yet landed.
8. Hygiene: #16 feedback→flag keep/kill.
9. Decide `pending` vs `draft` quote-status consolidation (flagged above).

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
