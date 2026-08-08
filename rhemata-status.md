# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-08 (session close: quote-rail sub-chunk exclusion
Müller gap closed, PLAN.md Phase 4 entry collapsed per Standing Rule 13).

**Session close:** `.claude/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**This session (2026-08-08, quote-rail sub-chunk exclusion gap-close).**
Closed the inline Müller quotation gap in the quote verifier. Added
`muller_inline_quotation` detector to `backend/app/services/quote_subchunk_exclusion.py`
(scoped to chunks mentioning "Muller", firing on long/all-caps single-quoted
paragraphs), expanded regression tests in `scripts/test_quote_verifier.py`
to cases 14–25 (25/25 passing), and documented residual risks (cross-chunk
catechism continuation; `:—`/`writes:` false-exclusion) in
`scripts/dry_run_subchunk_exclusion.py`. PLAN.md Phase 4 entry collapsed to
a single DONE line per Standing Rule 13. Two commits already made: `ca984cb`
(build), `c0c34c7` (docs). No DB writes this session.

**Prior sessions (2026-08-08, sessions 1-3; condensed — full detail: git
log + PLAN.md/CLAUDE.md).** Sixteen governance/product decisions recorded
(position-layer governance, quote-rail scope, Manna rename — CLAUDE.md
Settled decisions #20-27); 4 of 6 position-paper editorial markers
resolved, `five_fold_ministry.md`'s left open for Alex. Quote-rail human
approval removed (migration 085). Precept Austin word-study leak closed
(`is_commentary_chunk()` now excludes `source_kind="word_study"`).
`chat.py` deleted — async is the only answer path, `serving_enabled` TRUE.
`ingest_helloao.py` converted to route through `shared_ingest`, Phase 5 #13
closed.

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
  (Murray out). Sub-chunk exclusion (translator footnotes, block quotes,
  catechism Q&A sharing a chunk with real teacher material) landed this
  session window via a separate commit (`a2f4573`/`6dba89a`, not this
  session's own work — PLAN.md Phase 4 already reflects it).
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
