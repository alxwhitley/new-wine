# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-14 (real-worker probes 1–2 merged to local
`main`; records close).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**O6 concurrent rehearsal merged to `main` at `425d6e2`.** Two disjoint
lanes run as real `multiprocessing.Process` children on a barrier — the
independent reviewer proved the concurrency proof load-bearing by mutation
(forced sequential execution made the overlap assertion fail). All five O6
failure paths (crash/resume, worker failure, quota fallback Kimi→Sonnet,
quarantine, human-stop) demonstrated with real journal evidence, reusing the
O3/O5 fixtures directly. New pure `night_loop.combine_morning_reports()`
merges lanes into one report. Independent `ACCEPT`, one round. Full O2–O6
suite: 1352 passed, 1 skipped, confirmed post-merge. Full detail:
`docs/audits/o6_overnight_rehearsal_2026-08-13.md`. Phase 0 (O1–O6) is now
fully closed. Real AI workers running overnight remain a separate milestone,
still blocked on the deferred safety fence — unchanged, not this session's
work.

**Two real-worker harness probes, 2026-08-14 — build/merge happened
locally this session, this is the records close.** First: a real (not
simulated) Claude Code worker ran a repo-only test-coverage packet
attended, isolated worktree, zero Auto Mode interference — one round
`ACCEPT`. Second: closed the verification-timeout gap the first
surfaced (`scripts/harness_coordinator/v1/verification_commands.py` —
timeouts now declared ahead of the run, clean `TIMED_OUT` into the
existing hard-stop machinery, not a parallel one) — one round
`REVISE`, bounded one-line fix applied and reverified, no second
round needed. Both merged to local `main` only, not pushed. Full
suite: 1366 passed, 1 skipped. Full detail: PLAN.md's Overnight
unattended runs section. **Not done:** the timeout fix landed on
`.codex/agents/*.toml` only — the parallel Claude-side
`.claude/agents/*.md` definitions still need it; see Next.

**O5 budgets merged to `main` at `20ce143`; coordinator run loop at
`ac53f76`.** Both unchanged since last session — see PLAN.md for full
detail rather than re-narrating here.

**Standing decisions, unchanged:** harness-tooling review is one round
(multi-round stays on the answer path). Safety fence deferred — not
cancelled, not a launch blocker. Path to real overnight workers: narrow
file allowlist + Alex reading the morning report daily for a week.
**Revisit trigger:** the fence gets built if a real overnight run causes
damage that cannot be recovered from git, or before any harness work
reaches anything outside the repository. Production DB writes never run
through the harness, day or night.

Already true, unchanged: all 8 pillars live; one async answer path
(`serving_enabled` TRUE); quote rail live; position one-hop live on
origin. Auto Mode landmine still current — reconfirmed this session as
pure reporting noise (misfired on report prose, not on any real file),
not a build defect.

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

## Known Harness Bugs

- **Auto Mode misfire on harmless prose mentioning "SQL"/"migration"
  — 2026-08-14.** Consistent with the existing Auto Mode landmine
  (CLAUDE.md): the classifier reacted to report/instruction prose
  that merely named "SQL"/"migration" as words, with no such file or
  action actually present anywhere in the session. Pure noise, not a
  build defect — logged so a future session doesn't re-investigate it
  as new.

---

## Next

1. Close the Claude-side agent-definition timeout gap —
   `.claude/agents/executor.md`/`planner-reviewer.md` need the same
   declared-ahead-timeout hard constraint just added to
   `.codex/agents/executor.toml`/`planner-reviewer.toml` (probe 2,
   2026-08-14); confirmed zero timeout mentions in the Claude-side
   copies today.
2. Run a Grok-built probe through the same real-worker harness path —
   probes 1–2 were both Claude Code; needed before the supervised-week
   path can claim coverage across both permitted builders.
3. First supervised overnight night. Fence stays deferred, unchanged
   revisit trigger (real unrecoverable damage, or harness work
   reaching outside the repo).
4. Decide extractor hardening before any next Prince-style batch.
5. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction.
6. Human review of chapter-boundary proposals (18 books) — Open
   Decision #21.
7. Trail / Brooks one-offs — review then visibility.
8. `pending` vs `draft` quote-status consolidation.
9. `jewish_perspectives` drop — needs Alex's explicit approval + a
   dedicated DB-write session.
10. F2–F5 remain open before F6's ingestion-ready benchmark can be
    declared — O6 alone does not close F6.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
