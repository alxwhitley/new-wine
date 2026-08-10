# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-10 (O3 coordinator P5A–P5C committed on
`codex/o3-p5-coordinator-loop`; not merged or pushed). No production writes,
provider commissioning, deployment, or `serving_enabled` change.

**Session close:** `.agents/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**O3 coordinator P5A–P5C — built, committed, and independently accepted.**
Branch `codex/o3-p5-coordinator-loop`, not merged or pushed. Build commits:
`7a78541` (safe enrollment and durable attempt start), `c700b97` (bounded
synthetic invocation and recovery-safe process sidecars), and `028372e`
(trusted verdict ingestion, review ownership/recovery, terminal seals,
REVISE requeue, and seal-before-promotion). The controller's final gate passed
591 O2/O3 tests, including 104 focused P5C tests; three legacy harness scripts
also pass. Fresh Opus returned `ACCEPT` for each slice. P5C binds its complete
artifact lifecycle to one pinned, no-follow state-root identity.

**Not complete:** P5D (fallback/reassignment/reconciliation/status) and P5E
(disposable synthetic end-to-end commissioning) remain. No real Kimi, Sonnet,
Claude, or Grok worker was commissioned. Real-provider commissioning remains
blocked until a subprocess sandbox and command policy are independently
proven.

**Required pre-P5D remediation, each as a separate bounded fix:**

- Enrollment can report success after a chronology-invalid journal append is
  later treated as a torn tail.
- Invocation cleanup can signal a recycled PID after the process was reaped.
- Derived queue entries are ordered by packet ID while validation requires
  ascending enqueue sequence.
- P5A worker claims still use pathname lifecycle operations rather than P5C's
  pinned state-root identity.

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
- **O3 coordinator branch not merged** — P5A–P5C are committed on
  `codex/o3-p5-coordinator-loop`; four pre-P5D remediations remain above.

---

## Next

1. **Fresh O3 session:** fix the four pre-P5D defects in separate commits,
   rerun the full harness gate, then build P5D and P5E. Decide merge timing
   only after synthetic commissioning passes.
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
