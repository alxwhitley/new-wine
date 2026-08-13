# O5 Budgets and Hard Stops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind every coordinator run to one authenticated finite execution plan and enforce crash-safe packet, process, provider, routing, and human-stop boundaries without silently downgrading capability or claiming extra work.

**Architecture:** Add a closed execution-plan contract and a pure budget/routing decision layer, then integrate those decisions at the coordinator's existing pre-claim, invocation, recovery, and reconciliation boundaries. Durable journal events remain the sole accounting authority; provider and worker output remain untrusted until validated through existing evidence paths.

**Tech Stack:** Python 3 standard library, JSON Schema Draft 2020-12, append-only SHA-256 journal, pytest synthetic adapters/disposable Git repositories.

## Global Constraints

- Follow `AGENTS.md`, `CLAUDE.md`, `PLAN.md`, and `docs/superpowers/specs/2026-08-11-o5-budgets-hard-stops-design.md` in full.
- Work only on `codex/o5-budgets-hard-stops` in the clean isolated worktree; never modify, clean, stage, switch, or otherwise disturb `/Users/alexwhitley/rhemata`.
- Workers and reviewers never stage, commit, merge, push, clean, delete, deploy, access production DB/network, commission real providers, or alter governed content.
- The controller alone makes one build commit after each accepted task; docs/records commits stay separate.
- Use fake clocks, synthetic provider evidence, disposable state roots, and synthetic adapters only.
- Subscription capacity is observed provider state, never estimated monetary spend.
- Graceful limits finish the active attempt and stop before the next claim; command timeout, output overflow, operator stop, containment loss, and O4 isolation failures remain immediate.
- Fallback is acyclic, same-capability-class, explicitly qualified, plan-pinned, and authority-neutral.
- `design_judgment` remains Fable-only until Alex separately enables the disabled `gpt-5.6-sol` design candidate.
- Preserve closed schemas, canonical bytes, boolean-as-integer rejection, stable reason codes, collision-safe publication, and pinned state-root access.
- Full completion requires the exact O2/O3/O4/O5 suite, the three legacy guards, scoped `py_compile`, both diff checks, commissioning reconciliation, and independent high-reasoning `ACCEPT`.

---

### Task 1: Authenticated execution-plan contract and binding

**Files:**
- Create: `schemas/harness/v1/execution-plan.schema.json`
- Create: `scripts/harness_contracts/v1/execution_plan.py`
- Create: `.claude/harness-selftest/test_o5_execution_plan.py`
- Modify: `scripts/harness_contracts/v1/__init__.py`
- Modify: `schemas/harness/v1/journal-event.schema.json`
- Modify: `scripts/harness_contracts/v1/journal.py`
- Modify: `scripts/harness_coordinator/v1/recovery.py`

**Interfaces:**
- Produces: `validate_execution_plan(value: Any) -> Dict[str, Any]`.
- Produces: `execution_plan_sha256(plan: Dict[str, Any]) -> str` over canonical bytes omitting only `plan_sha256`.
- Produces: `bind_execution_plan(handle, raw: bytes, coordinator_id: str, run_id: str, now: str) -> Dict[str, Any]` that collision-safely publishes `plans/<plan_id>.json` and returns the validated plan.
- Produces journal event `EXECUTION_PLAN_BOUND` with payload keys `plan_id`, `plan_sha256`, `plan_path`, and `packet_count`.
- Consumes existing `canonical_bytes`, `compute_sha256`, pinned state-root handles, and journal append/fold primitives.

- [ ] **Step 1: Write failing contract tests**

Add canonical valid-plan and invalid-plan fixtures. The valid fixture must include exact packet digests, dependencies, capability classes, resolved routes, packet budgets, provider backoff, human-stop categories, and a positive `wall_clock_safety_seconds`.

```python
def test_execution_plan_is_closed_canonical_and_hash_bound():
    plan = _valid_plan()
    assert validate_execution_plan(plan)["valid"] is True
    assert plan["plan_sha256"] == execution_plan_sha256(plan)
    extra = copy.deepcopy(plan)
    extra["unexpected"] = True
    assert validate_execution_plan(extra)["errors"][0]["code"] == "UNKNOWN_PROPERTY"


@pytest.mark.parametrize("mutation", [
    "boolean_budget", "duplicate_packet", "dependency_outside_plan",
    "packet_digest_mismatch", "fallback_cycle", "enabled_unqualified_model",
    "design_sol_enabled", "noncanonical_model_id", "zero_wall_clock",
])
def test_execution_plan_rejects_authority_and_identity_bypasses(mutation):
    plan = _mutated_plan(mutation)
    assert validate_execution_plan(plan)["valid"] is False
```

- [ ] **Step 2: Run the new tests and prove RED**

Run:

```bash
PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o5_execution_plan.py -q
```

Expected: collection or import failure because `execution_plan.py` and its schema do not exist.

- [ ] **Step 3: Implement the closed execution-plan validator**

Use exact top-level keys:

```python
REQUIRED = {
    "schema_version", "plan_id", "plan_sha256", "packets", "routes",
    "provider_backoff", "wall_clock_safety_seconds", "human_stop_categories",
}
CAPABILITY_CLASSES = {
    "design_judgment", "planning_architecture", "implementation",
    "independent_review", "adversarial_audit", "mechanical_check",
}
```

Each packet row must contain `packet_id`, `packet_sha256`, `dependencies`, `capability_class`, and a closed `budgets` object. Each route hop must contain exact `provider`, `model_id`, `minimum_reasoning`, `enabled`, and `qualification_id`. Reject booleans for integers, duplicate IDs, dependencies outside membership, route cycles, missing qualification IDs, enabled `gpt-5.6-sol` under `design_judgment`, and noncanonical hashes.

- [ ] **Step 4: Add durable plan binding and replay validation**

Add `EXECUTION_PLAN_BOUND` to runtime and JSON Schema enums with a closed payload. Recovery must reject a second different plan binding for one `run_id`, missing plan artifacts, hash disagreement, noncanonical bytes, and packet membership/digest drift.

```python
def test_second_different_plan_for_run_is_integrity_error(tmp_path):
    state = _state_with_bound_plan(tmp_path, _valid_plan("plan-a"))
    with pytest.raises(IntegrityError, match="PLAN_IDENTITY_CONFLICT"):
        _bind(state, _valid_plan("plan-b"))
```

- [ ] **Step 5: Verify Task 1**

Run the O5 contract test, O2/O3 JSON-schema suites, O3 enrollment/recovery suites, `py_compile`, and `git diff --check`. Expected: all pass and no existing pre-O5 journal becomes invalid merely because it has no O5 plan event.

- [ ] **Step 6: Controller review and commit**

After independent spec and quality review returns `ACCEPT`, the controller stages only Task 1 files and commits:

```bash
git commit -m "feat: bind coordinator runs to execution plans"
```

---

### Task 2: Pure budget accounting and capability routing

**Files:**
- Create: `scripts/harness_coordinator/v1/budget_runtime.py`
- Create: `.claude/harness-selftest/test_o5_budget_runtime.py`
- Modify: `scripts/harness_contracts/v1/provider_evidence.py`
- Modify: `schemas/harness/v1/provider-evidence.schema.json`
- Modify: `schemas/harness/v1/journal-event.schema.json`
- Modify: `scripts/harness_contracts/v1/journal.py`

**Interfaces:**
- Consumes: validated execution plan, folded packet rows, authenticated journal events, validated provider evidence, and caller-supplied `now_utc`.
- Produces: immutable `BudgetDecision` represented as a closed dict with `decision`, `reason_code`, `packet_id`, `route`, `next_eligible_at`, and `evidence_ids`.
- Produces: `evaluate_preclaim(plan, packet, journal_events, provider_state, now_utc) -> Dict[str, Any]`.
- Produces: `select_capable_route(plan, capability_class, journal_events, provider_state, now_utc) -> Dict[str, Any]`.
- Produces events `PROVIDER_CAPACITY_RECORDED`, `PROVIDER_BACKOFF_SCHEDULED`, `MODEL_FALLBACK_SELECTED`, and `PACKET_PAUSED`.

- [ ] **Step 1: Write table-driven RED tests for accounting**

```python
@pytest.mark.parametrize(("attempts", "limit", "decision"), [
    (0, 0, "STOP"), (0, 1, "ALLOW"), (1, 1, "STOP"),
])
def test_attempt_limit_is_checked_before_claim(attempts, limit, decision):
    result = evaluate_preclaim(
        _plan(attempt_limit=limit), _packet(attempts_started=attempts), [], {}, T_NOW)
    assert result["decision"] == decision


def test_worker_report_cannot_increase_remaining_budget():
    events = [_authenticated_attempt_started(), _worker_claims_zero_usage()]
    assert evaluate_preclaim(_plan(attempt_limit=1), _packet(1), events, {}, T_NOW)[
        "reason_code"] == "PACKET_BUDGET_ATTEMPTS_EXHAUSTED"
```

Include exact-boundary, boolean, duplicate-event, missing-event, clock-regression, plan-member mismatch, and cache-disagreement cases.

- [ ] **Step 2: Write routing and exhaustion RED tests**

```python
def test_design_route_pauses_instead_of_using_disabled_sol():
    result = select_capable_route(
        _plan_with_fable_and_disabled_sol(), "design_judgment", [],
        {"anthropic/fable": "EXHAUSTED"}, T_NOW)
    assert result["decision"] == "PAUSE"
    assert result["reason_code"] == "NO_CAPABLE_MODEL_AVAILABLE"


def test_implementation_fallback_is_same_class_and_acyclic():
    result = select_capable_route(
        _implementation_plan(), "implementation", [_kimi_exhausted_event()],
        _provider_state(kimi="EXHAUSTED", openai="AVAILABLE"), T_NOW)
    assert result["route"]["model_id"] == "gpt-5.6-terra"
```

Cover Grok adversarial/review routing, exact plan-pinned OpenCode Go IDs, runtime catalog drift, executor/reviewer family diversity, stale reset evidence, exhausted-hop replay, and cross-class substitution.

- [ ] **Step 3: Implement pure deterministic decisions**

No function in `budget_runtime.py` writes files, journals, invokes providers, or reads environment variables. Sort all reason/evidence lists. Compare only normalized UTC timestamps validated by existing timestamp helpers. Detect fallback cycles during plan validation and again defensively at fold time.

Decision vocabulary is closed:

```python
DECISIONS = {"ALLOW", "BACKOFF", "FALLBACK", "PAUSE", "STOP", "HUMAN_REQUIRED"}
```

- [ ] **Step 4: Extend authenticated provider capacity evidence**

Add a closed capacity observation containing provider, exact model ID, state (`AVAILABLE`, `RATE_LIMITED`, `ALLOWANCE_EXHAUSTED`, `UNAVAILABLE`), observed/reset timestamps, and evidence digest. Never persist raw headers, credentials, response bodies, subscription identifiers, or prompt content.

- [ ] **Step 5: Verify Task 2**

Run Task 2 tests plus existing provider-evidence, classification, scheduling, reconciliation, and JSON Schema tests. Run compilation and diff checks. Expected: deterministic results under shuffled input event order and no mutation of arguments.

- [ ] **Step 6: Controller review and commit**

After independent `ACCEPT`, controller commit:

```bash
git commit -m "feat: derive budget and model routing decisions"
```

---

### Task 3: Invocation safety limits and durable graceful-stop state

**Files:**
- Modify: `scripts/harness_coordinator/v1/invoke.py`
- Modify: `scripts/harness_coordinator/v1/process_sidecar.py`
- Modify: `scripts/harness_coordinator/v1/coordinator.py`
- Modify: `scripts/harness_coordinator/v1/recovery.py`
- Modify: `schemas/harness/v1/journal-event.schema.json`
- Modify: `scripts/harness_contracts/v1/journal.py`
- Create: `.claude/harness-selftest/test_o5_hard_stops.py`
- Modify: `.claude/harness-selftest/test_o3_p5_invocation.py`

**Interfaces:**
- Produces: `request_graceful_stop(..., reason_code: str, evidence_ids: List[str])` and `make_graceful_stop_effective(...)` journal helpers.
- Produces events `GRACEFUL_STOP_REQUESTED` and `GRACEFUL_STOP_EFFECTIVE` bound to plan/run identities.
- Changes `invoke_worker` call sites to pass plan-derived command timeout and output limit; adapters cannot override them upward.
- Consumes Task 2 `BudgetDecision` but does not duplicate routing/accounting logic.

- [ ] **Step 1: Write immediate-limit RED tests**

```python
def test_plan_output_limit_terminates_process_group_and_caps_artifacts(tmp_path):
    outcome = _invoke_with_plan_limit(tmp_path, output_bytes=1024,
                                      code="print('x' * 100000); sleep_forever()")
    assert outcome.termination_reason == "OUTPUT_LIMIT_EXCEEDED"
    assert len(outcome.stdout) + len(outcome.stderr) <= 1024
    assert _process_group_is_dead(outcome.pgid)


def test_adapter_cannot_raise_plan_command_timeout(tmp_path):
    outcome = _invoke_with_plan_limit(tmp_path, command_timeout=1,
                                      adapter_timeout=60, code="sleep_forever()")
    assert outcome.termination_reason == "COMMAND_TIMEOUT"
```

- [ ] **Step 2: Write graceful-stop crash matrix RED tests**

Cover stop observed while idle, while RUNNING, after worker exit/before receipt, after receipt/before postflight, after postflight/before stop-effective, and restart after each boundary.

```python
def test_queue_ceiling_during_attempt_finishes_then_blocks_next_claim(tmp_path):
    state = _two_packet_plan(tmp_path)
    _run_first_worker_while_fake_clock_crosses_ceiling(state)
    folded = _restart_and_fold(state)
    assert folded["packet-1"]["state"] in TERMINAL_OR_REVIEW_STATES
    assert folded["packet-2"]["state"] == "READY"
    assert _attempt_started_count(state, "packet-2") == 0
    assert _stop_events(state) == ["GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"]
```

- [ ] **Step 3: Implement exact stop ordering**

If no attempt is open, write requested/effective events before returning. If an attempt is open, record requested, complete receipt recovery and O4 postflight, resolve the attempt, then record effective. Every pre-claim path checks for an effective or pending stop before selection/claim. A restart treats requested-without-effective conservatively and completes recovery before making the stop effective.

- [ ] **Step 4: Preserve immediate process containment**

Retain process-group identity checks, bounded reads, and TERM→grace→KILL semantics. Add stable immediate reason codes without including command output in journal payloads. Assert no surviving child/grandchild in timeout and output-flood tests.

- [ ] **Step 5: Verify Task 3**

Run O5 hard-stop tests, all O3 invocation/resume/crash tests, O4 coordinator/isolation tests, compilation, and diff checks. Expected: pre-existing timeout/output tests still pass and graceful stops create zero extra `ATTEMPT_STARTED` events.

- [ ] **Step 6: Controller review and commit**

After independent `ACCEPT`, controller commit:

```bash
git commit -m "feat: enforce O5 invocation and graceful stops"
```

---

### Task 4: Coordinator plan scope, fallback, pause, and human gates

**Files:**
- Modify: `scripts/harness_coordinator/v1/coordinator.py`
- Modify: `scripts/harness_coordinator/v1/enroll.py`
- Modify: `scripts/harness_coordinator/v1/scheduler.py`
- Modify: `scripts/harness_coordinator/v1/recovery.py`
- Modify: `scripts/harness_coordinator/v1/classify_runtime.py`
- Modify: `scripts/harness_coordinator/v1/reassignment_runtime.py`
- Create: `.claude/harness-selftest/test_o5_coordinator_budgets.py`
- Modify: `.claude/harness-selftest/test_o3_classification.py`

**Interfaces:**
- Adds required O5 coordinator input `execution_plan_path` or already-open canonical plan bytes at the CLI boundary; internal code receives a validated plan object.
- Consumes `evaluate_preclaim` and `select_capable_route` from Task 2.
- Produces coordinator statuses `plan_complete`, `plan_stopped`, `awaiting_provider_reset`, `no_capable_model`, and existing statuses where compatible.
- Produces only journal events defined in Tasks 1–3; no new ad hoc event shape.

- [ ] **Step 1: Write plan-scope and one-extra-claim RED tests**

```python
def test_packet_outside_bound_plan_cannot_enroll(tmp_path):
    state = _bound_state(tmp_path, packet_ids=["p1"])
    with pytest.raises(IntegrityError, match="PLAN_SCOPE_PACKET_OUTSIDE_PLAN"):
        enroll_packets(state, [_packet("p2")])


def test_completed_plan_never_discovers_or_claims_more_work(tmp_path):
    state = _completed_single_packet_plan(tmp_path)
    result = run_once(...)
    assert result["status"] == "plan_complete"
    assert _attempt_started_packet_ids(state) == ["p1"]
```

Add simultaneous-selection tests proving two coordinators cannot each consume the last budget unit or claim after a graceful stop. Reuse existing singleton/claim locks rather than inventing a second lock hierarchy.

- [ ] **Step 2: Write provider fallback/pause RED tests**

Use synthetic authenticated signals only. Prove Kimi/OpenCode Go exhaustion routes an implementation packet to plan-pinned Terra or Sonnet; Fable exhaustion pauses design because Sol is disabled; review may route Sol→Fable→qualified Grok; no path crosses capability class or changes packet authority.

```python
def test_fable_exhaustion_pauses_design_without_claim(tmp_path):
    state = _design_plan_with_disabled_sol(tmp_path)
    _record_exhausted(state, provider="anthropic", model="claude-fable-5")
    result = run_once(...)
    assert result["status"] == "no_capable_model"
    assert _packet_state(state, "design-1") == "PAUSED"
    assert _attempt_started_count(state, "design-1") == 0
```

- [ ] **Step 3: Implement pre-claim gate ordering**

Under the existing coordinator singleton and journal serialization:

1. authenticate/bind the plan;
2. recover open attempts and pending graceful stops;
3. reconcile/fold;
4. verify plan membership and terminal partition;
5. evaluate stop/budget/provider/model decision;
6. persist fallback, backoff, pause, or stop decision;
7. run O4 preflight;
8. append `ATTEMPT_STARTED`; and
9. invoke the exact plan-pinned route.

No adapter lookup, provider catalog response, worker result, or cache may alter steps 4–8.

- [ ] **Step 4: Implement human authority gate**

Map packet authorities/actions to the closed plan `human_stop_categories`. Production DB, migration, deployment, destructive Git/filesystem, unapproved stage/commit/merge/push/clean/delete, governed content, licensing, real-provider commissioning, and material plan expansion yield `HUMAN_AUTHORITY_REQUIRED` before claim. Existing explicit approvals are not inferred across categories.

- [ ] **Step 5: Verify Task 4**

Run O5 coordinator tests plus all O3 scheduling/classification/enrollment/recovery and O4 isolation suites. Include a deterministic two-process last-budget contention test. Run compilation and diff checks.

- [ ] **Step 6: Controller review and commit**

After independent `ACCEPT`, controller commit:

```bash
git commit -m "feat: gate O5 coordinator work by plan and capability"
```

---

### Task 5: Reconciliation, commissioning, and milestone evidence

**Files:**
- Modify: `schemas/harness/v1/reconciliation-report.schema.json`
- Modify: `scripts/harness_contracts/v1/reconciliation.py`
- Modify: `scripts/harness_coordinator/v1/reconcile.py`
- Modify: `scripts/harness_coordinator/v1/run_cli.py`
- Modify: `scripts/harness_coordinator/v1/cli.py`
- Create: `.claude/harness-selftest/test_o5_reconciliation.py`
- Create: `.claude/harness-selftest/test_o5_commissioning.py`
- Create: `docs/audits/o5_budgets_hard_stops_2026-08-11.md`

**Interfaces:**
- Extends each reconciliation row with plan identity, capability class, route history, budget usage, provider/backoff state, stop reasons, and exactly one terminal disposition.
- Produces plan totals `planned`, `attempted`, `accepted`, `resting_revise`, `quarantined`, `paused_provider`, `blocked_human`, and `never_started`.
- Enforces `planned == accepted + resting_revise + quarantined + paused_provider + blocked_human + never_started` and independently reports attempted membership/count.
- CLI requires an execution plan for O5 mode and accepts only local canonical plan paths; no provider/network discovery is added.

- [ ] **Step 1: Write reconciliation identity RED tests**

```python
def test_terminal_partition_equals_authenticated_plan_membership():
    report = build_reconciliation_report(_commissioned_events())
    totals = report["plan_totals"]
    assert totals["planned"] == sum(totals[key] for key in (
        "accepted", "resting_revise", "quarantined", "paused_provider",
        "blocked_human", "never_started"))


@pytest.mark.parametrize("tamper", [
    "missing_member", "duplicate_disposition", "foreign_packet",
    "route_not_in_plan", "fallback_cycle", "attempt_over_limit",
    "stop_then_claim", "forged_provider_evidence", "clock_regression",
])
def test_reconciliation_fails_closed_on_o5_tamper(tamper):
    assert _report_for_tamper(tamper)["all_invariants_passed"] is False
```

- [ ] **Step 2: Build disposable multi-scenario commissioning**

Commission sequentially, not concurrently:

1. an implementation packet whose primary synthetic provider exhausts and whose plan-pinned fallback succeeds;
2. a design packet whose Fable signal exhausts and whose disabled Sol candidate causes a pause without invocation;
3. an active packet that finishes after the queue safety ceiling while the next packet remains never started;
4. a packet with `retry_limit=1` whose command timeout kills a
   child/grandchild process group on both bounded attempts and then
   deterministically quarantines the packet;
5. a packet with `retry_limit=1` whose output flood is capped and killed on
   both bounded attempts and then deterministically quarantines;
6. a human-authority packet blocked before claim; and
7. restart at every durable crash boundary followed by identical final accounting.

Expected hard reconciliation:

```python
assert totals == {
    "planned": 7,
    "accepted": 2,
    "resting_revise": 0,
    "quarantined": 2,
    "paused_provider": 1,
    "blocked_human": 1,
    "never_started": 1,
}
assert report["all_invariants_passed"] is True
```

The timeout and output-limit fixtures exhaust their single permitted retry, so
both must land in `quarantined`; changing that disposition requires a new
approved design, not a fixture adjustment.

- [ ] **Step 3: Add CLI and schema parity tests**

Prove missing/tampered/noncanonical plan paths fail before coordinator claim; legacy read/reconciliation commands remain available; runtime and JSON Schema accept/reject identical O5 event/report shapes; stdout/stderr/provider artifacts contain no credential-like fixture values or prompt bodies.

- [ ] **Step 4: Run the exact final verification matrix**

```bash
PYTHONPYCACHEPREFIX=/tmp/rhemata-o5-final-pycache \
PYTHONPATH=scripts:.claude/harness-selftest \
python3 -m pytest \
  .claude/harness-selftest/test_o2_*.py \
  .claude/harness-selftest/test_o3_*.py \
  .claude/harness-selftest/test_o4_*.py \
  .claude/harness-selftest/test_o5_*.py -q

PYTHONPYCACHEPREFIX=/tmp/rhemata-o5-final-pycache \
PYTHONPATH=scripts:.claude/harness-selftest \
python3 -m py_compile \
  scripts/harness_contracts/v1/*.py \
  scripts/harness_coordinator/v1/*.py

git diff --check
git diff --check main...HEAD
```

Run the three legacy guards from `/Users/alexwhitley/rhemata` without altering it:

```bash
python3 .claude/harness-selftest/test_current_routing_contract.py
python3 .claude/harness-selftest/test_sql_verb_narrowing.py
python3 .claude/harness-selftest/test_write_accounting_loop_fix.py
```

- [ ] **Step 5: Record commissioning evidence**

The audit records exact commit/tree identity, test counts/durations, crash and tamper matrices, plan reconciliation totals, primary-checkout before/after status digest, no-network/provider/DB proof, residual O6 concurrency boundary, and every non-action. Do not update `PLAN.md` or `rhemata-status.md` until final review accepts O5.

- [ ] **Step 6: Controller review and build/audit commits**

After task review and a fresh whole-branch high-reasoning review both return `ACCEPT`, controller commits build files first:

```bash
git commit -m "feat: reconcile and commission O5 hard stops"
```

Then commit the audit separately:

```bash
git commit -m "docs: record O5 hard-stop commissioning"
```

---

## Final records closeout

Only after the whole-branch reviewer returns Spec PASS, Quality PASS, `ACCEPT`:

1. Replace the existing O5 entry in `PLAN.md` with its final DONE record.
2. Overwrite the Current state and Next sections of `rhemata-status.md`.
3. Run `git diff --check`.
4. Make one records-only commit, separate from every build/audit commit:

```bash
git commit -m "docs: close O5 budgets milestone"
```

Do not merge or push without Alex's explicit approval.
