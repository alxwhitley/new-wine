# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-11 (O4 Git/filesystem isolation accepted on
`codex/o4-git-isolation` at `7ab9f15`; not merged or pushed). No production
writes, real-provider commissioning, deployment, or `serving_enabled` change.

**Session close:** `.agents/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**O4 Git/filesystem isolation — complete, committed, synthetically
commissioned, and independently accepted on `codex/o4-git-isolation`.** Final
build commit is `7ab9f15`; the branch is not merged or pushed. O3 remains
integrated locally into `main` at `b580915`, also not pushed.

Final controller evidence: 804 O2/O3/O4 tests passed; scoped compilation, diff
checks, and all three legacy harness guards passed. Independent final review
returned Spec PASS, Quality PASS, `ACCEPT`. The coordinator now binds an
operator-supplied repository root, baselines before a write attempt can become
`RUNNING`, derives postflight changes from Git, refuses staged, forbidden,
out-of-allowlist, secret-like, protected-tree, or evidence-inconsistent changes,
and emits mutation-free integration advice. Rootless legacy artifacts remain
readable but cannot authorize a new write attempt.

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

1. **O5 budgets and hard stops.** Add turn, wall-clock, retry, output-size,
   provider-allowance, and queue-wide limits before overnight rehearsal.
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
