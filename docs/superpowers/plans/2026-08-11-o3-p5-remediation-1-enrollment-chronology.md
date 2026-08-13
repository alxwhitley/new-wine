# O3-P5 Remediation 1: Enrollment Chronology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `enroll_packets()` incapable of reporting enrollment success for an event that the authoritative journal validator will later reject as chronology-invalid.

**Architecture:** Reuse `validate_journal_event()` as the single chronology authority. Build and validate each prospective `PACKET_ENROLLED` event against the current journal head before the first artifact write, and revalidate after every journal-head CAS refresh before append; do not weaken `read_journal()` torn-tail behavior or add a second timestamp parser.

**Tech Stack:** Python 3.9, pytest, existing harness v1 journal contracts and filesystem fixtures.

## Global Constraints

- Start from `6be8c32` on branch `codex/o3-p5-coordinator-loop`.
- Repo-only work: no database, network, provider, deployment, push, merge, or governed-content action.
- Writable allowlist: `scripts/harness_coordinator/v1/enroll.py`, `.claude/harness-selftest/test_o3_p5_enrollment.py`, and the Task 1 report under `.superpowers/sdd/2026-08-11-o3-p5-pre-p5d-remediations/`.
- Do not touch the P5B PID, derived-queue ordering, or pinned worker-claim lifecycle remediations in this packet.
- Preserve unrelated dirty-worktree changes exactly as found.
- Use Python 3.9-compatible typing and syntax.
- This remediation gets its own build commit and fresh Opus gate before remediation 2 begins.

---

### Task 1: Reject chronology-invalid enrollment before publication

**Files:**
- Modify: `scripts/harness_coordinator/v1/enroll.py`
- Test: `.claude/harness-selftest/test_o3_p5_enrollment.py`
- Create: `.superpowers/sdd/2026-08-11-o3-p5-pre-p5d-remediations/task-1-report.md`

**Interfaces:**
- Consumes: `validate_journal_event(event, prev_event=..., state_root_id=...)`, `_make_event(...)`, `append_journal(...)`, and the current `PacketPreflightError.errors` shape.
- Produces: unchanged public signatures for `preflight_packets(...)` and `enroll_packets(...)`; chronology rejection is surfaced as `PacketPreflightError` with the authoritative `CHRONOLOGY_VIOLATION` error.

- [ ] **Step 1: Add the exact false-success regression**

Add a test which enrolls `packet-1` at `2026-08-10T00:00:02Z`, snapshots the journal, queue, and packet directory, then attempts `packet-2` at `2026-08-10T00:00:01Z`.

```python
def test_stale_enrollment_time_is_rejected_before_any_publication(tmp_path):
    from harness_coordinator.v1.enroll import PacketPreflightError, enroll_packets
    from harness_coordinator.v1.store import read_journal

    args = (str(tmp_path), "srid-1", "coord-1", "run-1")
    enroll_packets(*args, "2026-08-10T00:00:02Z", [_packet("packet-1")])
    journal_before = (tmp_path / "journal.ndjson").read_bytes()
    queue_before = (tmp_path / "queue.json").read_bytes()

    with pytest.raises(PacketPreflightError) as exc_info:
        enroll_packets(*args, "2026-08-10T00:00:01Z", [_packet("packet-2")])

    assert any(error["code"] == "CHRONOLOGY_VIOLATION" for error in exc_info.value.errors)
    assert (tmp_path / "journal.ndjson").read_bytes() == journal_before
    assert (tmp_path / "queue.json").read_bytes() == queue_before
    assert not (tmp_path / "packets" / "packet-2.json").exists()
    events, torn = read_journal(str(tmp_path / "journal.ndjson"), state_root_id="srid-1")
    assert torn is None
    assert [event.get("packet_id") for event in events] == ["packet-1"]
```

- [ ] **Step 2: Prove RED against the committed checkpoint**

Run:

```bash
PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o3_p5_enrollment.py::test_stale_enrollment_time_is_rejected_before_any_publication -q
```

Expected: FAIL because the second call returns `{"enrolled": ["packet-2"], "skipped": []}` and publishes an artifact plus a chronology-invalid journal tail.

- [ ] **Step 3: Add a single authoritative event builder/validator**

Import `validate_journal_event` from `harness_contracts.v1.journal`. Extract the existing `PACKET_ENROLLED` event construction into a private helper that validates the complete event against the supplied head and state-root ID before returning it.

```python
def _validated_enrollment_event(
    seq: int,
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    prev: Optional[Dict[str, Any]],
    now: str,
    packet_id: str,
    to_state: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    event = _make_event(
        seq,
        "PACKET_ENROLLED",
        coordinator_id,
        run_id,
        state_root_id,
        prev,
        now,
        packet_id=packet_id,
        intent_id=f"enroll-{packet_id}-{seq}",
        to_state=to_state,
        cause="enrollment",
        payload={**payload, "packet": {**payload["packet"], "enqueue_seq": seq}},
    )
    validation = validate_journal_event(
        event,
        prev_event=prev,
        state_root_id=state_root_id,
    )
    if not validation["valid"]:
        raise PacketPreflightError(validation["errors"])
    return event
```

Use `Optional` from `typing`; do not introduce `str | None` or duplicate RFC3339 parsing.

- [ ] **Step 4: Preflight the whole prospective batch before its first write**

After durable/artifact conflict decisions are complete and before `_preserve_packet()` is called, simulate only the not-already-enrolled decisions in order. Starting from the current journal head, compute each prospective sequence and payload exactly as the live loop does, call `_validated_enrollment_event()`, and advance the in-memory prospective head.

This preflight must preserve these outcomes:

- identical already-enrolled packets remain `skipped` and do not consume a sequence;
- equal timestamps remain valid because the contract rejects only `event_at < previous event_at`;
- any invalid prospective event aborts the whole batch before packet, journal, queue, or rejection-evidence publication;
- no new timestamp comparison logic exists outside `validate_journal_event()`.

- [ ] **Step 5: Revalidate after every CAS head refresh**

Replace the live loop's direct `_make_event()` call with `_validated_enrollment_event()`. On `JournalHeadMoved`, keep the existing bounded reread/refold/dedup behavior, recompute `prev` and `seq`, then build and validate again before the next append attempt.

Add a deterministic race regression: inject `JournalHeadMoved`, append or expose a valid intervening event whose `event_at` is later than the enrollment call's `now`, and assert the retry raises `PacketPreflightError` without appending the stale enrollment or returning success. The existing packet artifact may remain at this post-preflight crash boundary; the acceptance requirement is that the journal stays valid and the call never reports enrollment.

- [ ] **Step 6: Add boundary regressions**

Add focused tests proving:

```python
def test_equal_enrollment_time_is_allowed(...): ...
def test_two_packet_batch_with_one_timestamp_remains_valid(...): ...
def test_cas_refresh_revalidates_chronology_against_new_head(...): ...
```

Assert outcomes and durable state, not helper call counts. In every successful case, immediately call `read_journal(..., state_root_id="srid-1")` and assert `torn is None` plus the expected enrolled packet IDs.

- [ ] **Step 7: Run focused GREEN verification**

Run:

```bash
PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o3_p5_enrollment.py -q
```

Expected: all enrollment/P5A tests pass, including the new RED regression.

- [ ] **Step 8: Run the accepted harness regression gate**

Run:

```bash
PYTHONPATH=scripts python3 -m pytest .claude/harness-selftest/test_o2_*.py .claude/harness-selftest/test_o3_*.py -q
python3 -m py_compile scripts/harness_coordinator/v1/enroll.py .claude/harness-selftest/test_o3_p5_enrollment.py
git diff --check -- scripts/harness_coordinator/v1/enroll.py .claude/harness-selftest/test_o3_p5_enrollment.py
```

Expected: no regression from the accepted baseline, compilation succeeds, and the scoped diff is clean. Record exact counts and the genuine RED failure in `task-1-report.md`.

- [ ] **Step 9: Audit scope and obtain fresh judgment**

Run:

```bash
git status --short
git diff -- scripts/harness_coordinator/v1/enroll.py .claude/harness-selftest/test_o3_p5_enrollment.py
```

Verify no file outside the allowlist was changed by this packet. Obtain fresh Opus review against this plan, the Task 1 report, and the scoped diff. A verdict other than `ACCEPT` returns this same packet for bounded revision; it does not authorize work on remediations 2–4.

- [ ] **Step 10: Commit only remediation 1 after ACCEPT**

```bash
git add scripts/harness_coordinator/v1/enroll.py .claude/harness-selftest/test_o3_p5_enrollment.py
git commit -m "fix: reject stale harness enrollment events"
```

Do not stage the ignored Task 1 report or unrelated dirty files. Record the accepted commit SHA for the next packet's exact starting revision.

## Self-Review

- Spec coverage: false-success reproduction, pre-write rejection, CAS-time revalidation, valid equality/batch behavior, full regression gate, isolated commit, and independent judgment are all assigned explicit steps.
- Placeholder scan: every implementation and verification step is concrete and executable.
- Type consistency: the helper uses the existing event, validation-result, and `PacketPreflightError.errors` dictionary shapes; public enrollment signatures remain unchanged.
