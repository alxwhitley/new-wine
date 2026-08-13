# O3-P5 Remediation 4: Pinned Worker-Claim Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind every coordinator/recovery worker-claim read, creation, contention decision, and archive move to the same pinned state-root identity used by P5C.

**Architecture:** Add handle-aware claim primitives in `locks.py`, thread one `StateRootHandle` through `run_once → run_started_recovery → claim_and_start_attempt`, and guard accepted pathname journal/queue calls with immediate root-identity checks. Legacy pathname APIs remain compatible; runtime worker-claim paths exclusively use the pinned variants.

**Tech Stack:** Python 3.9, retained directory FDs, `openat`/`renameat`, existing `StateRootHandle`, pytest filesystem adversarial fixtures.

## Global Constraints

- Start from remediation 3 commit `badc41c` on `codex/o3-p5-coordinator-loop`.
- Writable allowlist: `scripts/harness_coordinator/v1/locks.py`, `scripts/harness_coordinator/v1/coordinator.py`, `scripts/harness_coordinator/v1/recovery.py`, new `.claude/harness-selftest/test_o3_p5_claim_root_identity.py`, and the ignored Task 4 report.
- Do not modify `seals_runtime.py`, generic journal/queue/store contracts, DB/network/provider/deploy surfaces, governed content, or unrelated dirty files.
- Preserve legacy pathname claim APIs, O_EXCL contention, claim bytes/self-hash, recovery event order, Python 3.9, and separate-commit discipline.
- Real provider commissioning remains `HUMAN_REQUIRED`.

---

### Task 1: Add pinned worker-claim primitives

**Files:**
- Modify: `scripts/harness_coordinator/v1/locks.py`
- Create/Test: `.claude/harness-selftest/test_o3_p5_claim_root_identity.py`

**Interfaces:**

```python
def create_claim_at(handle, packet_id: str, record: Dict[str, Any]) -> None
def read_claim_at(handle, packet_id: str) -> Dict[str, Any]
def list_worker_claim_ids(handle) -> List[str]
def reclaim_lock_at(handle, packet_id: str, run_id: str,
                    classification: str, expected_claim_sha256: str) -> None
```

- [ ] Write RED tests for O_EXCL contention, canonical unchanged bytes, parent/root swap non-redirection, symlink/non-regular refusal, exclusive archive destination, and digest mismatch before archive.
- [ ] Implement all file operations relative to `handle.directory(("locks",), ...)`; validate IDs before constructing basenames; use `O_NOFOLLOW`; require regular files; fully write/fsync claims; enumerate via the retained directory FD; move with source/destination directory FDs.
- [ ] `reclaim_lock_at` must reread and validate the current claim, require the expected digest, refuse an existing destination, and move verbatim only after all checks.
- [ ] Keep `create_claim`, `read_claim`, and `reclaim_lock` unchanged for compatibility.

### Task 2: Share one handle through selection and claim commit

**Files:**
- Modify: `scripts/harness_coordinator/v1/coordinator.py`
- Test: `.claude/harness-selftest/test_o3_p5_claim_root_identity.py`

- [ ] Add optional `handle=None` compatibility to `claim_packet()` and `claim_and_start_attempt()`. A direct caller opens one scoped handle and recurses; `_run_iteration()` passes its existing handle.
- [ ] Use `_load_enrolled_packet(..., handle=handle)`, `create_claim_at`, and `read_claim_at` exclusively in runtime claim paths.
- [ ] Guard pathname `atomic_replace`, `append_journal`, and `read_journal` phases immediately before and after with `handle.verify_identity()`.
- [ ] RED tests must cover root swap before creation, after claim/before pending projection, and during `JournalHeadMoved` CAS reread. Replacement roots/outside targets receive no claim, queue, or journal mutation.

### Task 3: Bind crash recovery enumeration and reclaim

**Files:**
- Modify: `scripts/harness_coordinator/v1/recovery.py`
- Test: `.claude/harness-selftest/test_o3_p5_claim_root_identity.py`

- [ ] Add optional `handle=None` to `run_started_recovery()`. Direct calls create the root if needed, open exactly one handle, recurse, and close it on success/failure. `run_once()` passes its existing handle.
- [ ] Thread `handle` into `_reconcile_locks()` and `_resolve_pending_intents()`; use `list_worker_claim_ids`, `read_claim_at`, and `reclaim_lock_at` only.
- [ ] Pass the classified record's exact `claim_sha256` into `reclaim_lock_at` after journaling `LOCK_RECLAIMED`; a changed claim fails before the move.
- [ ] Preserve event order: `LOCK_RECLAIMED`, then `INTENT_ABANDONED` where applicable, then archive move.
- [ ] Guard accepted pathname manifest/trust/journal/queue/sweep phases with immediate `verify_identity()` without reimplementing them.
- [ ] RED tests must cover replacement-root enumeration, claim/locks symlinks, swap after reclaim journal append, digest mutation before archive, pending-intent reclaim, and direct-call handle closure.

### Task 4: Verify the complete boundary

**Files:**
- Create: `.superpowers/sdd/2026-08-11-o3-p5-pre-p5d-remediations/task-4-report.md`

- [ ] Focused:

```bash
PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o3_p5_claim_root_identity.py -q
PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o3_locks.py .claude/harness-selftest/test_o3_p5_enrollment.py .claude/harness-selftest/test_o3_crash_recovery.py .claude/harness-selftest/test_o3_p5_review.py -q
```

- [ ] Full/static:

```bash
PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o2_*.py .claude/harness-selftest/test_o3_*.py -q
PYTHONPYCACHEPREFIX=/private/tmp/rhemata-pycache python3 -m py_compile scripts/harness_coordinator/v1/locks.py scripts/harness_coordinator/v1/coordinator.py scripts/harness_coordinator/v1/recovery.py .claude/harness-selftest/test_o3_p5_claim_root_identity.py
git diff --check -- scripts/harness_coordinator/v1/locks.py scripts/harness_coordinator/v1/coordinator.py scripts/harness_coordinator/v1/recovery.py .claude/harness-selftest/test_o3_p5_claim_root_identity.py
```

- [ ] Obtain fresh Opus review against every listed root/parent/CAS/recovery/archive adversary. After `ACCEPT`, commit only four build files:

```bash
git add scripts/harness_coordinator/v1/locks.py scripts/harness_coordinator/v1/coordinator.py scripts/harness_coordinator/v1/recovery.py .claude/harness-selftest/test_o3_p5_claim_root_identity.py
git commit -m "fix: pin worker claims to state root identity"
```

## Acceptance Criteria

- `run_once()` opens one handle and shares it through recovery, P5C, selection, claim creation, CAS rereads, and recovery reclaim.
- No runtime worker-claim operation follows a replacement root, parent symlink, claim symlink, or replacement claim.
- Archived bytes match the digest recorded in reclaim evidence.
- Direct callers and legacy pathname APIs remain compatible.
- No unrelated generic pathname remediation enters this commit.

