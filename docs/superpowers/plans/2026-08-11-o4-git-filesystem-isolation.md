# O4 Git and Filesystem Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic coordinator-owned Git/worktree preflight, postflight, protected-dirty-tree preservation, and mutation-free integration analysis for every write-capable harness packet.

**Architecture:** Extend the existing O3 coordinator with two focused modules. `workspace_evidence.py` owns Git identity, filesystem snapshots, ownership overlap, allowlist enforcement, worker-manifest comparison, and secret-like diff metadata; `integration_analysis.py` owns conservative ancestry/path-overlap advice. The coordinator durably publishes a baseline before invocation and a postflight artifact after every worker outcome, while reconciliation independently rehashes both artifacts.

**Tech Stack:** Python 3.9 standard library, Git plumbing invoked with argv arrays and `shell=False`, existing canonical JSON/SHA-256 helpers, pytest disposable repositories/worktrees.

## Global Constraints

- Python 3.9: use `Optional[str]`, never `str | None`.
- O4 is repo-only: no production DB/network access, provider commissioning, deployment, migration, push, or governed-content edit.
- Workers and coordinator never stage, commit, merge, rebase, clean, delete, or resolve conflicts.
- The operator provisions packet branches/worktrees; O4 validates but never creates or removes them.
- Direct Git/filesystem evidence is authoritative; worker `changed_files` is untrusted corroboration.
- Out-of-scope or uncertain changes remain intact and route to `HUMAN_REQUIRED`; never auto-revert.
- Evidence may contain paths, modes, object IDs, digests, rule IDs, and line numbers, but never file contents, secret values, environment values, or prompt payloads.
- Build commits and the final records commit remain separate.
- Tests mutate only disposable temporary repositories/worktrees, never the Rhemata checkout.

---

## File map

- Create `scripts/harness_coordinator/v1/workspace_evidence.py`: Git execution, registered-worktree identity, snapshots, ownership overlap, changed-file derivation, allowlist and worker-manifest comparison, protected-tree comparison, secret-like finding metadata, canonical evidence publication/loading.
- Create `scripts/harness_coordinator/v1/integration_analysis.py`: mutation-free ancestry/path-overlap analysis and canonical integration-manifest construction.
- Modify `scripts/harness_coordinator/v1/coordinator.py`: publish preflight before invocation, always run postflight after an invocation outcome, and prevent review/acceptance without valid workspace evidence.
- Modify `scripts/harness_coordinator/v1/reconcile.py`: independently load, validate, and rehash O4 artifacts; expose attention codes.
- Modify `scripts/harness_coordinator/v1/recovery.py`: fold O4 evidence journal bindings and resume postflight after worker completion without re-invocation.
- Modify `scripts/harness_coordinator/v1/invoke.py`: remove `_result_paths_allowed()` as an acceptance authority; retain it only as an early worker-result sanity check until Task 3 replaces its callers.
- Modify `scripts/harness_contracts/v1/packet.py`: expose the existing path
  normalizer through a public wrapper; do not fork path semantics.
- Create `.claude/harness-selftest/test_o4_workspace_evidence.py`: disposable Git/worktree unit and adversarial tests.
- Create `.claude/harness-selftest/test_o4_integration_analysis.py`: ancestry/path-overlap integration tests.
- Create `.claude/harness-selftest/test_o4_coordinator_isolation.py`: coordinator/recovery/reconciliation end-to-end tests.

---

### Task 1: Registered-worktree identity and canonical snapshots

**Files:**
- Create: `scripts/harness_coordinator/v1/workspace_evidence.py`
- Create: `.claude/harness-selftest/test_o4_workspace_evidence.py`

**Interfaces:**
- Produces: `WorkspaceEvidenceError(code: str, message: str)`.
- Produces: `inspect_worktree(repo_root: str, worktree_path: str, expected_branch: str, expected_revision: str) -> Dict[str, Any]`.
- Produces: `capture_snapshot(worktree_path: str) -> Dict[str, Any]`.
- Produces: `snapshot_sha256(snapshot: Dict[str, Any]) -> str`.
- Produces: `harness_contracts.v1.packet.normalize_repo_relative_path(path: str) -> Optional[str]`, a public wrapper over the existing private implementation.
- Internal Git runner: `_run_git(cwd: str, argv: List[str], timeout_seconds: int = 10) -> bytes`; always `subprocess.run(["git", *argv], shell=False, check=True, stdout=PIPE, stderr=PIPE, timeout=timeout_seconds)` with a minimal explicit environment containing only `PATH`, `LANG=C`, `LC_ALL=C`, `GIT_CONFIG_NOSYSTEM=1`, and `GIT_TERMINAL_PROMPT=0`.

- [ ] **Step 1: Write disposable-repository fixtures and failing identity tests**

Add a fixture that initializes a repository, configures a local test identity, commits `allowed/base.txt`, creates two named branches, and creates registered worktrees below `tmp_path`. Tests must call Git only inside `tmp_path`.

```python
def test_registered_branch_and_revision_are_pinned(repo_fixture):
    evidence = inspect_worktree(
        repo_fixture.root, repo_fixture.packet_worktree,
        "codex/packet-a", repo_fixture.packet_revision,
    )
    assert evidence["branch"] == "refs/heads/codex/packet-a"
    assert evidence["head"] == repo_fixture.packet_revision
    assert evidence["common_dir"] == repo_fixture.common_dir

@pytest.mark.parametrize("mutation", [
    "symlink", "detached", "wrong_branch", "wrong_revision", "foreign_repo",
])
def test_identity_mismatch_fails_before_snapshot(repo_fixture, mutation):
    repo_fixture.apply_identity_mutation(mutation)
    with pytest.raises(WorkspaceEvidenceError) as caught:
        inspect_worktree(repo_fixture.root, repo_fixture.packet_worktree,
                         "codex/packet-a", repo_fixture.packet_revision)
    assert caught.value.code.startswith("WORKTREE_IDENTITY_")
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o4_workspace_evidence.py \
  -k 'registered or identity' -q
```

Expected: collection/import failure because `workspace_evidence.py` does not exist.

- [ ] **Step 3: Implement no-shell Git identity inspection**

Parse `git worktree list --porcelain -z` as NUL-delimited records. Canonicalize operator paths with `os.path.realpath`, reject symlink endpoints via `os.lstat`, require exactly one record matching the canonical packet worktree, compare the record's `branch` and `HEAD`, and verify `git rev-parse --git-common-dir` resolves to the same common directory for repository root and packet worktree.

Return this exact shape before hashing:

```python
{
    "schema_version": 1,
    "repo_root": canonical_repo_root,
    "worktree_path": canonical_worktree,
    "common_dir": canonical_common_dir,
    "branch": "refs/heads/codex/packet-a",
    "head": forty_hex_revision,
}
```

Map failures to stable codes: `WORKTREE_IDENTITY_PATH`, `..._SYMLINK`, `..._REGISTRATION`, `..._COMMON_DIR`, `..._DETACHED`, `..._BRANCH`, and `..._REVISION`. Exception messages may name canonical paths and expected/actual revisions but never include Git stderr.

In `packet.py`, add:

```python
def normalize_repo_relative_path(path: str) -> Optional[str]:
    """Public O2 path-authority normalization; one implementation only."""
    return _normalize_relative_path(path)
```

All O4 code imports this wrapper rather than copying normalization logic.

- [ ] **Step 4: Add failing snapshot-shape tests**

Create tracked modification, staged addition, deletion, rename, executable-mode change, untracked file, and a dirty submodule in separate parametrized cases. Assert the snapshot contains sorted records with keys `path`, `kind`, `index_status`, `worktree_status`, `mode`, `object_id`, and `content_sha256`; absent values are `None`.

```python
def test_snapshot_is_canonical_and_complete(repo_fixture):
    repo_fixture.make_all_change_shapes()
    first = capture_snapshot(repo_fixture.packet_worktree)
    second = capture_snapshot(repo_fixture.packet_worktree)
    assert first == second
    assert [row["path"] for row in first["entries"]] == sorted(
        row["path"] for row in first["entries"])
    assert first["snapshot_sha256"] == snapshot_sha256(first)
    assert {row["kind"] for row in first["entries"]} >= {
        "tracked", "untracked", "submodule"
    }
```

- [ ] **Step 5: Implement canonical snapshot capture**

Use `git status --porcelain=v2 -z --untracked-files=all` plus `git ls-files -s -z` to capture index/worktree state. Hash regular untracked and worktree files by opening with `O_NOFOLLOW`; reject symlinks as entries with `kind="symlink"` and no followed-content digest. Record file mode from `lstat`. Do not enumerate ignored files. Compute `snapshot_sha256` using `canonical_bytes(snapshot, omit={"snapshot_sha256"})` and `compute_sha256`. `build_baseline()` in Task 2 refuses invocation unless the packet snapshot has zero entries; the protected worktree snapshot is allowed to contain arbitrary pre-existing dirt.

- [ ] **Step 6: Run Task 1 tests and the O2 path tests**

Run:

```bash
PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o4_workspace_evidence.py \
  .claude/harness-selftest/test_o2_packet_contract.py \
  .claude/harness-selftest/test_o2_replay.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add scripts/harness_coordinator/v1/workspace_evidence.py \
  scripts/harness_contracts/v1/packet.py \
  .claude/harness-selftest/test_o4_workspace_evidence.py
git commit -m "feat: capture pinned packet worktree evidence"
```

---

### Task 2: Ownership preflight and durable baseline evidence

**Files:**
- Modify: `scripts/harness_coordinator/v1/workspace_evidence.py`
- Modify: `scripts/harness_coordinator/v1/coordinator.py`
- Modify: `.claude/harness-selftest/test_o4_workspace_evidence.py`
- Create: `.claude/harness-selftest/test_o4_coordinator_isolation.py`

**Interfaces:**
- Produces: `validate_ownership(packet: Dict[str, Any], active_packets: List[Dict[str, Any]]) -> None`.
- Produces: `build_baseline(packet, repo_root, protected_worktree_path, active_packets) -> Dict[str, Any]`.
- Produces: `publish_workspace_artifact(handle, relative_parts: Tuple[str, ...], artifact: Dict[str, Any]) -> Dict[str, str]` returning `artifact_path`, `artifact_sha256`, and `content_sha256`.
- Produces: `ensure_attempt_baseline(handle, packet, intent_id, repo_root, protected_worktree_path, active_packets) -> Dict[str, Any]`.
- Coordinator contract: `WORKSPACE_BASELINE_RECORDED` is durably journaled before `invoke_worker()` can be called.

- [ ] **Step 1: Write failing ownership-overlap tests**

Parametrize exact worktree, exact branch, equal writable path, parent path, and child path. Terminal packets and read-only lanes do not conflict; two nonterminal write-capable packets do.

```python
@pytest.mark.parametrize("field", [
    "same_worktree", "same_branch", "equal_path", "parent_path", "child_path",
])
def test_nonterminal_write_ownership_conflicts(packet, field):
    active = conflicting_packet(packet, field, state="RUNNING")
    with pytest.raises(WorkspaceEvidenceError) as caught:
        validate_ownership(packet, [active])
    assert caught.value.code.startswith("OWNERSHIP_CONFLICT_")
```

- [ ] **Step 2: Run ownership tests and confirm RED**

Run the test above directly. Expected: missing `validate_ownership`.

- [ ] **Step 3: Implement normalized prefix ownership**

Reuse `harness_contracts.v1.packet.normalize_repo_relative_path` and equivalent path-overlap semantics through a new public `paths_overlap(a: str, b: str) -> bool` helper in `workspace_evidence.py`; do not fork normalization rules. A lane is write-capable when `writable_paths` is nonempty. Compare only active states `READY`, `RUNNING`, `REVIEW`, and `REVISE`.

- [ ] **Step 4: Write failing durable-baseline/crash tests**

Monkeypatch `invoke_worker` to assert a canonical artifact exists at `workspace/<packet_id>/<intent_id>.baseline.json` and a matching `WORKSPACE_BASELINE_RECORDED` event is already in the journal. Inject failure before publication and after artifact publication/before journal append; prove the former never invokes and the latter resumes idempotently without creating a second baseline.

- [ ] **Step 5: Implement baseline artifact publication and coordinator gate**

Baseline exact top-level fields:

```python
{
    "schema_version": 1,
    "artifact_kind": "workspace_baseline",
    "packet_id": packet["packet_id"],
    "packet_sha256": packet["packet_sha256"],
    "intent_id": intent_id,
    "worktree_identity": identity,
    "packet_snapshot": packet_snapshot,
    "protected_snapshot": protected_snapshot_or_none,
    "writable_paths": sorted(packet["writable_paths"]),
    "forbidden_surfaces": sorted(packet["forbidden_surfaces"]),
    "content_sha256": "",
    "artifact_sha256": "",
}
```

Publish through the pinned state-root handle under a validated packet/intent path. Compute content hash omitting both hash fields and artifact hash omitting only `artifact_sha256`. Journal only the path and both hashes. On resume, load and rehash the existing artifact; mismatch raises `IntegrityError` and never invokes.

- [ ] **Step 6: Run Task 2 tests**

```bash
PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o4_workspace_evidence.py \
  .claude/harness-selftest/test_o4_coordinator_isolation.py \
  .claude/harness-selftest/test_o3_p5_enrollment.py \
  .claude/harness-selftest/test_o3_p5_commissioning.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add scripts/harness_coordinator/v1/workspace_evidence.py \
  scripts/harness_coordinator/v1/coordinator.py \
  .claude/harness-selftest/test_o4_workspace_evidence.py \
  .claude/harness-selftest/test_o4_coordinator_isolation.py
git commit -m "feat: gate invocation on workspace ownership"
```

---

### Task 3: Authoritative postflight, allowlist enforcement, and secret-safe findings

**Files:**
- Modify: `scripts/harness_coordinator/v1/workspace_evidence.py`
- Modify: `scripts/harness_coordinator/v1/coordinator.py`
- Modify: `scripts/harness_coordinator/v1/invoke.py`
- Modify: `.claude/harness-selftest/test_o4_workspace_evidence.py`
- Modify: `.claude/harness-selftest/test_o4_coordinator_isolation.py`

**Interfaces:**
- Produces: `derive_changes(baseline_snapshot, current_snapshot) -> List[Dict[str, Any]]`.
- Produces: `compare_worker_manifest(derived, claimed) -> List[Dict[str, str]]`.
- Produces: `scan_secret_like_additions(worktree_path, changes, maximum_bytes=1048576) -> List[Dict[str, Any]]`.
- Produces: `build_postflight(packet, intent_id, baseline, worker_result) -> Dict[str, Any]`.
- Coordinator contract: `WORKSPACE_POSTFLIGHT_RECORDED` exists before worker result can advance to review; postflight runs for completed, failed, timed-out, malformed, and interrupted outcomes.

- [ ] **Step 1: Write failing derived-manifest and allowlist tests**

Cover added, modified, deleted, renamed, mode-changed, staged, untracked, symlink, and submodule drift. Assert an undeclared, forbidden, governed, escaped, symlink, or submodule change yields a finding whose code starts `ALLOWLIST_VIOLATION_` and sets `acceptance_allowed` false. Assert files remain present after refusal.

- [ ] **Step 2: Write failing worker-manifest mismatch tests**

Use coordinator-derived changes as truth and parametrize a worker omission, invented path, incorrect status, wrong before digest, and wrong after digest. Require `WORKER_MANIFEST_MISMATCH_*` with path only; exact agreement returns an empty finding list.

- [ ] **Step 3: Implement snapshot diff and scope comparison**

Key entries by normalized path. A rename is recognized only when porcelain-v2 supplies the original path; otherwise represent deletion plus addition. Preserve status vocabulary accepted by the existing worker-result contract (`added`, `modified`, `deleted`, `renamed`) and add non-contract metadata (`mode_changed`, `index_status`, `worktree_status`) only to the coordinator artifact. Use O2 governed-path and forbidden-surface checks; do not weaken replay validation.

- [ ] **Step 4: Write failing protected-tree and secret-scan tests**

Seed a protected worktree with pre-existing tracked and untracked dirt. Prove an isolated packet leaves its complete snapshot equal. Then mutate one protected tracked file and add one untracked file; both yield `PROTECTED_WORKTREE_CHANGED_*`.

For secret scanning, add lines matching private-key header, assignment to `API_KEY`, bearer token, and common cloud credential prefix. Assert artifacts contain only:

```python
{"code": "SECRET_LIKE_DIFF_PATTERN", "rule_id": "api_key_assignment",
 "path": "allowed/new.py", "line": 7}
```

Assert the literal fixture secret does not occur in canonical artifact bytes. Binary, >1 MiB, unreadable, and symlink additions yield metadata-only `SECRET_LIKE_DIFF_REVIEW_REQUIRED`.

- [ ] **Step 5: Implement secret-safe scanning and protected comparison**

Read only regular changed additions/modifications with `O_NOFOLLOW`, cap at 1,048,576 bytes, decode UTF-8 strictly, inspect added lines from `git diff --unified=0 --no-ext-diff --no-textconv <starting_revision> --`, and never retain the matched group. Because preflight requires a clean packet worktree at `starting_revision`, this diff is exactly the worker delta; no baseline content needs to be persisted. Pattern rules are fixed constants with stable IDs. A match or unscannable addition routes to `HUMAN_REQUIRED`; it is not automatically deleted or redacted.

- [ ] **Step 6: Implement and durably publish postflight**

Postflight exact top-level fields mirror baseline identity and add `derived_changes`, `scope_findings`, `worker_manifest_findings`, `protected_findings`, `secret_findings`, and `acceptance_allowed`. Revalidate worktree identity before snapshot. Publish and journal with the same hash ordering as Task 2. Replace `_result_paths_allowed()` as the coordinator's acceptance gate; keep worker-result schema validation unchanged.

If postflight cannot complete, persist/return `HUMAN_REQUIRED`; never reinterpret it as ordinary worker failure eligible for Kimi→Sonnet fallback.

- [ ] **Step 7: Run Task 3 tests**

```bash
PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o4_workspace_evidence.py \
  .claude/harness-selftest/test_o4_coordinator_isolation.py \
  .claude/harness-selftest/test_o2_bypasses.py \
  .claude/harness-selftest/test_o2_replay.py \
  .claude/harness-selftest/test_o3_p5_invocation.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add scripts/harness_coordinator/v1/workspace_evidence.py \
  scripts/harness_coordinator/v1/coordinator.py \
  scripts/harness_coordinator/v1/invoke.py \
  .claude/harness-selftest/test_o4_workspace_evidence.py \
  .claude/harness-selftest/test_o4_coordinator_isolation.py
git commit -m "feat: enforce packet changes from Git evidence"
```

---

### Task 4: Mutation-free integration analysis

**Files:**
- Create: `scripts/harness_coordinator/v1/integration_analysis.py`
- Create: `.claude/harness-selftest/test_o4_integration_analysis.py`
- Modify: `scripts/harness_coordinator/v1/coordinator.py`

**Interfaces:**
- Produces: `analyze_integration(repo_root: str, starting_revision: str, integration_base: str, packet_changes: List[Dict[str, Any]], integration_target_path: Optional[str] = None) -> Dict[str, Any]`.
- Produces: `build_integration_manifest(packet, postflight, analysis) -> Dict[str, Any]`.
- Result enum: `CLEAN_CANDIDATE` or `HUMAN_REQUIRED`; never `MERGED`, `COMMITTED`, or another mutation-implying state.

- [ ] **Step 1: Write failing ancestry and overlap tests**

In a disposable repository, create a packet branch changing `allowed/a.py`; create descendant integration bases with disjoint and overlapping changes, plus a divergent branch. Assert:

```python
assert analyze_integration(...disjoint...)["decision"] == "CLEAN_CANDIDATE"
assert analyze_integration(...overlap...)["reason_codes"] == [
    "INTEGRATION_CONFLICT_PATH_OVERLAP"
]
assert analyze_integration(...divergent...)["decision"] == "HUMAN_REQUIRED"
```

Also test missing revision/object and a supplied dirty integration-target worktree. Capture refs, index checksum, status, and object count before/after each call; assert equality to prove analysis is mutation-free.

- [ ] **Step 2: Run focused integration tests and confirm RED**

Expected: import failure because `integration_analysis.py` does not exist.

- [ ] **Step 3: Implement conservative read-only analysis**

Use only `git merge-base --is-ancestor`, `git diff --name-only -z <starting>..<integration_base>`, `git cat-file -e`, and `git status --porcelain=v2 -z`. Invoke by argv with `shell=False`. Normalize changed paths with the same helper as workspace evidence. Any packet/base path overlap, non-descendant base, missing object, dirty target, invalid path, or command uncertainty produces sorted reason codes and `HUMAN_REQUIRED`.

- [ ] **Step 4: Implement canonical integration manifest and coordinator publication**

Manifest fields: packet identity, starting revision, integration base, derived changed paths/statuses/digests, verification evidence IDs, protected-tree result, secret result, analysis decision/reason codes, and `required_human_action`. Compute content/artifact hashes using the established O4 order and publish under `workspace/<packet_id>/<intent_id>.integration.json`. Do not journal or publish a manifest unless the postflight artifact rehashes successfully.

- [ ] **Step 5: Run Task 4 tests**

```bash
PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o4_integration_analysis.py \
  .claude/harness-selftest/test_o4_coordinator_isolation.py -q
```

Expected: all pass and repository mutation assertions hold.

- [ ] **Step 6: Commit Task 4**

```bash
git add scripts/harness_coordinator/v1/integration_analysis.py \
  scripts/harness_coordinator/v1/coordinator.py \
  .claude/harness-selftest/test_o4_integration_analysis.py \
  .claude/harness-selftest/test_o4_coordinator_isolation.py
git commit -m "feat: emit safe packet integration manifests"
```

---

### Task 5: Recovery, reconciliation, and disposable O4 commissioning

**Files:**
- Modify: `scripts/harness_coordinator/v1/recovery.py`
- Modify: `scripts/harness_coordinator/v1/reconcile.py`
- Modify: `scripts/harness_coordinator/v1/coordinator.py`
- Modify: `.claude/harness-selftest/test_o4_coordinator_isolation.py`
- Modify: `.claude/harness-selftest/test_o3_crash_recovery.py`
- Create: `docs/audits/o4_git_filesystem_isolation_2026-08-11.md`

**Interfaces:**
- Recovery fold recognizes `WORKSPACE_BASELINE_RECORDED`, `WORKSPACE_POSTFLIGHT_RECORDED`, and `INTEGRATION_MANIFEST_RECORDED` only when packet, attempt, intent, path, content hash, and artifact hash agree.
- Reconciliation attention codes: `workspace_baseline_missing`, `workspace_postflight_missing`, `workspace_evidence_mismatch`, `protected_worktree_changed`, `allowlist_violation`, `secret_like_diff`, and `integration_human_required`.

- [ ] **Step 1: Write failing crash/resume tests**

Inject crashes at: before baseline artifact, after baseline artifact before event, after worker receipt before postflight, after postflight artifact before event, and after postflight event before integration manifest. Assert worker invocation count is zero before durable baseline and exactly one after any post-worker crash. Repeated resume produces one canonical artifact/event per stage.

- [ ] **Step 2: Write failing reconciliation tamper tests**

For each O4 artifact, test missing file, altered bytes, cross-packet path, wrong intent, wrong content hash, wrong artifact hash, and contradictory `acceptance_allowed`. Require `all_invariants_passed=false` and the corresponding attention code; never silently omit the packet.

- [ ] **Step 3: Implement fold/recovery bindings**

Follow O3's existing intent-first publication pattern: artifacts may be recovered after a crash only when their canonical bytes, schema fields, packet/intent identity, and hashes agree with the pending stage. A mismatched artifact is integrity failure, never overwritten. Resume performs missing postflight/integration analysis without re-invoking a worker whose authenticated completion receipt exists.

- [ ] **Step 4: Implement reconciliation checks**

Load artifacts through the pinned state-root handle, validate canonical bytes and both hashes, cross-check packet/attempt/intent, and append stable attention items. An accepted packet requires a passing postflight; an integration decision of `HUMAN_REQUIRED` does not rewrite the packet verdict but must remain visible in the morning report.

- [ ] **Step 5: Add a disposable two-packet O4 commissioning test**

Create a disposable repository with a protected dirty worktree and two disjoint packet worktrees. Run two synthetic packets sequentially through the real coordinator (O6 owns concurrent rehearsal), prove disjoint allowed edits, protected-tree preservation, one clean integration candidate, one intentionally overlapping integration `HUMAN_REQUIRED`, and exact reconciliation totals. Include a worker that attempts one forbidden untracked file; prove it is retained for inspection and cannot be accepted.

- [ ] **Step 6: Run full verification**

```bash
PYTHONPYCACHEPREFIX=/tmp/rhemata-o4-pycache \
PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o2_*.py \
  .claude/harness-selftest/test_o3_*.py \
  .claude/harness-selftest/test_o4_*.py -q

PYTHONPYCACHEPREFIX=/tmp/rhemata-o4-pycache \
PYTHONPATH=scripts:.claude/harness-selftest python3 -m py_compile \
  scripts/harness_contracts/v1/*.py scripts/harness_coordinator/v1/*.py

python3 .claude/harness-selftest/test_current_routing_contract.py
python3 .claude/harness-selftest/test_sql_verb_narrowing.py
python3 .claude/harness-selftest/test_write_accounting_loop_fix.py
git diff --check main...HEAD
```

Expected: every command exits 0. Record exact test totals, commands, changed-file audit, non-actions, and residual limitations in `docs/audits/o4_git_filesystem_isolation_2026-08-11.md`.

- [ ] **Step 7: Commit commissioning evidence separately from build commits**

```bash
git add scripts/harness_coordinator/v1/recovery.py \
  scripts/harness_coordinator/v1/reconcile.py \
  scripts/harness_coordinator/v1/coordinator.py \
  .claude/harness-selftest/test_o4_coordinator_isolation.py \
  .claude/harness-selftest/test_o3_crash_recovery.py
git commit -m "feat: reconcile O4 workspace evidence"

git add docs/audits/o4_git_filesystem_isolation_2026-08-11.md
git commit -m "docs: record O4 isolation commissioning"
```

- [ ] **Step 8: Run final branch review and records close**

Request an independent whole-branch code review against this plan and spec. Resolve every load-bearing finding, rerun full verification, then update `PLAN.md` O4 and overwrite `rhemata-status.md` in a separate records-only commit. Do not merge or push without Alex's explicit approval.

---

## Plan self-review checklist

- Every spec requirement maps to Tasks 1–5.
- No task provisions or removes a worktree or performs Git integration.
- Protected dirty-tree preservation and out-of-scope file retention are tested.
- Secret-like evidence excludes matched values by construction and assertion.
- Recovery prevents worker invocation before baseline and prevents re-invocation after receipt.
- O6 concurrency rehearsal and O5 budgets remain explicitly out of O4.
- Build, commissioning-audit, and final records commits are separate.
