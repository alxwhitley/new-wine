"""O5 Task 5 Step 3: CLI plan-authentication and read/write CLI parity tests.

``run_cli.py`` (``--once``, the sole write-capable coordinator entry point)
previously accepted no execution-plan argument at all: a caller could invoke
it with nothing but ``--state-root``/``--coordinator-id``/``--run-id``/
``--now`` and ``coordinator.run_once()`` would silently execute with, per its
own docstring, "no plan-derived limits, no wall-clock backstop, and no
pre-claim budget/routing/human-authority gate." These tests prove the now-
REQUIRED ``--execution-plan-path`` argument fails closed -- before any
coordinator claim, before any journal write -- on a missing path, a
non-canonical plan, and a structurally invalid plan, and that a genuinely
valid plan reaches ``run_once`` and lets a real (empty) iteration complete.

They also prove ``cli.py`` (the read-only reconcile/replay/status CLI) is
unaffected: no plan argument was added there, and all three of its
subcommands still run zero-write against a real, plan-governed durable state
root produced by ``run_cli.py`` itself.

Plan-loading reuses ``harness_contracts.v1.execution_plan.
authenticate_execution_plan_bytes`` -- the exact canonical-bytes/hash-
checking path Task 1 built for ``bind_execution_plan`` -- via
``run_cli._load_execution_plan``; this file does not re-validate a plan by
any second mechanism.
"""

import json
import os

import pytest

from harness_contracts.v1.canonical import canonical_bytes
from harness_coordinator.v1 import cli as read_cli
from harness_coordinator.v1 import run_cli

from test_o3_p5_review import TRUSTED_REVIEWER, _write_trust_roots
from test_o5_execution_plan import _valid_plan


COORDINATOR_ID = "coord-o5-cli"
RUN_ID = "run-o5-cli"
T_NOW = "2026-08-12T00:00:00Z"

# Deliberately not exhaustive -- a simple substring scan, per the plan's own
# Task 5 Step 3 instruction ("a simple substring/pattern check is fine, don't
# over-engineer this"). Every string here is checked case-insensitively.
_CREDENTIAL_LIKE_PATTERNS = (
    "sk-", "bearer ", "anthropic_api_key", "openai_api_key", "api_key",
    "apikey", "secret", "password", "authorization:", "private_key",
)
_PROMPT_BODY_MARKERS = (
    "you are ", "system:", "### instruction", "<|", '"role": "system"',
    "you must", "as an ai",
)


def _assert_no_leaked_material(*blobs):
    combined = "\n".join(blob for blob in blobs if blob).lower()
    for pattern in _CREDENTIAL_LIKE_PATTERNS:
        assert pattern not in combined, "credential-like value leaked: %r" % pattern
    for marker in _PROMPT_BODY_MARKERS:
        assert marker not in combined, "prompt-body-shaped content leaked: %r" % marker


def _write_plan_file(path, plan_bytes):
    with open(str(path), "wb") as handle:
        handle.write(plan_bytes)
    return str(path)


def _base_argv(state_root, plan_path, now=T_NOW, coordinator_id=COORDINATOR_ID, run_id=RUN_ID):
    return [
        "--once", "--state-root", state_root, "--coordinator-id", coordinator_id,
        "--run-id", run_id, "--now", now, "--execution-plan-path", plan_path,
    ]


def _run_write_cli(argv, capsys):
    exit_code = run_cli.main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def _run_read_cli(argv, capsys):
    exit_code = read_cli.main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def _journal_path(state_root):
    return os.path.join(state_root, "journal.ndjson")


def _locks_path(state_root):
    return os.path.join(state_root, "locks")


def _manifest_path(state_root):
    return os.path.join(state_root, "MANIFEST.json")


def _assert_nothing_durable_was_written(state_root):
    """No coordinator claim was attempted -- proof, not inference.

    A real run always creates ``locks/`` (the singleton flock, step 1 of
    ``run_started_recovery``) before it ever appends ``RUN_STARTED``, so the
    absence of both, plus a missing/blank MANIFEST.json, together demonstrate
    the failure happened strictly before any durable coordinator activity --
    not merely that the journal specifically was untouched.
    """
    assert not os.path.exists(_journal_path(state_root))
    assert not os.path.exists(_locks_path(state_root))
    assert not os.path.exists(_manifest_path(state_root))


def _snapshot_tree(root):
    """Every file's exact bytes, keyed by path relative to ``root``.

    Dict equality before/after a read-only CLI call is a stronger zero-write
    proof than an mtime check: it also catches an in-place content change
    that happens to preserve size/mtime resolution.
    """
    snapshot = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            with open(full, "rb") as handle:
                snapshot[os.path.relpath(full, root)] = handle.read()
    return snapshot


# --------------------------------------------------------------------------
# run_cli.py: required --execution-plan-path fails closed
# --------------------------------------------------------------------------


def test_missing_execution_plan_path_fails_closed(tmp_path, capsys):
    state_root = str(tmp_path / "state")
    os.makedirs(state_root)
    missing_path = str(tmp_path / "does-not-exist.json")

    exit_code, out, err = _run_write_cli(_base_argv(state_root, missing_path), capsys)

    assert exit_code == 1
    payload = json.loads(out)
    assert payload == {
        "error": True,
        "code": "PLAN_IDENTITY_INVALID",
        "message": payload["message"],
    }
    assert "execution plan file cannot be read" in payload["message"]
    _assert_nothing_durable_was_written(state_root)
    _assert_no_leaked_material(out, err)


def test_noncanonical_execution_plan_fails_closed(tmp_path, capsys):
    """Re-serialized with different key order/whitespace -- same JSON object,
    not the canonical encoding ``authenticate_execution_plan_bytes`` requires.
    Mirrors ``test_o5_execution_plan.py``'s own
    ``test_binding_rejects_noncanonical_plan_bytes`` fixture shape exactly."""
    state_root = str(tmp_path / "state")
    os.makedirs(state_root)
    plan = _valid_plan()
    noncanonical = json.dumps(plan, indent=2, sort_keys=False).encode("utf-8")
    plan_path = _write_plan_file(tmp_path / "plan.json", noncanonical)

    exit_code, out, err = _run_write_cli(_base_argv(state_root, plan_path), capsys)

    assert exit_code == 1
    payload = json.loads(out)
    assert payload["error"] is True
    assert payload["code"] == "PLAN_IDENTITY_NONCANONICAL"
    _assert_nothing_durable_was_written(state_root)
    _assert_no_leaked_material(out, err)


def test_tampered_plan_hash_fails_closed(tmp_path, capsys):
    """A byte flipped inside the self-referential hash -- still a
    syntactically valid 64-char lowercase-hex sha256 string, so this
    exercises EVIDENCE_HASH_MISMATCH rather than the format check."""
    state_root = str(tmp_path / "state")
    os.makedirs(state_root)
    plan = _valid_plan()
    original = plan["plan_sha256"]
    flipped_char = "f" if original[0] != "f" else "e"
    plan["plan_sha256"] = flipped_char + original[1:]
    assert plan["plan_sha256"] != original
    plan_path = _write_plan_file(tmp_path / "plan.json", canonical_bytes(plan))

    exit_code, out, err = _run_write_cli(_base_argv(state_root, plan_path), capsys)

    assert exit_code == 1
    payload = json.loads(out)
    assert payload["error"] is True
    assert payload["code"] == "PLAN_IDENTITY_INVALID"
    assert "self-hash" in payload["message"]
    _assert_nothing_durable_was_written(state_root)
    _assert_no_leaked_material(out, err)


def test_structurally_invalid_plan_fails_closed(tmp_path, capsys):
    """Fails ``validate_execution_plan`` itself (a required top-level
    property missing), independent of canonical-bytes/hash checks."""
    state_root = str(tmp_path / "state")
    os.makedirs(state_root)
    plan = _valid_plan()
    del plan["human_stop_categories"]
    plan_path = _write_plan_file(tmp_path / "plan.json", json.dumps(plan).encode("utf-8"))

    exit_code, out, err = _run_write_cli(_base_argv(state_root, plan_path), capsys)

    assert exit_code == 1
    payload = json.loads(out)
    assert payload["error"] is True
    assert payload["code"] == "PLAN_IDENTITY_INVALID"
    assert "human_stop_categories" in payload["message"]
    _assert_nothing_durable_was_written(state_root)
    _assert_no_leaked_material(out, err)


def test_execution_plan_path_argument_is_required():
    """No default exists that would silently permit an ungoverned run --
    omitting the flag is an argparse-level hard failure, the same posture
    every other required flag on this CLI already has."""
    with pytest.raises(SystemExit):
        run_cli.main([
            "--once", "--state-root", "/nonexistent/does-not-matter",
            "--coordinator-id", COORDINATOR_ID, "--run-id", RUN_ID, "--now", T_NOW,
        ])


# --------------------------------------------------------------------------
# A genuinely valid plan reaches run_once, and legacy read-only cli.py still
# works unchanged against the resulting real, plan-governed durable state.
# --------------------------------------------------------------------------


def test_valid_execution_plan_reaches_run_once_and_legacy_readonly_cli_still_works(tmp_path, capsys):
    state_root = str(tmp_path / "state")
    os.makedirs(state_root)
    _write_trust_roots(state_root, sessions=(TRUSTED_REVIEWER,))

    plan = _valid_plan()
    plan_path = _write_plan_file(tmp_path / "plan.json", canonical_bytes(plan))

    exit_code, out, err = _run_write_cli(_base_argv(state_root, plan_path), capsys)

    payload = json.loads(out)
    # A real run_once() result, not this CLI's own load-time error shape
    # (proven distinct by the tests above: {"error": True, "code": ...,
    # "message": ...} and nothing else). Reaching run_once means a genuine
    # reconciliation-bearing coordinator result is present instead.
    assert "error" not in payload
    assert "reconciliation" in payload
    assert exit_code == 0

    with open(_manifest_path(state_root), "rb") as handle:
        manifest = json.loads(handle.read().decode("utf-8"))
    state_root_id = manifest["state_root_id"]
    assert os.path.exists(_journal_path(state_root))

    tree_before = _snapshot_tree(state_root)

    reconcile_exit, reconcile_out, reconcile_err = _run_read_cli([
        "reconcile", "--state-root", state_root, "--state-root-id", state_root_id,
        "--coordinator-id", COORDINATOR_ID, "--run-id", RUN_ID,
    ], capsys)
    reconcile_report = json.loads(reconcile_out)
    assert "error" not in reconcile_report
    assert reconcile_report["reconciliation"]["all_invariants_passed"] is True
    assert reconcile_exit == 0

    replay_exit, replay_out, replay_err = _run_read_cli([
        "replay", "--state-root", state_root, "--state-root-id", state_root_id,
    ], capsys)
    replay_report = json.loads(replay_out)
    assert replay_report["replay_passed"] is True
    assert replay_exit == 0

    status_exit, status_out, status_err = _run_read_cli([
        "status", "--state-root", state_root, "--state-root-id", state_root_id,
    ], capsys)
    status_report = json.loads(status_out)
    assert status_report["error"] is False
    assert status_exit == 0

    # All three read-only subcommands together wrote nothing -- byte-for-byte
    # identical durable state before and after.
    assert _snapshot_tree(state_root) == tree_before

    _assert_no_leaked_material(
        out, err, reconcile_out, reconcile_err, replay_out, replay_err,
        status_out, status_err,
    )
