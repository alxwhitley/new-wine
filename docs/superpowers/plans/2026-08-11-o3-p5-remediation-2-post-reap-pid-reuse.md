# O3-P5 Remediation 2: Post-Reap PID Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure invocation cleanup never signals a recycled process group after the original worker leader has been reaped.

**Architecture:** Extend the existing process-group termination primitive with an optional captured leader-start identity. Recheck that identity immediately before TERM and KILL; a different live identity proves numeric PID/PGID reuse and must suppress the signal. `invoke_worker()` obtains the authoritative identity from its durable sidecar and supplies it to every later cleanup call.

**Tech Stack:** Python 3.9, POSIX process groups, existing Darwin/Linux process identity helpers, pytest synthetic subprocess fixtures.

## Global Constraints

- Start from remediation 1 commit `c8a5c4c` on `codex/o3-p5-coordinator-loop`.
- Repo-only; no database, network, provider, deployment, push, merge, or governed-content action.
- Writable allowlist: `scripts/harness_coordinator/v1/process_sidecar.py`, `scripts/harness_coordinator/v1/invoke.py`, `.claude/harness-selftest/test_o3_p5_invocation.py`, and the ignored Task 2 report.
- Preserve descendant cleanup, timeout/interruption semantics, sidecar authentication, Python 3.9 compatibility, and all unrelated dirty files.
- Do not touch derived-queue ordering or P5A pinned worker-claim lifecycle in this packet.
- Commit this fix separately only after fresh Opus `ACCEPT`.

---

### Task 1: Bind every group signal to the original leader identity

**Files:**
- Modify: `scripts/harness_coordinator/v1/process_sidecar.py`
- Modify: `scripts/harness_coordinator/v1/invoke.py`
- Test: `.claude/harness-selftest/test_o3_p5_invocation.py`
- Create: `.superpowers/sdd/2026-08-11-o3-p5-pre-p5d-remediations/task-2-report.md`

**Interfaces:**
- Extend compatibly: `terminate_process_group(pgid: int, grace_seconds: float, expected_leader_identity: Optional[str] = None) -> bool`.
- Preserve all existing two-argument callers.
- `invoke_worker()` consumes the exact `process_start_identity` returned by `write_sidecar()`; packets and adapter output cannot supply it.

- [ ] **Step 1: Write the recycled-leader RED regression**

Add a test that patches `process_sidecar.process_start_identity()` to return a different live identity and patches `os.killpg()` to raise if called. Invoke `terminate_process_group(..., expected_leader_identity="original")` and assert it returns `True` without signaling.

Run the single test and confirm RED because the current function has no identity parameter and/or calls `killpg`.

- [ ] **Step 2: Add the second-signal reuse regression**

Simulate an original identity before TERM and a replacement identity immediately before the KILL escalation. Force the group-live probe to remain true and use zero grace. Assert TERM is the only emitted signal and the function returns `True` once replacement is observed.

This test catches a fix that checks identity only once at function entry.

- [ ] **Step 3: Implement identity-bound termination**

Add a private predicate that treats only a non-null, unequal current identity as replacement:

```python
def _leader_was_replaced(pgid: int, expected: Optional[str]) -> bool:
    if expected is None:
        return False
    current = process_start_identity(pgid)
    return current is not None and current != expected
```

Call it immediately before each `os.killpg` operation. `current is None` must not automatically suppress cleanup: the original group leader may be reaped while descendants still keep the original process group alive.

- [ ] **Step 4: Thread the durable identity through invocation cleanup**

Capture the dictionary returned by `write_sidecar()` and retain its `process_start_identity`. Pass that value to every subsequent normal and `finally` call to `terminate_process_group()`. If failure occurs before a sidecar identity is captured, retain the existing two-argument fail-safe cleanup because the launched leader has not been polled/reaped by the coordinator yet.

- [ ] **Step 5: Close the sidecar check-to-signal window**

After `terminate_sidecar_process()` authenticates the sidecar and confirms PID/PGID/session identity, pass `sidecar["process_start_identity"]` into `terminate_process_group()`. This rechecks immediately at each signal instead of relying only on the earlier check.

- [ ] **Step 6: Run focused and stress verification**

```bash
PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o3_p5_invocation.py -q
for i in $(seq 1 20); do PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o3_p5_invocation.py::test_timeout_kills_entire_process_group -q || exit 1; done
```

Record exact counts. The timeout test must remain stable and its child PID must be dead.

- [ ] **Step 7: Run the full accepted harness gate**

```bash
PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o2_*.py .claude/harness-selftest/test_o3_*.py -q
PYTHONPYCACHEPREFIX=/private/tmp/rhemata-pycache python3 -m py_compile scripts/harness_coordinator/v1/process_sidecar.py scripts/harness_coordinator/v1/invoke.py .claude/harness-selftest/test_o3_p5_invocation.py
git diff --check -- scripts/harness_coordinator/v1/process_sidecar.py scripts/harness_coordinator/v1/invoke.py .claude/harness-selftest/test_o3_p5_invocation.py
```

- [ ] **Step 8: Obtain Opus acceptance and commit only Task 2**

Fresh review must pressure-test natural exit, timeout, interruption, exception-before-sidecar, exception-after-sidecar, TERM→KILL replacement, descendant-only groups after leader reap, and backward-compatible callers. After `ACCEPT`:

```bash
git add scripts/harness_coordinator/v1/process_sidecar.py scripts/harness_coordinator/v1/invoke.py .claude/harness-selftest/test_o3_p5_invocation.py
git commit -m "fix: bind worker cleanup to process identity"
```

Do not stage either remediation plan, ignored reports, or unrelated files.

## Self-Review

- Coverage includes replacement before TERM and between TERM/KILL, plus the real timeout group-kill path.
- The design preserves cleanup of descendant-only groups by distinguishing “leader absent” from “leader replaced.”
- Public compatibility is preserved through an optional third parameter.
- No other pre-P5D remediation is included.

