# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-08 (session close: `ingest_helloao.py` converted to
`shared_ingest`, Phase 5 #13 closed).

**Session close:** `.claude/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**This session (2026-08-08, session 3) — Phase 5 #13 closed.**
`ingest_helloao.py` now routes through `shared_ingest.ingest_document()`,
mirroring `ingest_preceptaustin.py`/`ingest_lexicon.py` (chunk_fn override
for one-chunk-per-verse; direct psycopg2/propositions calls dropped; added
`--dry-run`). Verified per standing session rules 2/3: dry-run → a real
single-item write (Adam Clarke/Genesis ch.1, isolated throwaway title,
independently confirmed in the DB — 19 chunks, correct headers, resolved
source_id, `propositions: skipped_licensed` — then deleted, cascade
confirmed) → a full unfiltered batch (`attempted=198 stored=0 skipped=198
failed=0`), reconciled against the live DB (186 HelloAO documents unchanged,
0 stray rows). Two commits: `929bc34` (build), `e91f5bb` (docs).

**Finding, not a bug:** the 0-stored batch result is real. PLAN.md's
Ongoing #27 had claimed "8 further [HelloAO books], content ready" —
false. All 12 currently-missing HelloAO book/commentary combinations (1
Matthew Henry, 10 Adam Clarke, 1 Jamieson-Fausset-Brown — all `Song of
Solomon`, plus a scattered Adam Clarke set) have no verse-level commentary
at the HelloAO API for those specific books: either a 404, or content that
exists only under a chapter-level `introduction` field this script has
never parsed. Corrected in PLAN.md's Ongoing #27; not fixed — reading
`introduction` needs new parsing/chunking logic (no verse number to key a
chunk on), a separate, unscoped question. Full detail: PLAN.md Phase 5 #13
/ Ongoing #27, CLAUDE.md's resolved Landmine, commit `929bc34`.

**Prior sessions (2026-08-08, sessions 1-2; condensed — full detail: git
log + PLAN.md/CLAUDE.md).** Sixteen governance/product decisions recorded
(position-layer governance, quote-rail scope, Manna rename — CLAUDE.md
Settled decisions #20-27); 4 of 6 position-paper editorial markers
resolved, `five_fold_ministry.md`'s left open for Alex. Quote-rail human
approval removed (migration 085). Precept Austin word-study leak closed
(`is_commentary_chunk()` now excludes `source_kind="word_study"`).
`chat.py` deleted — async is the only answer path, `serving_enabled` TRUE.

**Still not fully proven at scale:** a real queue+worker run previously hit
local connection-pool exhaustion (`:5432` session pooler capped at 15), read
as a local-dev artifact, not a code regression.

**Still live (product).**

- **Answer path:** ONE path (async; chat.py deleted). `serving_enabled` TRUE =
  live and unpaused; pooler :6543 in prod; 100-dial concurrency unproven at
  scale.
- **Project 2 phase 1:** single-teacher lock + debate classifier; lock rarely
  fires.
- **Project 3 quote rail:** the only path now runs it; few approved quotes;
  threshold 0.40; curation next targets Prince + visible non-book teachers
  (Murray out).
- **Position papers:** fence + exclusion + disclaimer fallback; 4 of 5
  found editorial gaps resolved with dated house positions.
- **Position layer one-hop:** matcher only; injection sequence open; refresh
  trigger + versioning policy decided (CLAUDE.md #21/#22), neither built yet.
- **Corpus ingestion:** every document-writing ingest script now routes
  through `shared_ingest` (Phase 5 #13 was the last). Props backfill
  complete; book chapters 8/53; counts query live.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at scale.

- Guest→account, auth CTAs, v4 props prompt, **#14 apply** (prep done —
  renames + `jewish_perspectives` DROP still need Alex), SP residuals, Hebrew
  lexicon grant, Lewis/Tolkien/Wilson mistag, embedded third-party quote
  spans.
- **Phase 1.3 subset/execution** still open (policy settled 2026-08-01;
  inventory done).
- **Admin-panel notifications** — new build dependency (CLAUDE.md #21;
  PLAN.md Horizon item 4) with no design yet.
- **`five_fold_ministry.md`'s editorial marker** — unresolved, distinct
  question (restored vs. never-ceased offices); needs Alex's call.

---

## Next

1. **`five_fold_ministry.md` editorial decision** — the 5th marker a prior
   session found but didn't guess at.
2. **One-hop injection** (Opus-shaped, not mechanical): lookup position by
   key → feed PROPOSITIONS only into hardened answer path → review /
   concurrency / rollout. Matcher is ready; wiring is not.
3. Async concurrency proof at 100-dial (before any speed-optimization work,
   per the 20s-target decision).
4. Phase 1.3 **subset/execution** (Ravenhill/Savchuk/Poonen — which subset,
   never sentinel; policy itself is no longer the open part).
5. **#14 apply** when Alex says rename / drop / both — use
   `docs/audits/plan14_housekeeping_prep_2026-08-07.md` as the checklist.
6. **Quote curation — Derek Prince specifically** (Murray is out, all-book
   with zero non-book material). See PLAN.md Phase 4 for the full
   visible-teacher non-book breakdown.
7. Hygiene: #16 feedback→flag keep/kill (Alex's call, not urgent).
8. If Alex wants real confidence in the queue+worker path at scale, a
   controlled run against a connection pool that isn't capped at 15 would
   close the "not fully proven" gap above.

SP: next #43 mobile sheet. Pass B: remount `UsageRing` in drawer.
