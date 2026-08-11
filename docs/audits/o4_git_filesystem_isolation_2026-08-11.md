# O4 Git/filesystem isolation commissioning — 2026-08-11

## Scope and changed-path audit

Task 5 completes recovery, reconciliation, and sequential disposable
commissioning for O4. The working-tree change set is limited to:

- `scripts/harness_coordinator/v1/recovery.py`
- `scripts/harness_coordinator/v1/reconcile.py`
- `scripts/harness_coordinator/v1/coordinator.py`
- `scripts/harness_contracts/v1/journal.py`
- `schemas/harness/v1/journal-event.schema.json`
- `.claude/harness-selftest/test_o4_coordinator_isolation.py`
- `.claude/harness-selftest/test_o3_classification.py`
- `.claude/harness-selftest/test_o3_p5_resume.py`
- `docs/audits/o4_git_filesystem_isolation_2026-08-11.md`

The journal/schema and two O3 fixture changes are the authorized compatibility
expansion needed for durable `INTEGRATION_MANIFEST_RECORDED` events and the now-
required postflight binding. No other path is changed.

## Recovery and tamper evidence

- `WORKSPACE_BASELINE_RECORDED`, `WORKSPACE_POSTFLIGHT_RECORDED`, and
  `INTEGRATION_MANIFEST_RECORDED` each bind exactly one stage-specific canonical
  artifact by packet, attempt intent, canonical path, content SHA-256, and
  artifact SHA-256. Recovery also checks schema version, artifact kind, packet
  digest, exact field set, and stage order.
- The five crash boundaries are covered: before baseline publication, after the
  baseline artifact but before its event, after the worker receipt but before
  postflight, after the postflight artifact but before its event, and after the
  postflight event but before integration publication. Pre-baseline crashes
  invoke the worker zero times. Every post-worker recovery finishes with exactly
  one invocation and one canonical artifact/event per stage; an additional
  resume does not duplicate any stage.
- The matrix exposed and fixed one real resume defect: after a resumed invocation
  the coordinator previously used the pre-invocation receipt value and tried to
  terminate the already-completed sidecar. It now re-reads the durable completion
  receipt before any uncertain-process handling.
- Reconciliation covers 21 artifact-tamper cases: three O4 stages multiplied by
  missing file, altered bytes, cross-packet identity, wrong intent, wrong content
  hash, wrong artifact hash, and contradictory `acceptance_allowed`. Every case
  reports `all_invariants_passed=false`, attributes
  `workspace_evidence_mismatch` to the enrolled packet, and retains that packet
  in the packet array.
- Four additional journal-binding cases cover a cross-packet event, wrong event
  intent, wrong binding path, and wrong byte length. Every workspace-fold error
  now carries the partial packet inventory, so reconciliation cannot replace the
  affected packet array with an empty one when the fold stops.
- Reconciliation reads workspace artifacts through the pinned state-root handle.
  Its stable O4 attention vocabulary is `workspace_baseline_missing`,
  `workspace_postflight_missing`, `workspace_evidence_mismatch`,
  `protected_worktree_changed`, `allowlist_violation`, `secret_like_diff`, and
  `integration_human_required`.
- O4 `RUN_STARTED` events authenticate the compatibility boundary with
  `contract_versions.workspace_evidence=1`. The runtime and JSON schema accept
  the absent key for pre-O4 journals but require version `1` whenever declared.
  Reconciliation maps attempts to that journaled run version only; a packet or
  workspace artifact cannot upgrade a legacy attempt to O4.
- Parsed workspace evidence must have a JSON object root before canonical/hash
  work. String, list, and scalar JSON roots all fail deterministically with an
  attributed `WORKSPACE_EVIDENCE_MISMATCH`.
- Runtime validation and reconciliation require the journaled
  `workspace_evidence` marker to be a non-boolean integer exactly equal to `1`.
  The negative parity matrix includes JSON `true`, preventing Python's
  `True == 1` behavior from authenticating an O4 run.

## Disposable two-packet commissioning

The commissioning test creates one disposable Git repository, a protected
checkout with pre-existing tracked and untracked dirt, two named packet branches
and registered packet worktrees, and one read-only integration-analysis branch.
The real coordinator runs the two packets sequentially; O6, not O4, owns the
concurrent rehearsal.

- Protected baseline: two dirty entries. The complete protected snapshot is
  identical after both workers.
- Packet writes are disjoint and both allowed deltas remain present:
  `scripts/o4-clean.py` and `scripts/o4-refused.py`.
- `o4-clean` reaches `ACCEPTED` and publishes one `CLEAN_CANDIDATE` integration
  manifest.
- `o4-refused` writes one additional undeclared untracked file,
  `forbidden-untracked.txt`. The file remains present with its contents for
  inspection, the postflight records `acceptance_allowed=false`, and the packet
  reaches `HUMAN_REQUIRED` rather than acceptance.
- The refused packet's allowed delta is evaluated against a descendant base that
  changes the same path. The mutation-free analyzer returns exactly
  `HUMAN_REQUIRED` with `INTEGRATION_CONFLICT_PATH_OVERLAP`. Because the packet
  is already refused by its authoritative postflight, the coordinator correctly
  publishes no integration manifest for it.

Exact final reconciliation from the commissioning state root:

```text
inventory_total=2
by_state: ACCEPTED=1 HUMAN_REQUIRED=1; all other states=0
attempts_started_total=2
results_recorded_total=2
verdicts_recorded_total=1
infra_retries_total=0 revise_verdicts_total=0 revise_cycles_total=0
reassignments_total=0 intents_abandoned_total=0 locks_reclaimed_total=0
sum_of_by_state=2 packets_array_length=2 distinct_packet_ids=2
equals_inventory_total=true all_invariants_passed=false
```

`all_invariants_passed=false` is expected: the retained undeclared file produces
the required `allowlist_violation` attention on `o4-refused`.

## Verification receipts

The exact prescribed suite completed with a real terminal receipt:

```text
PYTHONPYCACHEPREFIX=/tmp/rhemata-o4-pycache \
PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o2_*.py \
  .claude/harness-selftest/test_o3_*.py \
  .claude/harness-selftest/test_o4_*.py -q

796 passed in 62.85s (0:01:02)
```

A pre-Fix-Round-2 final receipt completed with `787 passed in 73.27s`. A prior
diagnostic run with `--durations=20` also completed: `783 passed in 60.03s`;
the slowest individual test was 1.66 seconds. The prior apparent hang was a
quiet buffered tail near 90%, not a blocked test or surviving worker process.

Additional exact checks:

```text
Fix Round 2 focused selection: 9 passed, 61 deselected in 1.14s
Affected recovery/reconciliation/schema/O4 files: 235 passed in 36.94s
Fix Round 3 focused selection: 10 passed, 61 deselected in 1.46s
Fix Round 3 affected recovery/reconciliation/schema/O4 files: 236 passed in 36.67s
Fix Round 3 full prescribed O2/O3/O4 suite: 796 passed in 62.85s
Final crash/commissioning/fold-attribution subset: 10 passed in 10.16s
py_compile scripts/harness_contracts/v1/*.py scripts/harness_coordinator/v1/*.py: exit 0
git diff --check main...HEAD: exit 0
git diff --check: exit 0
```

The three legacy guards were run from the primary checkout with bytecode writes
disabled. Each printed `ALL CHECKS PASSED`:

- `.claude/harness-selftest/test_current_routing_contract.py`
- `.claude/harness-selftest/test_sql_verb_narrowing.py`
- `.claude/harness-selftest/test_write_accounting_loop_fix.py`

The primary checkout's porcelain-status SHA-256 was identical before and after:
`80b900dc0c98e47117604e36a34a1519f88dfd81125d1030de092a16e2817c13`.

## Non-actions and residual boundary

No project or user worktree was created, removed, cleaned, overwritten, merged,
staged, committed, pushed, or deleted. Only pytest-managed disposable
repositories/worktrees were exercised. No production database, provider,
network, migration, deployment, governed record, or answer/retrieval path was
touched.

This is O4's sequential commissioning, not O6's concurrent multi-packet
rehearsal. It makes no concurrency-readiness claim.
