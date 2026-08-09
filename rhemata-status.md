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
- Chunking near-universal (3,595/3,597); `full_text` almost entirely
  missing (58/3,597, supersedes Phase 5 #7's stale "56 present" probe).
- Propositions cover 864/3,597 docs corpus-wide — looks sparse, but the gap
  is concentrated in commentary-type sources excluded by standing policy
  (Precept Austin's `word_study` alone is 2,176 docs); every teacher with
  real curatable material has complete coverage.
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
- "Deliverance from demonic oppression and spiritual warfare" → confirmed
  via `match_stored_position()` that this hits the deliverance
  stored-position topic; returned a real position-backed answer built
  entirely from Savchuk evidence (15/15 citations) — a no-op before today.
  Also found in passing: PLAN.md's Phase 3 item 5 called the
  evidence-injection commit (`eca8070`/`34f6b0b`) "NOT pushed to origin" —
  stale, both are on `origin/main`. Corrected in PLAN.md.
**Rollback (seconds):** flip `visibility` back to `hidden` for the same 3 ids.

**Derek Prince quote extraction + review (2026-08-09, Kimi extraction +
in-session review/approval).** The extractor (migration 086's `pending`
status) actually ran twice: an untracked live test inserted 1 row ~65s
before the "official" logged run started, so the DB's 250 pending rows are
NOT all one batch — **corrects the prior "250 candidates" figure**: only
249 belong to `logs/extract_prince_20260809_080948.log` (249 docs, 0
refusals, 0 errors, 247 unattempted); the 1 untracked row (`bc3f71fd…`)
was left untouched this session (out of scope) and still sits `pending`,
flagged for Alex.

**All 249 logged candidates reviewed this session.** Fresh independent
re-verification (`verify_quote_candidate()` against live chunk content,
not the prior run's stored verdict): 249/249 passed. A full manual
scan — 100% coverage for two failure classes the automated verifier can't
catch, plus genuine side-by-side reading on a ~33% sample — found **10
rejects**: 6 dominated by a verbatim Scripture quotation (risking KJV/NKJV
wording being read as Prince's own voice) and 4 that open/close on an
incoherent dangling fragment. Logged to `quote_verification_log`
(`reviewer_judgment_majority_scripture` / `_incoherent_fragment`), left at
`pending` (schema has no `rejected` state). **The other 239 approved** —
`document_quote_clearance` inserted per document (238 new), then
`status→'approved'` per row through the real DB trigger. Live re-query
confirms: Prince approved = **240** (239 new + 1 pre-existing), system-wide
approved = 241, Prince pending = 11 (10 rejects + the 1 out-of-scope row).
Live on the serving path now. (Mid-review: the first approval attempt on
all 239 failed a CHECK constraint — `approved_at` wasn't set alongside
`approved_by` — logged as `db_trigger_failure`, fixed, retried clean;
accurate history, not noise.) **Recommendation, not a decision:** the
96% pass rate and the fact both defect classes are systematic suggest
adding a "majority-known-Scripture" check and an "unbalanced quote mark"
check to the extractor before re-running against the remaining 247 docs —
Alex's call. Separately: ~80 rows in `quote_verification_log` are dry-run
test noise from before dry-run logging was disabled — don't count them.

**Two flagged findings, not fixed, Alex's call:** (1) **`pending` vs
`draft`** — migration 086 added `pending` for "awaiting human review,"
exactly what `draft` already meant before 2026-08-08's auto-approval change
orphaned it (`create_and_approve_quote()` never creates a `draft` row
anymore) — reusing `draft` looks like the right call in hindsight; two
status values now do the same job. (2) **`quote_source_revisions.passage_text`
snapshot convention** — the Prince extractor stored `passage_text = the
candidate span itself`, not the full chunk `create_and_approve_quote()`
captures, making the DB trigger's own substring check a no-op for these 249
rows (a string is always a substring of itself); harmless here since the
real gate is `verify_quote_candidate()`'s live re-check, but defeats
migration 082's stated snapshot-immutability purpose. Recorded in
CLAUDE.md's Landmines.

**Confirmed this session:** no push to origin from the census, the Kimi
run, or any of this session's DB work; `serving_enabled` untouched; no
teacher other than Prince/Ravenhill/Savchuk/Poonen and no book-type
document touched by any of it.

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
5. **Prince quote batch reviewed 2026-08-09 — 240 approved, live.** Next:
   the 1 out-of-scope row (`bc3f71fd…`); harden extractor before rerun on
   remaining 247 docs (recommended, not decided).
6. **Human review of chapter-boundary proposals** (18 books) before any
   apply/wiring decision — Open Decision #21 still open.
7. **Trail / Brooks one-offs** — review then decide visibility; script still
   uncommitted if not yet landed.
8. Hygiene: #16 feedback→flag keep/kill.
9. Decide `pending` vs `draft` quote-status consolidation (flagged above).
10. Decide `quote_source_revisions.passage_text` snapshot-convention fix
    (flagged above, CLAUDE.md Landmines).

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
