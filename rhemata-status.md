# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-10 (O3 harness build committed on its own branch,
worktree, not merged to main; no coordinator run loop exists yet). No push
to origin; `serving_enabled` untouched.

**Session close:** `.agents/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**O3 (durable queue/resume/retry/quarantine/fallback/reconciliation harness)
— decision layer built, tested, reviewed; coordinator run loop NOT built
(2026-08-10).** Work happened entirely in
`.worktrees/o3-queue-resume-quarantine`, branch
`codex/o3-queue-resume-quarantine` — never merged, never pushed; main's own
checkout is untouched. Three commits on that branch: `463650e` (prior
checkpoint: P1 contracts, P2 durable store, P3 scheduler), `1051755`
(this session: P3-runtime-transitions + P4 reconciliation/replay + 3
integration-gate fixes), `d22c4ab` (docs: PLAN.md's O3 entry, on that
branch only — main's `PLAN.md` still shows O3 unstarted until merge).
391 harness self-tests passing (168 pre-existing O2 + 223 new O3). 21
independent Opus review rounds across the whole build (P1 ×4, P2 ×3,
P3-scheduler ×2, P3-runtime ×5, P4 ×5, final integration gate ×2), every
round found and fixed real defects — never a rubber stamp. Built via Kimi
until confirmed quota-exhausted (401 Insufficient Balance), then Sonnet 5
as the pre-authorized fallback worker; Grok was not invoked (no access in
this environment — recorded honestly, not fabricated).

**What's real:** durable journal (position-based torn-tail recovery, no
silent repair), deterministic packet scheduling, dependency BLOCKED→READY
promotion logic, crash-safe fold/recovery (all 3 documented crash points +
idempotent double-restart), retry classification with a 4-guard
provider-exhaustion confirmation (a fabricated exhaustion signal is
provably rejected), quarantine isolation (one bad packet never blocks
independent ready ones), and a morning reconciliation report + read-only
replay CLI — genuinely correct and adversarially tested (~90 named
fixtures), all of it inert until something drives it live.

**What's missing, stated plainly — no coordinator main loop exists
anywhere in this repo.** Nothing enrolls a packet or invokes a real
worker; `queue.json`, a per-packet state cache, terminal seals, and
reassignment records have no writer; `invoke.py` from the original design
sequencing was never built. Concretely demonstrated: with no seal writer,
dependency promotion can never actually fire in this build — now surfaced
by the report itself (`promotion_stalled`) rather than reading healthy.
Full detail: `PLAN.md`'s O3 entry **on the O3 branch** (`d22c4ab`) — read
it there, not on main, until merged.

**Derek Prince non-book quote curation — COMPLETE as of 2026-08-09,**
unrelated prior session, untouched by O3. 477/496 documents approved, 20
still have zero approved quotes (their only candidate was rejected) —
Alex's open call whether that's worth a targeted re-extraction. Full
detail in git history of this file (commit `e04940a`).

**Still live (product).** ONE answer path (async; `serving_enabled` TRUE).
Quote rail live. Position one-hop live on origin. Book chapter extraction
still 8/53; Open Decision #21 not decided.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at 100-dial.

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- `five_fold_ministry.md` editorial marker — needs Alex.
- 20 Prince documents with zero approved quotes (2026-08-09).
- **O3 branch not merged** — Alex's call whether/when to merge
  `codex/o3-queue-resume-quarantine`, and whether the coordinator run loop
  (`invoke.py` + writers for queue/state-cache/seals/reassignment records)
  is scoped as a follow-on session before or after merge.

---

## Next

1. **O3 merge decision** — review the branch, decide merge timing, and
   scope the coordinator-run-loop session (separate, substantial work;
   not a continuation of what's already built).
2. **`five_fold_ministry.md` editorial decision.**
3. Async concurrency proof at 100-dial (before speed work).
4. Decide extractor hardening before any next Prince-style batch —
   majority-Scripture/unbalanced-quote checks, the `--per-doc-limit=1`
   cap (raise or keep), whether unused material exists in already-
   processed chunks. Savchuk/Ravenhill/Poonen eligible next.
5. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction.
6. **Human review of chapter-boundary proposals** (18 books) — Open
   Decision #21 still open.
7. **Trail / Brooks one-offs** — review then decide visibility.
8. Decide `pending` vs `draft` quote-status consolidation.
9. `jewish_perspectives` drop — needs Alex's explicit approval + a
   dedicated DB-write session.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
