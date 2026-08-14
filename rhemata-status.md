# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-14 (Grok role-definition file authored, merged
`1797e31`, and pushed; every previously-local-only commit this week is
now on origin too).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Grok's standing role-definition file authored, merged, and pushed —
2026-08-14.** `.grok/agents/harness-builder.md`, branch
`claude/grok-harness-builder-role` (build `d0bdf64`, merge `1797e31`,
pushed same commit). Authored directly by Claude Code — Grok does not
author its own fence — per the prior session's locked decisions: its own
agent type, not a shadow of `executor`; current task-class production-write
gate (mirrors `.codex/agents/executor.toml`/`HARNESS.md`, not Claude's
stale frozen-script version); shared verification-timeout discipline; a
Grok-shaped outer-timeout note sized from verified `run_terminal_command`
facts, not Grok's own self-report; Sonnet named as reviewer in the file's
own text; attended-only pending a separate hook-compatibility follow-up
(the guard doesn't yet recognize Grok's action shapes — the file states
this as its own mandatory warning). Alex confirmed the section outline
before the full text was written; no independent second-reviewer pass has
run against the finished file yet. Full detail: the file itself and
`HARNESS.md`'s Local activation note.

**Everything previously "merged locally, not pushed" is now on origin.**
O6's close was already on origin (`2867ecc`); this push carried the two
real-worker verification-timeout probes, their records closes, and this
session's role-definition merge — 11 commits, `2867ecc..1797e31`, fast-
forwarded cleanly. Not re-narrated here — see PLAN.md's Overnight
unattended runs section for what each one did.

**O5/O6/probes 1–3, unchanged since last entry, now also on origin:** O5
budgets (`20ce143`), coordinator run loop (`ac53f76`), O6 concurrent
rehearsal (`425d6e2`), and real-worker probes 1–3 closing the Claude-side
verification-timeout gap (`1356418`) are all live on `main`. Full detail:
PLAN.md's Phase 0 / Overnight unattended runs section.

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
origin. Auto Mode landmine still current — see the Known Harness Bugs
entry below.

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
  — 2026-08-14, upgraded same day.** First observed earlier this
  session as pure reporting noise (misfired on report prose, zero
  effect). **Later the same session, a real counterexample: the
  misfire can genuinely stall work, not just decorate a log.** During
  Probe 3, a live `executor` subagent hit this classifier while
  running Python `time.sleep` verification commands — semicolons in
  the test one-liners, combined with the executor's own loaded
  SQL-comment/semicolon instructions (the Migration 051 gotcha),
  triggered a defensive loop explaining a phantom SQL-migration flag
  instead of running the task. Nothing SQL- or migration-related was
  actually present. Worked around per the stall-risk rule: did not
  retry the identical prompt, removed the semicolons, reran once —
  cleared. **A future session must not assume this misfire is always
  harmless** — it can consume a full turn and block real work;
  reformulate, don't just retry.

---

## Next

1. Run a Grok-built probe through the same real-worker harness path —
   probes 1–3 were all Claude Code; needed before the supervised-week
   path can claim coverage across both permitted builders. Unblocked —
   `.grok/agents/harness-builder.md` landed 2026-08-14 (merge `1797e31`).
   Grok stays attended-only until the hook-compatibility follow-up lands.
2. First supervised overnight night. Fence stays deferred, unchanged
   revisit trigger (real unrecoverable damage, or harness work
   reaching outside the repo).
3. Decide extractor hardening before any next Prince-style batch.
4. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction.
5. Human review of chapter-boundary proposals (18 books) — Open
   Decision #21.
6. Trail / Brooks one-offs — review then visibility.
7. `pending` vs `draft` quote-status consolidation.
8. `jewish_perspectives` drop — needs Alex's explicit approval + a
   dedicated DB-write session.
9. F2–F5 remain open before F6's ingestion-ready benchmark can be
   declared — O6 alone does not close F6.
10. `.claude/agents/planner-reviewer.md` cleanup — retired two-value
    `VERDICT: APPROVE | REJECT` format (current standard elsewhere is
    the four-value `ACCEPT|REVISE|QUARANTINE|HUMAN_REQUIRED` contract)
    and stale hardcoded `PLAN.md:NN`/`CLAUDE.md:NN` line-number
    citations in its checklist — both confirmed real and pre-existing
    by a prior session's planner-reviewer round, deliberately left
    untouched (a different, larger change than the timeout mirror).
    Needs its own cleanup packet.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
