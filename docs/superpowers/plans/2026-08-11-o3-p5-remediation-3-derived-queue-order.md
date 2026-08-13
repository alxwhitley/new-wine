# O3-P5 Remediation 3: Derived Queue Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every queue projection built from folded journal state satisfy its own strict ascending-`enqueue_seq` contract.

**Architecture:** Change `_build_derived_queue()`'s deterministic iteration key from packet ID to `(enqueue_seq, packet_id)`. Keep the validator strict and unchanged; the packet-ID tie-breaker is deterministic defense-in-depth even though valid journal enrollment sequences are unique.

**Tech Stack:** Python 3.9, existing queue-state contract, pytest.

## Global Constraints

- Start from remediation 2 commit `65d908d` on `codex/o3-p5-coordinator-loop`.
- Writable allowlist: `scripts/harness_coordinator/v1/recovery.py`, `.claude/harness-selftest/test_o3_crash_recovery.py`, and the ignored Task 3 report.
- Repo-only; no DB, network, provider, deploy, merge, push, or governed-content action.
- Do not weaken `validate_queue()`, renumber enrollment sequences, or include the P5A pinned-claim remediation.
- Preserve unrelated dirty files; use Python 3.9 syntax; commit separately only after Opus `ACCEPT`.

---

### Task 1: Align projection ordering with the accepted queue contract

**Files:**
- Modify: `scripts/harness_coordinator/v1/recovery.py`
- Test: `.claude/harness-selftest/test_o3_crash_recovery.py`
- Create: `.superpowers/sdd/2026-08-11-o3-p5-pre-p5d-remediations/task-3-report.md`

**Interfaces:**
- Consumes unchanged `derived_states: Dict[str, Dict[str, Any]]` and `validate_queue(...)`.
- Produces unchanged queue schema and `_build_derived_queue(...)` signature.

- [ ] **Step 1: Write a genuine writer-validator RED regression**

Construct two complete folded packet states where alphabetic packet order conflicts with enrollment order: `z-first` has `enqueue_seq=1`; `a-later` has `enqueue_seq=2`. Call `_build_derived_queue()`, assert entry IDs are `['z-first', 'a-later']`, and assert `validate_queue(..., state_root_id='srid-1')['valid']`.

Run that single test and confirm RED: current output is packet-ID order and validator returns `INVALID_VALUE` for descending enqueue sequence.

- [ ] **Step 2: Implement the minimal deterministic order fix**

Replace:

```python
for packet_id in sorted(derived_states.keys()):
```

with:

```python
ordered_packet_ids = sorted(
    derived_states,
    key=lambda packet_id: (derived_states[packet_id]["enqueue_seq"], packet_id),
)
for packet_id in ordered_packet_ids:
```

Do not change validator rules or any queue field.

- [ ] **Step 3: Add an end-to-end rebuild regression**

Use real `PACKET_ENROLLED` events whose packet IDs sort opposite their journal sequences, fold them, build the queue, and validate the full projection. This catches a unit fixture drifting away from the actual fold shape.

- [ ] **Step 4: Verify focused and full gates**

```bash
PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o3_crash_recovery.py -q
PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o2_*.py .claude/harness-selftest/test_o3_*.py -q
PYTHONPYCACHEPREFIX=/private/tmp/rhemata-pycache python3 -m py_compile scripts/harness_coordinator/v1/recovery.py .claude/harness-selftest/test_o3_crash_recovery.py
git diff --check -- scripts/harness_coordinator/v1/recovery.py .claude/harness-selftest/test_o3_crash_recovery.py
```

- [ ] **Step 5: Obtain fresh Opus acceptance and commit only remediation 3**

The gate must check writer/validator parity, enrollment/fold realism, deterministic output, pending-intent preservation at callers, and no scheduling semantic change. After `ACCEPT`:

```bash
git add scripts/harness_coordinator/v1/recovery.py .claude/harness-selftest/test_o3_crash_recovery.py
git commit -m "fix: order derived queue by enrollment sequence"
```

## Self-Review

- The defect is corrected at the writer rather than weakening its authoritative validator.
- Ordering remains deterministic.
- Schema, public interfaces, scheduler choice, and unrelated remediations are unchanged.

