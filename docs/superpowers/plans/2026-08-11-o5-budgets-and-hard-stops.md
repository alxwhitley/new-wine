# O5 — Budgets and Hard Stops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the already-built wall-clock/output-size limiter into real
invocations, add a deterministic risk-class hard-stop admission gate, add
bounded backoff + lane pause on confirmed provider exhaustion, and add a
sequential session driver with queue-wide limits — closing all four O5
exit criteria in PLAN.md without touching O1–O4 guarantees.

**Spec:** `docs/superpowers/specs/2026-08-11-o5-budgets-and-hard-stops-design.md`
— read it first; this plan does not repeat its rationale.

## Global Constraints

- Python 3.9: use `Optional[str]`, never `str | None`.
- O5 is repo-only: no production DB/network access, provider commissioning,
  deployment, migration, push, or governed-content edit.
- No LLM judgment call anywhere in a new gate — pure functions over packet
  content and durable state only.
- D0.4 holds: no implicit clock inside a pure function; `now` is always an
  explicit argument. Only a CLI entry point may call `datetime.now()`.
- For this supervised build only, implementer/reviewer subagents never
  stage or commit; after a clean independent review, the explicitly
  authorized primary controller stages the task allowlist and creates the
  task commit.
- Build commits and the final records commit remain separate.
- Tests exercise only the disposable fixtures/tempdirs this suite already
  uses, never a real state root outside a test's own tmp_path.
- Every O2/O3/O4 test that passes today must still pass after every task.

---

## File map

- Modify `scripts/harness_coordinator/v1/invoke.py`: real wall-clock
  capture in `persist_invocation_outcome`.
- Modify `scripts/harness_coordinator/v1/coordinator.py`: pass
  `packet["budgets"]` fields + `stop_requested` into both
  `invoke_worker(...)` call sites; add `run_session()`.
- Modify `scripts/harness_contracts/v1/packet.py`: `risk_class` field +
  validator; export the hard-stop indicator constants the classifier uses.
- Modify `schemas/harness/v1/packet.schema.json`: `risk_class` field.
- Create `scripts/harness_coordinator/v1/risk_classify.py`: deterministic
  hard-stop content classifier.
- Modify `scripts/harness_coordinator/v1/enroll.py`: call the classifier
  during preflight; refuse enrollment on a routine/hard-stop-indicator
  mismatch; route a genuine `hard_stop` packet straight to
  `HUMAN_REQUIRED` instead of `READY`.
- Modify `scripts/harness_coordinator/v1/classify_runtime.py`: backoff
  computation on exhaustion-without-fallback; derive `disabled_lanes` from
  the fold.
- Modify `scripts/harness_coordinator/v1/recovery.py`: fold the new
  disabled-lane derivation into `_fold_journal`'s output (or expose a
  sibling pure function reading the same fold — implementer's call,
  document the choice in the commissioning audit).
- Create `scripts/harness_coordinator/v1/run_session_cli.py`: write CLI
  looping `run_once`.
- Modify `scripts/harness_contracts/v1/provider_evidence.py`: cap
  `matched_signal.byte_length`.
- Create `.claude/harness-selftest/test_o5_invocation_budgets.py`
- Create `.claude/harness-selftest/test_o5_risk_classify.py`
- Create `.claude/harness-selftest/test_o5_backoff_pause.py`
- Create `.claude/harness-selftest/test_o5_session_driver.py`
- Modify `.claude/harness-selftest/test_o3_p5_invocation.py`,
  `test_o3_classification.py`, `test_o2_json_schemas.py` as needed for the
  new field/behavior (extend, never weaken existing assertions).

---

### Task 1: Wire wall-clock/output-size budgets into real invocation

**Files:**
- Modify: `scripts/harness_coordinator/v1/coordinator.py`
- Modify: `scripts/harness_coordinator/v1/invoke.py`
- Create: `.claude/harness-selftest/test_o5_invocation_budgets.py`

**Interfaces:**
- No new public functions. `coordinator.py`'s two `invoke_worker(...)` call
  sites (currently `coordinator.py:756-758` and `~908-910`) gain
  `timeout_seconds=invocation_packet["budgets"]["wall_clock_seconds"]`,
  `output_limit_bytes=invocation_packet["budgets"]["max_output_bytes"]`,
  `result_limit_bytes=invocation_packet["budgets"]["max_output_bytes"]`,
  and `stop_requested=<a callable the coordinator already has access to
  for interrupt handling — read `recovery.py`/`process_sidecar.py` for the
  existing interrupt-check primitive before inventing a new one>`.
- `invoke.py:persist_invocation_outcome` stops writing
  `"wall_clock_seconds": 0` and `started_at == finished_at`; it must use
  the invocation's own real start/finish timestamps (the function already
  has access to real elapsed time via the same monotonic clock
  `invoke_worker` uses internally — thread it through the `InvocationOutcome`
  return value rather than recomputing).

- [ ] **Step 1: Write failing tests proving budgets reach the real call**

  Monkeypatch `invoke_worker` (or use a fake adapter) to capture the
  kwargs `coordinator._run_iteration`/`coordinator.run_once` actually
  passes. Enroll a packet with a distinctive `wall_clock_seconds` (e.g.
  `7`) and `max_output_bytes` (e.g. `2048`) and assert those exact values
  arrive at `invoke_worker`, not the 30s/1MiB defaults.

  Also add a fixture proving `persist_invocation_outcome` records a
  nonzero, plausible `wall_clock_seconds` for an invocation that actually
  takes measurable time (a synthetic adapter with a deliberate short
  sleep, or a monkeypatched clock with two distinct values), and that
  `started_at != finished_at` when they genuinely differ.

- [ ] **Step 2: Run and confirm RED**

  ```bash
  PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
    .claude/harness-selftest/test_o5_invocation_budgets.py -q
  ```

  Expected: failures on the hardcoded-30s/0-wall-clock assertions.

- [ ] **Step 3: Implement the wiring and the capture fix**

  Read `budgets` off the raw packet body already in scope at both call
  sites (`invocation_packet`/`packet_body` — not the folded scheduling
  state, which does not carry these fields; see the spec's "What already
  exists" section for why). Preserve every existing default for any
  caller that doesn't supply a full `budgets` object (tests that
  construct minimal packets) — fail closed to the existing 30s/1MiB
  defaults only when a budget field is genuinely absent, never silently
  swallow a present-but-small value.

- [ ] **Step 4: Run Task 1 tests plus the existing invocation/O3 suite**

  ```bash
  PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
    .claude/harness-selftest/test_o5_invocation_budgets.py \
    .claude/harness-selftest/test_o3_p5_invocation.py \
    .claude/harness-selftest/test_o3_p5_commissioning.py \
    .claude/harness-selftest/test_o4_coordinator_isolation.py -q
  ```

  Expected: all pass.

- [ ] **Step 5: Controller commits Task 1 after independent review**

  ```bash
  git add scripts/harness_coordinator/v1/coordinator.py \
    scripts/harness_coordinator/v1/invoke.py \
    .claude/harness-selftest/test_o5_invocation_budgets.py
  git commit -m "fix: wire packet budgets into real worker invocation"
  ```

---

### Task 2: Deterministic risk-class hard-stop admission gate

**Files:**
- Modify: `scripts/harness_contracts/v1/packet.py`
- Modify: `schemas/harness/v1/packet.schema.json`
- Create: `scripts/harness_coordinator/v1/risk_classify.py`
- Modify: `scripts/harness_coordinator/v1/enroll.py`
- Create: `.claude/harness-selftest/test_o5_risk_classify.py`
- Modify existing packet fixtures across `.claude/harness-selftest/` that
  construct a full valid packet (they will need `risk_class` added — grep
  for `"budgets"` construction sites to find them all).

**Interfaces:**
- `packet.py` adds `RISK_CLASSES = {"routine", "hard_stop"}` and validates
  `value["risk_class"]` as a required enum field, same style as
  `network_policy`.
- `risk_classify.py` produces:
  `classify_risk(packet: Dict[str, Any]) -> Dict[str, Any]` returning
  `{"forced_class": "routine"|"hard_stop", "indicators": [{"code": str,
  "detail": str}]}` — pure, no I/O, no randomness. `indicators` is empty
  iff `forced_class == "routine"`.
- `enroll.py` calls `classify_risk` during preflight (same phase as
  existing `validate_packet` calls). If `forced_class == "hard_stop"` and
  `packet["risk_class"] != "hard_stop"`: raise `PacketPreflightError` with
  a clear code (e.g. `RISK_CLASS_MISMATCH`) citing the indicators —
  enrollment is refused entirely, same failure shape as an existing
  preflight rejection. If `packet["risk_class"] == "hard_stop"` (whether
  self-declared or matching a genuine indicator): enrollment proceeds, but
  the packet's initial state is `HUMAN_REQUIRED`, never `READY` — read
  `enroll.py`'s existing state-assignment logic to reuse its existing
  `HUMAN_REQUIRED`-producing path rather than inventing a second one.

- [ ] **Step 1: Write failing classifier tests**

  Table-driven: a packet with `writable_paths` touching `migrations/foo.sql`
  must classify `hard_stop` with an indicator citing the path; a packet
  whose `objective` contains `"run a production backfill"` must classify
  `hard_stop`; a packet with `network_policy: "allowed"` must classify
  `hard_stop` regardless of anything else; an ordinary repo-only packet
  (matching existing test fixtures' shape) must classify `routine` with
  empty indicators. Include at least one deliberately adversarial case —
  indicator text split across `objective` and `context` rather than one
  field, to prove the scan covers all the named fields, not just one.

- [ ] **Step 2: Write failing enrollment tests**

  A packet declaring `risk_class: "routine"` whose content triggers an
  indicator must fail `enroll_packet` (or whatever the real preflight
  entry point is named — confirm against `enroll.py`) with
  `RISK_CLASS_MISMATCH`, and must NOT be journaled as `PACKET_ENROLLED` in
  any state (verify via a journal read, not just the return value — an
  enrollment that partially wrote before failing would be worse than one
  that never tried). A packet declaring `risk_class: "hard_stop"`
  correctly must enroll successfully but land in `HUMAN_REQUIRED`, never
  become eligible via `scheduler.select_next`.

- [ ] **Step 3: Run and confirm RED**

  ```bash
  PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
    .claude/harness-selftest/test_o5_risk_classify.py -q
  ```

- [ ] **Step 4: Implement schema field, classifier, and enrollment gate**

  Add `risk_class` to `packet.schema.json`'s required properties and
  `packet.py`'s validator, matching the existing pattern for
  `network_policy`/`sonnet_reassignment_allowed`. Note this changes every
  packet's `packet_sha256` going forward — expected, not a defect (record
  it in the commissioning audit as an intentional packet-shape bump, same
  as O2/O3's own schema evolutions).

  Implement `risk_classify.py` as fixed constant lists (paths, keyword
  patterns with word-boundary regex, case-insensitive) scanning
  `objective`, `writable_paths`, `forbidden_surfaces`, and `context` (read
  the real packet schema for the exact field names/types of `context`
  before assuming its shape). No network access, no external data, no
  model call.

- [ ] **Step 5: Run Task 2 tests plus full O2/O3 schema + enrollment suite**

  ```bash
  PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
    .claude/harness-selftest/test_o5_risk_classify.py \
    .claude/harness-selftest/test_o2_json_schemas.py \
    .claude/harness-selftest/test_o2_packet_contract.py \
    .claude/harness-selftest/test_o3_p5_enrollment.py \
    .claude/harness-selftest/test_o3_scheduling.py -q
  ```

  Expected: all pass. Fix any existing fixture that now fails purely
  because it lacks `risk_class` — add `"risk_class": "routine"` to every
  pre-existing valid-packet fixture that has no hard-stop indicator in it
  (do not weaken the classifier to avoid touching fixtures).

- [ ] **Step 6: Controller commits Task 2 after independent review**

  ```bash
  git add scripts/harness_contracts/v1/packet.py \
    schemas/harness/v1/packet.schema.json \
    scripts/harness_coordinator/v1/risk_classify.py \
    scripts/harness_coordinator/v1/enroll.py \
    .claude/harness-selftest/
  git commit -m "feat: gate packet enrollment on deterministic risk class"
  ```

---

### Task 3: Bounded backoff and lane pause on confirmed exhaustion

**Files:**
- Modify: `scripts/harness_coordinator/v1/classify_runtime.py`
- Modify: `scripts/harness_coordinator/v1/recovery.py`
- Modify: `scripts/harness_coordinator/v1/run_cli.py`
- Create: `.claude/harness-selftest/test_o5_backoff_pause.py`

**Interfaces:**
- `classify_runtime.py` adds a pure `_compute_backoff(attempts_started:
  int) -> str` (returns an RFC3339 `earliest_next_attempt_at`-shaped
  offset from a `now` the caller supplies — no internal clock call) using
  a fixed deterministic formula, and wires its result into the fold
  wherever `attempt_budget_exhausted`/`fallback_not_permitted` currently
  gets set after a `PROVIDER_EXHAUSTED` classification (confirm the exact
  fold-update site in `recovery.py`/`classify_runtime.py` by reading, not
  guessing — the audit named `_resolve_reassignment_cause` and
  `_finish_attempt` as the decision points but the actual fold mutation
  may live in `recovery.py`'s journal-apply step).
- A new pure function (name your call; document it): derives
  `disabled_lanes: List[str]` from the fold — a lane is disabled once any
  packet's history shows a confirmed `PROVIDER_EXHAUSTED` resolving to
  `fallback_exhausted` (Sonnet lane itself exhausted) or
  `fallback_not_permitted` with the fallback lane also unavailable.
  Exposed from `reconcile.py` or `recovery.py` (whichever already owns
  fold-derived read helpers — follow existing module boundaries, don't
  create a new one for a single function unless nothing existing fits).
- `run_cli.py` calls this new function against current durable state
  before calling `run_once`, and passes the result as `disabled_lanes`
  instead of the current implicit `None`.

- [ ] **Step 1: Write failing backoff tests**

  A packet at `attempt_budget_exhausted` after a confirmed
  `PROVIDER_EXHAUSTED` must have a non-null `earliest_next_attempt_at`
  strictly greater than the attempt's `now`, computed deterministically
  (same inputs → same output — assert this directly, not just
  "non-null"). A packet whose exhaustion cause is unrelated (e.g. a plain
  `INFRA_RETRYABLE` budget exhaustion) must NOT get a backoff timestamp —
  only the provider-exhaustion path does.

- [ ] **Step 2: Write failing lane-disable tests**

  Construct fold fixtures where (a) Kimi is exhausted with Sonnet
  available → `disabled_lanes` empty (reassignment handles it); (b) Sonnet
  itself resolves `fallback_exhausted` → `disabled_lanes == ["sonnet_implementation"]`
  and, transitively, `["kimi_implementation"]` is NOT auto-disabled just
  because Sonnet is (they're independent failure surfaces — don't couple
  them without evidence); (c) no exhaustion anywhere → `disabled_lanes`
  empty.

- [ ] **Step 3: Run and confirm RED**

  ```bash
  PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
    .claude/harness-selftest/test_o5_backoff_pause.py -q
  ```

- [ ] **Step 4: Implement backoff computation and lane-disable derivation**

  Backoff formula must be simple, bounded, and documented inline (e.g.
  `min(2 ** (attempts_started - 1), 60)` minutes, capped — pick a concrete
  cap and state it in a comment, not a magic unexplained number). Format
  the result using the exact canonical RFC3339 form `scheduler.py`'s
  module docstring specifies (`^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) —
  reuse whatever helper the rest of the codebase already uses for this
  (`worker_result.RE_RFC3339`'s sibling formatter, if one exists — grep
  before writing a new one).

- [ ] **Step 5: Wire `run_cli.py`**

  Read current durable state, derive `disabled_lanes`, pass it into
  `run_once`. Confirm this doesn't change behavior for a state root with
  no exhaustion history (must still pass `[]`/`None` equivalently to
  today).

- [ ] **Step 6: Run Task 3 tests plus the full O3 classification/scheduling/reconciliation suite**

  ```bash
  PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
    .claude/harness-selftest/test_o5_backoff_pause.py \
    .claude/harness-selftest/test_o3_classification.py \
    .claude/harness-selftest/test_o3_scheduling.py \
    .claude/harness-selftest/test_o3_reconciliation.py \
    .claude/harness-selftest/test_o3_p5_commissioning.py -q
  ```

  Expected: all pass.

- [ ] **Step 7: Controller commits Task 3 after independent review**

  ```bash
  git add scripts/harness_coordinator/v1/classify_runtime.py \
    scripts/harness_coordinator/v1/recovery.py \
    scripts/harness_coordinator/v1/run_cli.py \
    .claude/harness-selftest/test_o5_backoff_pause.py
  git commit -m "fix: back off and pause a lane on confirmed provider exhaustion"
  ```

---

### Task 4: Sequential session driver with queue-wide limits

**Files:**
- Modify: `scripts/harness_coordinator/v1/coordinator.py`
- Create: `scripts/harness_coordinator/v1/run_session_cli.py`
- Modify: `scripts/harness_contracts/v1/provider_evidence.py`
- Create: `.claude/harness-selftest/test_o5_session_driver.py`

**Interfaces:**
- `coordinator.run_session(state_root, coordinator_id, run_id,
  trusted_process_context_factory, now_factory, *, max_packets:
  Optional[int] = None, max_session_wall_clock_seconds: Optional[float] =
  None, worker_adapters=None, protected_worktree_path=None) -> Dict[str,
  Any]` — loops calling `run_once` (deriving fresh `disabled_lanes` each
  iteration via Task 3's new function), stopping per the spec's four
  conditions. Returns a summary: packets processed, per-packet outcomes,
  final `disabled_lanes`, and `stop_reason` (enum:
  `"no_eligible_work"|"max_packets_reached"|"session_wall_clock_exceeded"|"all_lanes_disabled"`).
  `now_factory` and `trusted_process_context_factory` are callables so the
  loop itself never calls `datetime.now()`/derives process identity
  internally — same testability property as every other pure O3/O4
  component. `max_packets`/`max_session_wall_clock_seconds` of `None`
  means "no limit on this dimension" (still bounded by the other three
  stop conditions — a session can never loop forever even with both
  unset, since `no_eligible_work`/`all_lanes_disabled` are always live).
- `run_session_cli.py` mirrors `run_cli.py`'s structure: parses
  `--state-root`, `--coordinator-id`, `--run-id`, `--max-packets`,
  `--max-wall-clock-seconds`, calls `datetime.now()`/derives process
  context once per loop iteration (passed as the factories), and prints
  one JSON session summary.
- `provider_evidence.py`: add a module-level constant (e.g.
  `MAX_VERBATIM_EXCERPT_BYTES = 4096`) and enforce
  `matched_signal.byte_length <= MAX_VERBATIM_EXCERPT_BYTES` in the
  existing validator function, same error style as the existing
  `byte_length`/`byte_offset` checks.

- [ ] **Step 1: Write failing session-driver tests**

  Using disposable fixtures (mirror O3/O4's fixture style — a tmp state
  root with several enrolled packets): (a) a queue with 3 eligible
  routine packets and no limits set drains to `no_eligible_work` after
  processing exactly 3; (b) `max_packets=1` stops after exactly 1 with
  `max_packets_reached` and 2 packets still `READY`; (c) inject a
  `now_factory` that jumps past `max_session_wall_clock_seconds` between
  iterations and confirm the loop stops with
  `session_wall_clock_exceeded` before processing every eligible packet;
  (d) construct fold state where every lane is already disabled (reuse
  Task 3's fixtures) and confirm `run_session` returns immediately with
  `all_lanes_disabled` and zero packets processed, never raising.

- [ ] **Step 2: Write failing excerpt-cap tests**

  A `matched_signal` with `byte_length` over the new constant must fail
  validation with a clear error code; at-or-under the cap must pass
  exactly as before this task.

- [ ] **Step 3: Run and confirm RED**

  ```bash
  PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
    .claude/harness-selftest/test_o5_session_driver.py -q
  ```

- [ ] **Step 4: Implement `run_session()`, the CLI, and the excerpt cap**

  `run_session()` must not duplicate `run_once`'s crash-safety logic — it
  is a thin loop, each iteration fully atomic via the existing
  `run_once`. Per-iteration errors from `run_once` that are *expected*
  operational states (a `HUMAN_REQUIRED` packet, a `QUARANTINE`) must not
  raise — only a genuine exception should stop the loop early (record it
  in the summary, don't swallow it silently).

- [ ] **Step 5: Run Task 4 tests plus the full suite so far**

  ```bash
  PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
    .claude/harness-selftest/test_o5_*.py \
    .claude/harness-selftest/test_o2_*.py \
    .claude/harness-selftest/test_o3_*.py \
    .claude/harness-selftest/test_o4_*.py -q
  ```

  Expected: all pass.

- [ ] **Step 6: Controller commits Task 4 after independent review**

  ```bash
  git add scripts/harness_coordinator/v1/coordinator.py \
    scripts/harness_coordinator/v1/run_session_cli.py \
    scripts/harness_contracts/v1/provider_evidence.py \
    .claude/harness-selftest/test_o5_session_driver.py
  git commit -m "feat: add sequential session driver and cap evidence excerpts"
  ```

---

### Task 5: Full verification, disposable O5 commissioning, and records close

**Files:**
- Create: `docs/audits/o5_budgets_and_hard_stops_2026-08-11.md`
- No source changes expected in this task beyond fixing findings from
  Step 1's review.

- [ ] **Step 1: Disposable multi-condition O5 commissioning test**

  In a disposable repository/state root (same fixture style as O3-P5E/O4's
  Task 5), run a scripted scenario through the real coordinator proving,
  in one connected run:
  - a `hard_stop`-indicator packet is refused at enrollment (or lands in
    `HUMAN_REQUIRED` if self-declared correctly) and is never dispatched
  - a packet whose declared `wall_clock_seconds` is shorter than its
    synthetic adapter's runtime actually times out (not the 30s default)
  - a confirmed provider-exhaustion sequence produces a real
    `earliest_next_attempt_at` and, once fallback is exhausted, a
    disabled lane
  - `run_session()` processes every remaining eligible routine packet in
    one call, stops with a real stop reason, and the run is still fully
    reconciliation-clean (`all_invariants_passed`)
  - a second lane's packets keep processing normally throughout the
    exhausted lane's disablement — proving bullet 4 concretely, not just
    by assertion

- [ ] **Step 2: Run full verification**

  ```bash
  PYTHONPYCACHEPREFIX=/tmp/rhemata-o5-pycache \
  PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
    .claude/harness-selftest/test_o2_*.py \
    .claude/harness-selftest/test_o3_*.py \
    .claude/harness-selftest/test_o4_*.py \
    .claude/harness-selftest/test_o5_*.py -q

  PYTHONPYCACHEPREFIX=/tmp/rhemata-o5-pycache \
  PYTHONPATH=scripts:.claude/harness-selftest python3 -m py_compile \
    scripts/harness_contracts/v1/*.py scripts/harness_coordinator/v1/*.py

  python3 .claude/harness-selftest/test_current_routing_contract.py
  python3 .claude/harness-selftest/test_sql_verb_narrowing.py
  python3 .claude/harness-selftest/test_write_accounting_loop_fix.py
  git diff --check main...HEAD
  ```

  Expected: every command exits 0. Record exact test totals, commands,
  and any residual limitations (turn counting, allowance metering,
  `guard_denials` ingestion, full log redaction — the spec's "explicitly
  not built" list) in `docs/audits/o5_budgets_and_hard_stops_2026-08-11.md`.

- [ ] **Step 3: Controller commits commissioning evidence separately**

  ```bash
  git add docs/audits/o5_budgets_and_hard_stops_2026-08-11.md
  git commit -m "docs: record O5 budgets and hard-stops commissioning"
  ```

- [ ] **Step 4: Final branch review and records close**

  Request an independent fresh (no prior context) whole-branch review
  against this plan and the design spec. Resolve every load-bearing
  finding, rerun full verification, then update `PLAN.md`'s O5 section
  (check the four exit-criteria boxes, or explain precisely which remain
  open and why) and overwrite `rhemata-status.md`'s "Current state"/"Next"
  sections in a separate records-only commit. Do not merge or push
  without Alex's explicit approval.

---

## Plan self-review checklist

- Every O5 exit-criteria bullet maps to a task above (bullet 1 → Task 1;
  bullet 3 → Task 2; bullet 2 → Task 3; bullet 4 → Task 4).
- No task re-implements an existing O1–O4 mechanism; each reuses or wires
  what the gap analysis found already built.
- Backoff/pause/session-driver logic stays a pure function of durable
  state plus explicit `now`/context arguments — no implicit clock.
- Risk-class classification is deterministic content matching only — no
  model call, consistent with this repo's standing rejection of LLM-judge
  mechanisms for safety-critical gates.
- Build, commissioning-audit, and final records commits are separate.
- Real-provider commissioning, turn/allowance accounting, `guard_denials`
  ingestion, and O6 concurrency remain explicitly out of O5, named in the
  audit rather than silently dropped.
