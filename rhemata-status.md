# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-11 (O3 repo-only synthetic coordinator integrated
locally into `main` at `b580915`; not pushed). No production writes,
real-provider commissioning, deployment, or `serving_enabled` change.

**Session close:** `.agents/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**O3 repo-only coordinator — complete, committed, synthetically commissioned,
independently accepted, and integrated locally into `main`.** Integration is
at `b580915`, not pushed. P5A–P5C: `7a78541`, `c700b97`, `028372e`; four bounded
pre-P5D remediations: `c8a5c4c`, `65d908d`, `badc41c`, `cfb753e`; P5D:
`746bb05`; P5E: `e16920b`; commissioning audit: `5322411`.

Final controller evidence: 656 O2/O3 tests passed, including 11 focused P5E
commissioning tests; three legacy harness scripts, scoped compilation, and
diff checks passed. Fresh Opus returned final `ACCEPT`. Disposable tests cover
the real coordinator path from enrollment through worker result, REVIEW,
trusted verdict, terminal seal, dependency promotion, reconciliation, crash
resume, separate singleton/claim contention, and deterministic `--once`.

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

1. **O4 Git/filesystem isolation.** Prove packet worktree ownership,
   allowlist enforcement, dirty-work preservation, and fail-closed integration
   conflicts before real-provider commissioning.
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
