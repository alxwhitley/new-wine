# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-11 (O5 Task 1 implemented but awaiting independent
review on `codex/o5-budgets-hard-stops`; live uncommitted diff). No production
writes, real-provider commissioning, deployment, or `serving_enabled` change.

**Session close:** `.agents/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**O5 budgets and hard stops — in progress on
`codex/o5-budgets-hard-stops`.** O4 is complete, accepted, pushed as
`origin/codex/o4-git-isolation`, and fast-forwarded into local `main` at
`d554554`; it is not merged to remote `main`. O5 design `59cf7f2` and detailed
plan `18bf213` are committed. Runs are designed to stop at an authenticated
finite plan, finish an active attempt before graceful provider/queue stops,
enforce immediate command/output safety limits, and use capability-class model
fallbacks. Fable 5 is the active design model; GPT-5.6 Sol `max` is a disabled
design fallback pending Alex's evaluation. OpenCode Go and Terra/Sonnet serve
implementation routes; Sol/Fable/Grok serve qualified review/audit routes.

Task 1 (execution-plan contract and binding) is implemented but uncommitted in
the isolated worktree. Changed scope: execution-plan schema/validator/tests,
contract exports, journal schema/runtime, and recovery binding. Implementer
evidence is green: 18 O5 contract tests, 92 O2/O3 schema tests, 64 O3
enrollment/recovery tests, scoped compilation, JSON parsing, and diff checks.
The independent reviewer was interrupted before returning a verdict. Task 1 is
therefore not accepted: Claude Code must review the live diff before any commit.
Durable task paths and exact continuation instructions are in
`.superpowers/sdd/2026-08-11-o5-budgets-hard-stops/progress.md`.

**Still intentionally blocked:** no real Kimi, Sonnet, Claude, or Grok worker
was commissioned. Real-provider commissioning remains `HUMAN_REQUIRED` until
an independently proven pre-execution sandbox constrains filesystem, command,
environment, and network access. Synthetic receipt recovery does not claim
general exactly-once semantics for arbitrary external effects before a receipt
can exist. The optional per-packet state-cache invariant remains explicitly
unverified in reconciliation; immutable reassignment preservation is verified.

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

---

## Next

1. **Resume O5 Task 1 review.** Worktree:
   `/private/tmp/rhemata-o3-verify.7NOGWb`; branch:
   `codex/o5-budgets-hard-stops`. Dispatch a fresh high-reasoning reviewer over
   the seven-file live diff using the Task 1 brief/report. On `ACCEPT`, the
   controller commits `feat: bind coordinator runs to execution plans`, then
   executes Tasks 2–5 sequentially from the committed O5 plan.
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
