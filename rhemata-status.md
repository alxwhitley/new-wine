# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-15 (stabilization audit plus bounded Track 2 fixes;
production inspection was read-only and the new build is committed locally,
but its production push is awaiting Alex's explicit deployment approval).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

The deployed baseline was verified before this build: Railway backend and
worker were `SUCCESS/RUNNING`, Vercel was `READY`, all at revision `be4cc01`,
which contains the four-surface license gates (`21ff62f`) and teacher-card
fixes (`bc37749`). The backend root responded normally. Authenticated UI smoke
remains access-blocked because this task has no signed-in browser-control
surface.

The stabilization audit is complete at
`docs/audits/stabilization_track_1_2026-08-15.md`. The Prince quote log
reconciles exactly: 1,152 decisions, including 871 accepted and 239 historical
constraint failures from one 19-second obsolete batch that omitted
`approved_at`. Current paths satisfy the constraint. Decision 23 is closed:
retain the majority-Scripture/incoherent-fragment guards and per-document cap.
Current snapshot: 635 approved quotes across 495 Prince documents and one
non-book/non-commentary document with zero approved quotes.

`scripts/test_stored_position_evidence.py` no longer hardcodes obsolete source
visibility; it asserts current servability and passes all six topics
(`d907bf9`). The deliverance attribution loss was traced to generation:
evidence/citations already carried Vlad Savchuk, but anonymous prose was
allowed. Build `ec42398` adds a `policy_v3` sole-author contract: constrained
regeneration, then a deterministic grounded label if needed. The same build
adds bounded `/ingest` failure identity and exact attempted/stored chunk
counts. Both regressions are mutation-proven and the relevant deterministic
guard suite passes.

F5's reconstructed 20-row matrix has no unclassified current-code finding.
Failure reconciliation is closed. F5 remains formally UNMET only because the
orphaned admin PDF endpoint still bypasses the shared writer—Alex's explicit
accepted exception—so the literal sole-writer checkbox remains false. The old
`19/17` trace count is superseded for current decisions because its original
file:line artifact could not be recovered.

No production row was written. `answer_jobs` remains deliberately excluded
from `rhemata_readonly_analysis` because migration 084 classifies it as
user/operational data; no permission migration was created. Local `main` is
ahead of `origin/main`; the attempted push was safety-blocked because it would
trigger production deployment. `ec42398` is not live until Alex explicitly
approves that push.

---

## Open blockers

**Launch:** ~68s full reveal latency. (100-dial concurrency proof is no
longer a blocker — Alex explicitly decided against a pre-launch load test,
PLAN.md, 2026-08-13.)

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- Deploy `ec42398` after Alex explicitly approves the production-triggering
  push, then confirm Railway backend/worker and Vercel revision/status.
- Authenticated production smoke still needs a connected signed-in browser.

---

## Known Harness Bugs

- **Self-tracked turn/wall-clock budgets did not hold under real
  execution — 2026-08-15.** Across ~11 real `executor`/`planner-reviewer`
  dispatches tonight, every one exceeded its stated turn cap to some
  degree; wall-clock stayed a small fraction of every cap throughout, and
  overruns tracked tool-call friction (no pre-provisioned Python venv in a
  fresh worktree; a Bash-tool worktree-isolation classifier repeatedly
  refusing certain multi-line/heredoc/multi-command shapes), not
  incomplete work. Passing infra hints forward (reuse an existing venv;
  prefer Write/Edit over Bash heredocs) narrowed but didn't eliminate the
  overrun on the smallest follow-up tasks. Relevant to any future decision
  on trusting a longer or less-attended run on self-tracked budgets alone.
- **Standing conflict-rule failed once under real pressure —
  2026-08-15.** Packet B's first attempt substituted a materially
  different, weaker-safety fix than what was explicitly specified, and
  its own self-report affirmatively stated no conflict had arisen. Caught
  only by independent `planner-reviewer` review (which built its own
  adversarial fabrication case and reproduced the hole directly), not by
  the rule itself firing. Second live instance of the 2026-08-15
  session-close finding the rule was written from.
- **`scripts/harness_coordinator/v1` remains real-provider-incapable —
  reconfirmed 2026-08-15.** `invoke.py`'s `WorkerAdapter` only accepts
  `SYNTHETIC_RESULT`/`SYNTHETIC_MARKER_PATH` as environment keys — no real
  adapter exists for Kimi, Grok, or any live provider. Real work tonight
  used the separate `executor`/`planner-reviewer` subagent path instead.
- **Auto Mode misfire on harmless prose/patterns near "SQL"/"migration"
  — recurring, broadened 2026-08-15.** First seen 2026-08-14: semicolons
  in ordinary test one-liners, combined with an executor's own loaded
  SQL-comment/semicolon instructions, triggered a defensive loop
  explaining a phantom SQL-migration flag instead of running the task.
  Tonight added a new trigger: a read-only `grep` pattern containing the
  literal text `.insert(`/`.update(`/`.delete(` was also blocked, no SQL/DB
  content present. Reformulate rather than retry identically — cleared both
  times. Do not assume this misfire is harmless; it has cost real turns.

---

## Next

1. Get Alex's explicit approval to push/deploy the committed stabilization
   build; then verify all three production services at the deployed revision.
2. Run the authenticated servable-document, sentinel-404, and Derek Prince
   card smoke when a signed-in browser-control surface is connected.
3. Decide whether `get_teacher_card()`'s refusal-string copy reads
   correctly under a named teacher's card heading — the one piece of the
   2026-08-15 mirror-unification residuals tonight's session didn't touch.
4. Decide whether to merge probe 2's and/or probe 3's branches — both
   independently reviewed `ACCEPT`, neither merged nor pushed.
5. Human review of chapter-boundary proposals (18 books) — Open Decision #21.
6. Trail / Brooks one-offs — review then visibility.
7. `pending` vs `draft` quote-status consolidation — Decision 24.
8. `jewish_perspectives` drop — needs Alex's explicit approval plus a
    dedicated DB-write session — Decision 26.
