# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-08 (session close: sixteen governance/product
decisions recorded, records-only, zero code/DB changes made by the decisions
themselves).

**Session close:** `.claude/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**This session (2026-08-08, session 2) — recorded sixteen product/architecture
decisions + a quote-curation rescope. Records-only, zero code/DB touched.**
A prior attempt at this exact task (run through Grok, not a reasoning model)
had not landed — PLAN.md showed none of it written. Read PLAN.md/CLAUDE.md/
rhemata-status.md end-to-end plus all `docs/position_papers/` files; found 5
`[EDITORIAL DECISION NEEDED — ALEX]` markers, not 4 — resolved the 4 named
(prosperity, divine healing, prophecy, deliverance) with dated position text
in the papers themselves; `five_fold_ministry.md`'s marker is a genuinely
different, unresolved question (restored-vs-never-ceased five-fold offices)
— left in place, flagged, not guessed at. Closed Open Decisions #9 (merge),
#13 (no dominance-threshold override), #14 (auto re-check + new admin-panel-
notification dependency), #15 (versioning, not replace — the code already
did this; this closes the question rather than reversing a "replace" default
that was never actually recorded anywhere), #17 (20s latency target,
supersedes the 7s figure — its only live occurrence). Recorded CLAUDE.md
Settled decisions #20-27 (dominance-threshold override, refresh trigger,
position versioning, quote-tool admin-only, quotes-on-async-only now
structural since `chat.py`'s deletion, the Manna rename, PA word-study
reintroduction-not-permanent, the two fabricated passages staying out
permanently) — also fixed a self-contradictory sentence in existing Settled
decision #18 that the OD#14/#15 resolution surfaced. Corrected PLAN.md
Phase 1.3's stale "whether to flip" framing: the hidden→visible **policy**
was already settled 2026-08-01 (CLAUDE.md #12); only subset-selection and
execution remain genuinely open, not the underlying decision.

**Mid-session addendum:** Alex tabled quote extraction from all 53
book-type documents indefinitely (`docs/audits/book_structure_diagnostic.md`
— no chapter/body-boundary structure exists anywhere in the schema for
books; the one detector is unwired with 2 documented, unfixed regressions).
Live-DB-confirmed via the `rhemata_readonly_analysis` read-only role
(SELECT-only) that this drops **Andrew Murray out of curation entirely** —
all 10 of his documents are book-type, zero non-book material exists.
Rescoped PLAN.md Phase 4 to **Derek Prince** (496 non-book docs, deepest
bench by far) plus other visible non-book teachers; Doug Kreighbaum keeps a
small non-book slice (5 docs) even though his 4 books stay tabled. Full
teacher-by-teacher counts: PLAN.md Phase 4.

**Skipped, per explicit instruction, not silently dropped:** the sixteenth
decision ("PA sourcing leak downgraded to batched") — the retrieval leak it
describes was already RESOLVED 2026-08-07; recording it as still-open would
have corrupted the record, so it was not written. Reported as a conflict
instead.

**Files touched this session:** `CLAUDE.md`, `PLAN.md`, `rhemata-status.md`
(this file), plus 4 of 6 `docs/position_papers/*.md` files
(`five_fold_ministry.md` and `gifts_of_the_spirit_overview.md` untouched).
`AGENTS.md`, `.gitignore`, `backend/app/services/answer_toolbox.py`, and
`scripts/test_commentary_answer_exclusion.py` were **deliberately left
alone** — out of scope for a records-only session and not part of what Alex
asked to be committed; their pre-existing uncommitted state (from the prior
Precept Austin fix session) is unchanged. Two commits made: (1) `PLAN.md` +
`CLAUDE.md` + `rhemata-status.md` — the latter two also carry forward the
Precept Austin fix documentation that was already sitting uncommitted in
them; (2) the 4 resolved position papers.

**Prior sessions (2026-08-07/08, session 1) — condensed.** `chat.py`/
`producer.py` mirror-unification re-verified intact (zero drift). Precept
Austin "citable author" leak closed same-day: `is_commentary_chunk()` now
hard-excludes `source_kind="word_study"` (Precept Austin's only kind), not
just `"commentary"` — live-confirmed 33/67→0 retrieved PA chunks on the
reproduction question. Quote-rail human-approval removed (migration 085,
tightened `quote_verifier.py`) — full detail: CLAUDE.md Settled decisions
#18/#19. Full narrative for both: git log (`4557e5c`/`e223c98`,
`0cfffd0`/`4cc5484`) and CLAUDE.md's Landmines/Settled-decisions sections.

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
  (Murray out — see above).
- **Position papers:** fence + exclusion + disclaimer fallback; 4 of the 5
  found editorial gaps now resolved with dated house positions.
- **Position layer one-hop:** matcher only; injection sequence open; refresh
  trigger + versioning policy now both decided (CLAUDE.md #21/#22), neither
  built yet.
- **Corpus:** props backfill complete; book chapters 8/53; counts query live.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at scale.

- **#13** `ingest_helloao.py` unconverted (only remaining chokepoint script).
- Guest→account, auth CTAs, v4 props prompt, **#14 apply** (prep done —
  renames + `jewish_perspectives` DROP still need Alex), SP residuals, Hebrew
  lexicon grant, Lewis/Tolkien/Wilson mistag, embedded third-party quote
  spans.
- **Phase 1.3 subset/execution** still open (policy settled 2026-08-01;
  inventory done; corrected framing this session — see PLAN.md).
- **Admin-panel notifications** — new build dependency (CLAUDE.md #21;
  PLAN.md Horizon item 4) with no design yet.
- **`five_fold_ministry.md`'s editorial marker** — unresolved, distinct
  question (restored vs. never-ceased offices); needs Alex's call.

---

## Next

1. **`five_fold_ministry.md` editorial decision** — the 5th marker this
   session found but didn't guess at.
2. **One-hop injection** (Opus-shaped, not mechanical): lookup position by
   key → feed PROPOSITIONS only into hardened answer path → review /
   concurrency / rollout. Matcher is ready; wiring is not.
3. Async concurrency proof at 100-dial (before any speed-optimization work,
   per this session's 20s-target decision).
4. Phase 1.3 **subset/execution** (Ravenhill/Savchuk/Poonen — which subset,
   never sentinel; policy itself is no longer the open part).
5. **#14 apply** when Alex says rename / drop / both — use
   `docs/audits/plan14_housekeeping_prep_2026-08-07.md` as the checklist.
6. **Quote curation — Derek Prince specifically** (rescoped this session;
   Murray is out, all-book with zero non-book material). See PLAN.md Phase 4
   for the full visible-teacher non-book breakdown.
7. Hygiene: #13 helloao; #16 feedback→flag keep/kill.
8. If Alex wants real confidence in the queue+worker path at scale, a
   controlled run against a connection pool that isn't capped at 15 would
   close the "not fully proven" gap above.

SP: next #43 mobile sheet. Pass B: remount `UsageRing` in drawer.
