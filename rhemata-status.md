# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-09 (session close — Derek Prince non-book quote
extraction to pending; 250 candidates inserted, 249 of 496 docs covered).

**Session close:** `.agents/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**This session (2026-08-09) — Derek Prince quote-candidate pipeline.** Built
and committed:

- `migrations/086_quote_pending_status.sql` + `scripts/apply_migration_086.py`:
  add `'pending'` to `quotes.status` so machine-extracted candidates can await
  review without being served.
- `scripts/extract_quote_candidates_derek_prince.py`: deterministic sentence-
  window extraction scoped to Derek Prince non-book material (`source_type !=
  'book'`, `source_kind != 'commentary'`). Runs the existing
  `quote_verifier` unchanged and inserts passing candidates as `pending`.
  Refusals are logged to `quote_verification_log` via `_log_quote_decision`.

**Live DB result:** 250 new Derek Prince rows in `quotes` with
`status='pending'`, spread across 249 of 496 documents. 0 rows approved.
0 other teachers touched. Log path:
`logs/extract_prince_20260809_080948.log`.

**Still live (product).** ONE answer path (async; `serving_enabled` TRUE).
Quote rail live; books tabled for quote extraction. Position one-hop live on
origin. Book chapter extraction still 8/53; Open Decision #21 still **not
decided**.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at 100-dial.

- Guest→account, auth CTAs, v4 props, **#14 drop `jewish_perspectives`**,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Phase 1.3 subset/execution still open.
- Admin-panel notifications — dependency of refresh (CLAUDE.md #21); no design.
- `five_fold_ministry.md` editorial marker — needs Alex.

---

## Next

1. **`five_fold_ministry.md` editorial decision.**
2. Async concurrency proof at 100-dial (before speed work).
3. Phase 1.3 subset/execution (Ravenhill/Savchuk/Poonen).
4. **#14 drop `jewish_perspectives`** when Alex says so.
5. **Review/approve Derek Prince pending quotes** (250 candidates waiting; requires `document_quote_clearance`).
6. **Human review of chapter-boundary proposals** (18 books) before any
   apply/wiring decision — Open Decision #21 still open.
7. **Trail / Brooks one-offs** — review then decide visibility; script still
   uncommitted if not yet landed.
8. Hygiene: #16 feedback→flag keep/kill.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
