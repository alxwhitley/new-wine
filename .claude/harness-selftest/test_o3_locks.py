"""Lock claim TDD for O3-P2 durable store."""

import os
import tempfile

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_coordinator.v1.locks import classify_claim, create_claim, read_claim, reclaim_lock


def _make_claim_record(
    packet_id: str = "pkt-1",
    coordinator_id: str = "coord-1",
    hostname: str = "host-1",
    boot_id: str = "boot-1",
    pid: int = 1234,
    lease_seconds: int = 60,
) -> dict:
    record = {
        "schema_version": 1,
        "packet_id": packet_id,
        "intent_id": f"intent-{packet_id}",
        "stage": "claim",
        "attempt": 1,
        "coordinator_id": coordinator_id,
        "run_id": "run-1",
        "hostname": hostname,
        "boot_id": boot_id,
        "pid": pid,
        "acquired_at": "2026-08-10T00:00:00Z",
        "heartbeat_at": "2026-08-10T00:00:00Z",
        "lease_seconds": lease_seconds,
        "lane": "kimi_implementation",
        "worktree_path": None,
        "claim_sha256": "",
    }
    record["claim_sha256"] = compute_sha256(canonical_bytes(record, omit={"claim_sha256"}))
    return record


def test_create_claim_writes_o_excl_file():
    state_root = tempfile.mkdtemp()
    lock_path = os.path.join(state_root, "locks", "pkt-1.lock.json")
    record = _make_claim_record()

    create_claim(lock_path, record)

    assert os.path.exists(lock_path)
    read_back = read_claim(lock_path)
    assert read_back["packet_id"] == "pkt-1"
    assert read_back["claim_sha256"] == record["claim_sha256"]


def test_create_claim_refuses_second_claim():
    state_root = tempfile.mkdtemp()
    lock_path = os.path.join(state_root, "locks", "pkt-1.lock.json")
    record = _make_claim_record()

    create_claim(lock_path, record)
    with pytest.raises(FileExistsError):
        create_claim(lock_path, record)


def test_reclaim_lock_moves_stale_prior_boot_verbatim():
    state_root = tempfile.mkdtemp()
    lock_path = os.path.join(state_root, "locks", "pkt-1.lock.json")
    record = _make_claim_record(boot_id="old-boot")
    create_claim(lock_path, record)

    reclaim_lock(lock_path, run_id="run-2", classification="STALE_PRIOR_BOOT")

    assert not os.path.exists(lock_path)
    reclaimed = os.path.join(state_root, "locks", "reclaimed", "run-2", "pkt-1.lock.json")
    assert os.path.exists(reclaimed)
    assert read_claim(reclaimed) == record


def test_reclaim_lock_refuses_foreign_live_and_foreign_host():
    state_root = tempfile.mkdtemp()
    lock_path = os.path.join(state_root, "locks", "pkt-1.lock.json")
    record = _make_claim_record()
    create_claim(lock_path, record)

    with pytest.raises(ValueError):
        reclaim_lock(lock_path, run_id="run-2", classification="FOREIGN_LIVE")
    with pytest.raises(ValueError):
        reclaim_lock(lock_path, run_id="run-2", classification="FOREIGN_HOST")
    assert os.path.exists(lock_path)


def test_classify_claim_stale_prior_boot_reclaimable():
    record = _make_claim_record(boot_id="old-boot")
    ctx = {
        "coordinator_id": "coord-1",
        "hostname": "host-1",
        "boot_id": "new-boot",
        "pid": 1234,
        "live_coordinator_ids": set(),
        "now": "2026-08-10T00:00:00Z",
    }
    result = classify_claim(record, ctx)
    assert result["status"] == "STALE_PRIOR_BOOT"


def test_classify_claim_foreign_host_refused():
    record = _make_claim_record(hostname="other-host")
    ctx = {
        "coordinator_id": "coord-1",
        "hostname": "host-1",
        "boot_id": "boot-1",
        "pid": 1234,
        "live_coordinator_ids": set(),
        "now": "2026-08-10T00:00:00Z",
    }
    result = classify_claim(record, ctx)
    assert result["status"] == "FOREIGN_HOST"
    assert any(e["code"] == "CLAIM_CONFLICT" for e in result["errors"])


def test_classify_claim_foreign_live_refused():
    record = _make_claim_record(coordinator_id="coord-2")
    ctx = {
        "coordinator_id": "coord-1",
        "hostname": "host-1",
        "boot_id": "boot-1",
        "pid": 1234,
        "live_coordinator_ids": {"coord-2"},
        "now": "2026-08-10T00:00:00Z",
    }
    result = classify_claim(record, ctx)
    assert result["status"] == "FOREIGN_LIVE"
    assert any(e["code"] == "CLAIM_CONFLICT" for e in result["errors"])


def test_classify_claim_missing_trust_context_fails_closed():
    record = _make_claim_record()
    ctx = {
        "coordinator_id": "coord-1",
        "hostname": "host-1",
        "boot_id": "boot-1",
        "pid": 1234,
        "live_coordinator_ids": set(),
        # "now" intentionally omitted
    }
    result = classify_claim(record, ctx)
    assert result["status"] == "TRUST_CONTEXT_MISSING"


def test_classify_claim_lease_expiry_not_liveness_proof():
    """A long-expired lease is still FOREIGN_LIVE if the owner is live."""
    record = _make_claim_record(coordinator_id="coord-2", lease_seconds=1)
    ctx = {
        "coordinator_id": "coord-1",
        "hostname": "host-1",
        "boot_id": "boot-1",
        "pid": 1234,
        "live_coordinator_ids": {"coord-2"},
        "now": "3026-08-10T00:00:00Z",
    }
    result = classify_claim(record, ctx)
    assert result["status"] == "FOREIGN_LIVE"


def test_classify_claim_self_owned():
    record = _make_claim_record()
    ctx = {
        "coordinator_id": "coord-1",
        "hostname": "host-1",
        "boot_id": "boot-1",
        "pid": 1234,
        "live_coordinator_ids": set(),
        "now": "2026-08-10T00:00:00Z",
    }
    result = classify_claim(record, ctx)
    assert result["status"] == "SELF_OWNED"
