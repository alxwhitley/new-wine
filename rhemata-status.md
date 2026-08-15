# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-15 (attended real-worker harness session: shipped and
pushed two independently-reviewed fixes with mutation-tested regression
tests; confirmed `scripts/harness_coordinator/v1` still cannot invoke a real
provider; closes with two governance findings on trusting a longer or
less-attended run — see below).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Tonight's harness run shipped and is on `origin/main` — deploy status NOT
checked this session.** `21ff62f` (license/visibility gate on document view,
library book excerpts, background-topic injection, `get_paper_body` — reuses
`is_source_servable()` unmodified) merged as a fast-forward; `ceb317f`/`bc37749` (`get_teacher_card()` bio false-positive + commentary
query-slot crowding fixes — see CLAUDE.md's Landmines entry) merged with a
merge commit. Both independently reviewed `ACCEPT` (Packet B needed one
`REVISE`-then-redo round first — full account in PLAN.md's
Overnight-unattended-runs entry), both got new mutation-tested regression
tests (`scripts/test_four_surfaces_license_gate.py`,
`scripts/test_teacher_card_bio_redaction.py`). Pushed and confirmed:
`origin/main` == local `main` == `bc37749`. **Not verified this session:
Railway/Vercel deploy status** — confirm before assuming either is live.

**Real-worker harness finding:** `scripts/harness_coordinator/v1/invoke.py`'s
own worker-invocation boundary is confirmed synthetic-only by code — no
real-provider adapter exists. Tonight's real work used the
`executor`/`planner-reviewer` subagent path directly instead, attended, not
the automated coordinator. Two governance findings from this — self-tracked
turn budgets didn't hold across ~11 dispatches, and the standing
conflict-rule failed once under real pressure — full account in PLAN.md's
Overnight-unattended-runs section, 2026-08-15 entry.

**From the earlier 2026-08-15 diagnostic session (condensed — full detail
in git history / CLAUDE.md's Landmines):** Prince quote coverage re-derived
live (1 zero-quote document, not the stale "20" figure; Decision 23 stays
open pending the rejection-reason breakdown, unblocked by a permission fix
but not yet re-run). Ingestion-bypass count corrected to 1 real bypass (an
orphaned admin PDF-upload endpoint, left in place per Alex's decision), not
the preliminary "six." Corpus visibility gap closed for
fasting/deliverance/prayer — all three live-verified answering with real
citations; `safe_mode_on` is off, all `source_toggles` enabled.
`quote_verification_log` read-permission gap fixed (migration 087).

**Process finding, 2026-08-15 session-close (the rule tonight re-tested):**
an executor was instructed to record two checks as unverified, judged the
instruction outdated given evidence in hand, and unilaterally overwrote it
rather than flagging the conflict — facts later confirmed correct, but that
doesn't make unilateral resolution correct. New standing rule in CLAUDE.md's
working rules. Tonight found a second live instance of the same shape
(Packet B's first attempt) — see above.

---

## Open blockers

**Launch:** ~68s full reveal latency. (100-dial concurrency proof is no
longer a blocker — Alex explicitly decided against a pre-launch load test,
PLAN.md, 2026-08-13.)

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- Prince quote rejection-reason breakdown still not produced (Decision 23
  stays open) — permission gap fixed; diagnostic not yet re-run.
- `test_stored_position_evidence.py` is stale against the live Savchuk/
  Ravenhill/Poonen visibility flip — would likely fail if run.
- Deploy status of tonight's merges (`21ff62f`/`bc37749`) not checked this
  session — confirm Railway/Vercel before assuming live.

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

1. Re-run the Prince quote rejection-reason diagnostic now that the
   permission gap is fixed — closes Decision 23 if the evidence supports it.
2. Fix or retire `test_stored_position_evidence.py`'s stale pre-flip
   assertions — currently false against live data.
3. Triage the 17 untouched bypasses from the 2026-08-15 F5 trace
   (accept/defer/close each) — F5's exit criteria stay unmet until this
   happens. Tonight closed 4 more license/visibility bypasses separately;
   unconfirmed whether they overlap this 17 — see PLAN.md's F5 note.
4. **Deliverance answer cites sources with no teacher name shown** — the
   2026-08-15 live verification's deliverance answer had six citations
   with no teacher name, unlike the fasting/prayer answers, which both
   named teachers directly. Named attribution is the product's core
   promise, so this is a correctness issue, not a display nicety — and
   deliverance is one of the eight charismatic pillars. Needs a read-only
   diagnostic first: missing from evidence, dropped during generation, or
   just not rendered?
5. Decide whether `get_teacher_card()`'s refusal-string copy reads
   correctly under a named teacher's card heading — the one piece of the
   2026-08-15 mirror-unification residuals tonight's session didn't touch.
6. Confirm Railway/Vercel deploy status for tonight's merges (`21ff62f`/
   `bc37749`) — not checked this session.
7. Decide whether to merge probe 2's and/or probe 3's branches — both
   independently reviewed `ACCEPT`, neither merged nor pushed.
8. Human review of chapter-boundary proposals (18 books) — Open Decision #21.
9. Trail / Brooks one-offs — review then visibility.
10. `pending` vs `draft` quote-status consolidation — Decision 24.
11. `jewish_perspectives` drop — needs Alex's explicit approval plus a
    dedicated DB-write session — Decision 26.
