# O6 — Concurrent Multi-Packet Rehearsal — 2026-08-13

## Boundary

This rehearsal used only disposable temporary state roots/worktrees, two real
disposable Git repositories (one per lane), and subprocess-based synthetic
workers (`synthetic_o6_worker.py`, a sleep-capable extension of the O3/O5
`synthetic_p5_worker.py` contract). It performed no network, database,
provider SDK, deployment, push, or merge-to-main action from inside the
packet itself, and no governed document (`CLAUDE.md`/`PLAN.md`/`HARNESS.md`/
`POSITIONING.md`/`DESIGN.md`/`rhemata-status.md`) was touched by the build.

This closes the concurrency gap O4 and O5 each explicitly left open for O6:
O4's own commissioning ran its two packets sequentially ("the real
coordinator runs the two packets sequentially; O6, not O4, owns the
concurrent rehearsal" — `o4_git_filesystem_isolation_2026-08-11.md`), and
O5's residual gaps list recorded the same thing as still-open ("O6 concurrent
multi-packet rehearsal — unaffected by this task, still open... every
scenario here runs sequentially" — `o5_budgets_hard_stops_2026-08-11.md`).

Real AI workers running overnight remain a separate, later milestone, still
blocked on the deferred safety fence — this rehearsal does not touch that
boundary and does not argue it should move.

## What this proves

- **Genuine concurrency, not simulated interleaving.** Two disjoint lanes
  (own git repo, branch, worktree, state root, and packet each) run as real
  `multiprocessing.Process` children, synchronized on a `multiprocessing.
  Barrier(2)` so both begin their claim at the same real instant, with real
  `time.time()` overlap evidence — never the coordinator's own simulated
  RFC3339 `now` strings, which prove nothing about actual concurrency.
- **All five O6 failure paths**, each reusing the established O3/O5
  mechanism directly rather than a new shortcut: crash/resume, quota
  fallback Kimi→Sonnet, bounded-retry quarantine, a recoverable (non-fatal)
  worker failure, and a human-authority packet blocked before claim.
- **One combined morning report.** A new pure function,
  `night_loop.combine_morning_reports()`, merges N lanes' own `run_night()`
  output into a single report Alex can read without opening two state roots
  by hand.

## New / changed files

- `.claude/harness-selftest/synthetic_o6_worker.py` (new, 63 lines) —
  extends `synthetic_p5_worker.py`'s exact file-write/marker/result contract
  with one addition: an optional `SYNTHETIC_SLEEP_SECONDS` env var, slept on
  before the worker does its writes, so the concurrency proof has a
  controllable real wall-clock window instead of racing near-instant
  subprocesses.
- `.claude/harness-selftest/test_o6_concurrent_rehearsal.py` (new, 854
  lines, 10 tests).
- `scripts/harness_coordinator/v1/night_loop.py` (+87/−1) — one additive,
  read-only function, `combine_morning_reports()`, exported in `__all__`.
  No existing function's body changed.

## Concurrency proof — real evidence, not asserted-and-hoped

`test_o6_two_lanes_run_concurrently_without_file_collision` was independently
mutation-tested by the reviewer, not merely read: the same two lanes run
**sequentially** (lane B started only after lane A exited, each with its own
single-party barrier) made the test's own overlap assertion evaluate
`False`. Run concurrently, real measurements across 5 runs: post-barrier
start skew `0.0000s` every time, each lane's real worker window ≈`0.83s`,
producing a genuine overlap window of the same width. The test's assertion
(`max(t_start_a, t_start_b) < min(t_end_a, t_end_b)`) is load-bearing, not
decorative.

File collision is checked on the real filesystem, not just in the journal:
lane A's worktree contains only `scripts/concurrency-lane-a.py`, never
`concurrency-lane-b.py`, and the mirror holds for lane B — against two
genuinely separate git repositories, branches, worktrees, and state roots.

## Failure-path evidence (real journal dumps, independently pulled)

**Lane B ("app-build"):**
```
PACKET_PAUSED:      appbuild-blocked -> HUMAN_AUTHORITY_REQUIRED
ATTEMPT_FINISHED:   appbuild-retry      attempt=1 cause=infra_retry              to_state=READY
                    appbuild-retry      attempt=2 cause=result_recorded          to_state=REVIEW
                    appbuild-quarantine attempt=1 cause=infra_retry              to_state=READY
                    appbuild-quarantine attempt=2 cause=attempt_budget_exhausted to_state=QUARANTINED
folded: appbuild-blocked=READY  appbuild-quarantine=QUARANTINED  appbuild-retry=ACCEPTED
```

**Lane A ("ingestion"):**
```
MODEL_FALLBACK_SELECTED: ingest-happy     implementation-primary -> implementation-terra (openai/gpt-5.6-terra)
MODEL_FALLBACK_SELECTED: ingest-fallback  implementation-primary -> implementation-terra (openai/gpt-5.6-terra)
ATTEMPT_STARTED worker identities: both openai/gpt-5.6-terra (never the exhausted opencode/kimi-k2.7-code)
folded: both ACCEPTED, attempts_started=1 each (after the injected crash + resume)
```

Quota fallback reuses O5's `_commission_scenario1` verbatim (a real
`PROVIDER_CAPACITY_RECORDED`/`ALLOWANCE_EXHAUSTED` evidence chain read by
the real pre-claim gate — the fallback identity is a synthetic stand-in,
per the same convention O5 already established, not a live Kimi/Sonnet
call). Quarantine reuses O5's process-group-kill pattern
(`_child_grandchild_worker_code`/`_process_group_probe_adapter`). Human-stop
reuses O5 scenario 6's shape. Crash/resume reuses `test_night_loop.py`'s
monkeypatch pattern, applied inside the lane's own multiprocessing target
(pytest's `monkeypatch` fixture cannot cross into a child process, so the
module attribute is patched by hand, same effect). Worker failure is a
plain non-zero-exit command hitting the real `INFRA_RETRYABLE`
classification, recovering on retry without reaching quarantine.

## `combine_morning_reports` — semantics verified against real reconciliation

Cross-checked against `reconcile.py` directly rather than trusting the
docstring: `attention_required` (reconcile.py ~L1296–1377) never appends an
item for a packet merely reaching `QUARANTINED` or `blocked_human` — a live
probe on Lane B's own `what_needs_attention`, with a quarantined **and** a
human-blocked packet both present, contained only the informational
`unverified_invariants` placeholder. The two synthesized attention items
`combine_morning_reports` adds are therefore load-bearing, not redundant —
without them those packets would be invisible in a morning report.
`all_invariants_passed` stays `True` at the lane level and ANDs to `True`
combined; the function only ever adds to the attention list, never filters,
so it cannot hide a real integrity problem. `_ATTENTION_WORTHY_DISPOSITIONS`
also covers terminal `HUMAN_REQUIRED` (via `reconcile.py`'s
`_O5_TERMINAL_DISPOSITION_BY_STATE` mapping it to `blocked_human`, ~L315),
not only the pre-claim pause form.

## Verification

Independently run twice — once by the orchestrating session, once by the
reviewer — with matching real output both times:

```
PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o6_concurrent_rehearsal.py -v
10 passed

PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o2_*.py .claude/harness-selftest/test_o3_*.py \
  .claude/harness-selftest/test_o4_*.py .claude/harness-selftest/test_o5_*.py \
  .claude/harness-selftest/test_o6_*.py .claude/harness-selftest/test_night_loop.py -q
1352 passed, 1 skipped
```

(1342 was O5's own closing baseline; the delta is exactly the 10 new O6
tests, with the same single pre-existing benign skip.)

The O6 file alone was re-run 4 times back to back (1 verbose + 3 plain) with
identical `10 passed` results each time, ~15.3s, confirming no flakiness.

Additional checks, all clean: `python3 -m py_compile` on all three changed
files; `git diff --check`; `git status --short` showing exactly the three
allowlisted paths; a grep for `psycopg2|requests|httpx|openai (as an
import)|anthropic (as an import)|supabase|socket|chmod|acl` across the new
files returning nothing but synthetic fixture identity strings and one
docstring reference.

## Final gate

Independent `planner-reviewer` pass, one round (per the harness's standing
review-intensity rule for harness tooling): `VERDICT: ACCEPT`. The reviewer
did not accept on the strength of the build's own report — it re-derived
the concurrency proof's load-bearing-ness by mutation (forcing sequential
execution and watching the assertion fail), pulled the journal evidence
above itself, and cross-checked `combine_morning_reports` against
`reconcile.py`'s real behavior rather than its docstring. All four of
PLAN.md's O6 exit criteria were confirmed independently satisfied.

Four non-blocking observations were recorded, none meeting the bar for a
second review round:
1. `barrier.wait()` has no timeout in either concurrency fixture — a dead
   child before the barrier could hang its sibling; the outer `join()` +
   liveness assert converts this to a clean test failure today, but a
   `timeout=` would convert a hang into a faster, cleaner one.
2. `combine_morning_reports` stores each lane's sub-report by reference
   (documented and asserted with `is`) — fine for current usage, worth
   knowing before any caller mutates a combined result in place.
3. `_ATTENTION_WORTHY_DISPOSITIONS` omits `paused_provider`/
   `resting_revise` — both defensible (self-clearing / already surfaced by
   an existing reconciliation item) but the docstring only explains the
   inclusions, not the omissions.
4. The combined test doesn't itself assert Lane A's fallback event or Lane
   B's pause reason code (those live in the dedicated per-path fixtures) —
   a documentation-coverage nit; the reviewer confirmed both hold inside
   the combined scenario anyway by direct journal inspection.

## Non-actions and residual boundary

No project or user worktree outside `.worktrees/o6-concurrent-rehearsal`
was created, removed, cleaned, overwritten, staged, or pushed by the build
itself. Only pytest-managed disposable repositories/worktrees and the one
authorized isolated build worktree were touched. No production database,
provider, network, migration, deployment, or governed record was touched.
Real-provider commissioning and the safety fence remain untouched and out
of scope, unchanged from O3/O4/O5's own stated position.

One operational note, not a defect: the build session repeatedly hit a
false positive from the Auto Mode classifier, misfiring on its own report
prose mentioning "SQL"/"migration" even though no such file exists
anywhere in this packet's three-file scope (confirmed by grep, twice,
independently). This is consistent with the already-documented Auto Mode
classifier landmine in `CLAUDE.md` — reporting noise, not a build defect,
confirmed by the reviewer to have caused no incomplete step or
silently-skipped verification.
