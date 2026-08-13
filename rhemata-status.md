# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-13 (harness records closeout).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**O5 budgets merged to `main` at `20ce143`.** The previous "not yet
merged" line is false and is replaced, not annotated. Post-merge
suite was 1337 passed, 1 skipped.

**Coordinator run loop built at `ac53f76` (not pushed).** Thin
driver over the one-step runner; simulated workers only. One review
round; four fixtures fired (full night, crash/resume, provider
outage without spin, clean stop). Full suite 1342 passed, 1 skipped.
"Done" means simulated night, not real AI workers overnight.

**Decisions this session:** harness-tooling review is one round
(multi-round stays on the answer path). Safety fence deferred — not
cancelled, not a launch blocker. Path to real overnight workers:
narrow file allowlist + Alex reading the morning report daily for a
week. **Revisit trigger:** the fence gets built if a real overnight
run causes damage that cannot be recovered from git, or before any
harness work reaches anything outside the repository. Production DB
writes never run through the harness, day or night.

Already true, unchanged: all 8 pillars live; one async answer path
(`serving_enabled` TRUE); quote rail live; position one-hop live on
origin. Auto Mode landmine still current.

**Worktree note:** uncommitted Prince/quote edits remain in
`CLAUDE.md`, `PLAN.md`, `quote_subchunk_exclusion.py`, and
`extract_quote_candidates_derek_prince.py` from a different session.
Left untouched.

---

## Open blockers

**Launch:** ~68s full reveal latency. (100-dial concurrency proof is no
longer a blocker — Alex explicitly decided against a pre-launch load test,
PLAN.md, 2026-08-13.)

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- 20 Prince documents with zero approved quotes (2026-08-09).

---

## Next

1. O6 concurrent multi-packet rehearsal, when wanted — not a launch
   blocker for the deferred fence.
2. Decide extractor hardening before any next Prince-style batch.
3. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction.
4. Human review of chapter-boundary proposals (18 books) — Open
   Decision #21.
5. Trail / Brooks one-offs — review then visibility.
6. `pending` vs `draft` quote-status consolidation.
7. `jewish_perspectives` drop — needs Alex's explicit approval + a
   dedicated DB-write session.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
