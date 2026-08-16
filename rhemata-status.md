# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-15 (source-ingest runner repository build; deterministic
local tests only, with no live fetch/provider/database write, migration apply,
push, or deployment).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

The durable source-ingest runner is built on local branch
`codex/source-ingest-runner` in commits `f6f51cb` through `4ee0d40`. It supports
one cleared `pdf + single + declared` row at a time: public-IP-pinned bounded
fetch, bounded child-process PDF extraction, existing non-sentinel source
resolution, canonical servability, declared-author override, read-only dry
run, the shared atomic corpus writer, leases/retries, and exact terminal
reconciliation. Successful ingest retains complete extracted text in
`documents.full_text`; it does not retain the PDF binary. Review corrected
retry accounting so a corpus attempt remains recorded across later retries.

Migration 088 and its explicit apply/verifier script are prepared but
unapplied. The script requires `--apply`, first writes a private exact retention
snapshot, verifies the schema/count/backfill on a fresh connection, and scopes
its two-claimer fixture and cleanup to one generated UUID/marker. There is no
source-worker service. No URL, provider, or production database was contacted,
and no push or deployment occurred.

The local gate passes 69 focused unit tests (12 fetcher, 6 PDF, 12 processor,
12 jobs, 8 worker, 1 router retention, 17 apply verifier, 1 async serving), the
migration contract, Nixpacks parity, ingest-failure reconciliation, compilation
of every changed Python file, and diff checks. Safety mutations were proven for
unsafe-IP rejection, streamed byte limits, PDF page/text bounds, sentinel and
declared-author gates, ownership/reconciliation, read-only dry run, and the
explicit apply guard.

The previously verified deployed baseline remains revision `be4cc01` on
Railway/Vercel. Local `main` also still contains the unpushed stabilization
build ending at `ec42398`; pushing `main` would trigger production deployment,
so it remains held for Alex's separate deployment decision. Authenticated UI
smoke still requires a connected signed-in browser surface.

---

## Open blockers

**Launch:** ~68s full reveal latency. (100-dial concurrency proof is no
longer a blocker — Alex explicitly decided against a pre-launch load test,
PLAN.md, 2026-08-13.)

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- Source ingest is not operational until migration 088 is separately approved,
  applied, verified, dry-run against one row, and proven on one isolated item;
  no worker service exists yet.
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

1. In a separately approved production-write session, apply and verify
   migration 088; then run one read-only queue-row dry run and review its
   URL/hash/page/chunk/source/dedup evidence before authorizing any write.
2. Process one isolated real queue item, reconcile queue/document/chunk/
   proposition counts, sample retained text, and only then decide whether to
   create/deploy a source-worker service or run a bounded attended batch.
3. Get Alex's explicit approval to integrate and push the local builds; because
   `main` push triggers production deployment, verify all three services at the
   resulting revision when that deployment is intentionally authorized.
4. Run the authenticated servable-document, sentinel-404, and Derek Prince
   card smoke when a signed-in browser-control surface is connected.
5. Decide whether `get_teacher_card()`'s refusal-string copy reads
   correctly under a named teacher's card heading — the one piece of the
   2026-08-15 mirror-unification residuals tonight's session didn't touch.
6. Decide whether to merge probe 2's and/or probe 3's branches — both
   independently reviewed `ACCEPT`, neither merged nor pushed.
7. Human review of chapter-boundary proposals (18 books) — Open Decision #21.
8. Trail / Brooks one-offs — review then visibility.
9. `pending` vs `draft` quote-status consolidation — Decision 24.
10. `jewish_perspectives` drop — needs Alex's explicit approval plus a
    dedicated DB-write session — Decision 26.
