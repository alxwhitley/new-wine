# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-14 (real-worker probes 1–3 merged to local
`main`, Claude-side verification-timeout mirror proven live; records
close).

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

**Three real-worker harness probes, 2026-08-14 — build/merge happened
locally this session, this is the records close.** First: a real
Claude Code worker ran a repo-only test-coverage packet, attended,
isolated worktree — one round `ACCEPT`. Second: closed the
verification-timeout gap the first surfaced, on the `.Codex` side —
one round `REVISE`, bounded fix, no second round needed. Third:
mirrored the same discipline onto the Claude-side `.claude/agents/*.md`
definitions Claude Code's own subagents actually load, plus a
Claude-specific outer-Bash-timeout-ceiling clause — one round
`APPROVE`, mutation-tested. A live, unprompted rerun then found the
wording insufficient (an executor could satisfy it with a raw native
Bash timeout instead of the CLI, and a genuine overrun backgrounded
instead of being cleanly killed); tightened to make the CLI mandatory,
reverified by an independent cold rerun — the executor chose the CLI
on its own, `pgrep` confirmed the timed-out process was actually dead.
All three merged to local `main` only, not pushed. Full suite: 1367
passed, 1 skipped. Full detail: PLAN.md's Overnight unattended runs
section. **This closes the last open item on the Claude-side path
before a real overnight night** — first item is now building Grok a
standing role-definition file (see Next).

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
origin. Auto Mode landmine still current — this session found a real
counterexample to the prior "pure noise" framing; see the upgraded
Known Harness Bugs entry below.

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

1. Build Grok a standing harness role-definition file — confirmed this
   session that none exists anywhere in the repo (no `.toml`/`.md`
   analog to `.Codex/agents/*.toml` or `.claude/agents/*.md`); the
   only Grok artifact found, `grok_overnight_prompt.txt`, is a one-off
   task prompt for an unrelated data-quality sweep and carries none of
   the hard constraints (governed-doc protection, ingest freeze,
   timeout discipline, reporting format). Blocks item 2.
2. Run a Grok-built probe through the same real-worker harness path —
   probes 1–3 were all Claude Code; needed before the supervised-week
   path can claim coverage across both permitted builders. Blocked on
   item 1.
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
11. `.claude/agents/planner-reviewer.md` cleanup — retired two-value
    `VERDICT: APPROVE | REJECT` format (current standard elsewhere is
    the four-value `ACCEPT|REVISE|QUARANTINE|HUMAN_REQUIRED` contract)
    and stale hardcoded `PLAN.md:NN`/`CLAUDE.md:NN` line-number
    citations in its checklist — both confirmed real and pre-existing
    by this session's planner-reviewer round, deliberately left
    untouched (a different, larger change than the timeout mirror).
    Needs its own cleanup packet.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
