#!/usr/bin/env python3
"""Phase 6 hidden single-slice ingestion proof tests.

All tests use pinned fixtures and strict in-memory fakes. They make no network,
embedding, model, or database connection.
"""

from __future__ import annotations

import copy
import contextlib
import io
import json
import socket
import sys
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from biblical_context_ingest_contract import (  # noqa: E402
    ProofContractError,
    build_aaron_projection,
    canonical_proof_text,
    projection_report,
    validate_aaron_record,
)
from biblical_context_tooling import canonical_json_bytes  # noqa: E402
from preview_biblical_context_ingest import (  # noqa: E402
    PreviewPathError,
    build_preview,
    main as preview_main,
)
from ingest_biblical_context_batch import (  # noqa: E402
    ApprovalError,
    ProofApplyError,
    StateConflictError,
    apply_single_proof,
    inspect_state,
    main as apply_main,
    validate_approval,
)
from reconcile_biblical_context_batch import (  # noqa: E402
    ReconciliationError,
    main as reconcile_main,
    reconcile_attempt,
    reconcile_single_proof,
)


EXPECTED_TEXT = """Dataset: STEPBible TIPNR
Revision: 02843f07cbb5009e00999a7c0efead6430dbb6e7
Entity ID: H0175
Entity type: person
Form 1 dStrong: H0175
Form 1 eStrong: H0175
Form 1 source script: אַהֲרֹן
Form 1 OSIS references: Exo.4.14; Exo.4.27
Form 2 dStrong: G0002
Form 2 eStrong: G0002
Form 2 source script: Ἀαρών
Form 2 OSIS references: Luk.1.5; Act.7.40
"""


def valid_approval() -> dict[str, object]:
    return {
        "schema_version": "biblical_context_phase6_approval.v1",
        "approved_by": "Alex Whitley",
        "operation_date": "2026-09-01",
        "source_slug": "stepbible-tipnr",
        "entity_id": "H0175",
        "record_sha256": (
            "78d6effc18c08911639e0e7240070564"
            "eed755037124268a4824cf3c719cc4d6"
        ),
        "maximum_spend_usd": "0.01",
        "source_registration_authorized": True,
        "embedding_request_authorized": True,
        "single_database_transaction_authorized": True,
    }


def exact_state(proof) -> dict[str, object]:
    return {
        "source": copy.deepcopy(proof.source),
        "alias": copy.deepcopy(proof.alias),
        "document": {**copy.deepcopy(proof.document), "ingest_completed_at": "set"},
        "chunk": {
            **copy.deepcopy(proof.chunks[0]),
            "embedding_dimensions": 1536,
        },
        "policies": [{"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", **copy.deepcopy(proof.policy)}],
    }


class MemoryCursor:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=()):
        self.connection.events.append(sql.strip().splitlines()[0])
        state = self.connection.state
        if "phase6:transaction_read_only" in sql:
            self.result = (state.get("transaction_read_only", "on"),)
        elif "phase6:current_user" in sql:
            self.result = (state.get("current_user", "newwine_readonly_analysis"),)
        elif "phase6:retrieval_vector" in sql:
            self.result = (state.get("retrieval_vector_count", 0),)
        elif "phase6:retrieval_fts" in sql:
            self.result = (state.get("retrieval_fts_count", 0),)
        elif "phase6:source" in sql:
            self.result = state.get("source")
        elif "phase6:alias" in sql:
            self.result = state.get("alias")
        elif "phase6:document" in sql:
            self.result = state.get("documents", state.get("document"))
        elif "phase6:chunk" in sql:
            self.result = state.get("chunks", state.get("chunk"))
        elif "phase6:policies" in sql:
            self.result = list(state.get("policies", []))
        elif "phase6:propositions" in sql:
            self.result = (state.get("proposition_count", 0),)
        elif "phase6:insert_source" in sql:
            self.connection.maybe_fail("source_insert")
            state["source"] = dict(self.connection.proof.source)
        elif "phase6:insert_alias" in sql:
            self.connection.maybe_fail("alias_insert")
            state["alias"] = dict(self.connection.proof.alias)
        elif "phase6:insert_document" in sql:
            self.connection.maybe_fail("document_insert")
            state["document"] = {
                **dict(self.connection.proof.document),
                "ingest_completed_at": None,
            }
        elif "phase6:insert_chunk" in sql:
            self.connection.maybe_fail("chunk_insert")
            state["chunk"] = {
                **dict(self.connection.proof.chunks[0]),
                "embedding_dimensions": 1536,
            }
        elif "phase6:insert_policy" in sql:
            self.connection.maybe_fail("policy_insert")
            state["policies"] = [
                {
                    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    **dict(self.connection.proof.policy),
                }
            ]
            self.result = ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",)
        elif "phase6:stamp_complete" in sql:
            self.connection.maybe_fail("stamp_complete")
            state["document"]["ingest_completed_at"] = "set"
        elif sql.strip().startswith("SET LOCAL"):
            self.connection.maybe_fail("set_timeout")
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        if isinstance(self.result, list):
            return self.result[0] if self.result else None
        return self.result

    def fetchall(self):
        if isinstance(self.result, list):
            return self.result
        return [] if self.result is None else [self.result]


class MemoryConnection:
    def __init__(self, state, proof, *, fail_on=None) -> None:
        self.state = state
        self.proof = proof
        self.fail_on = fail_on
        self.snapshot = copy.deepcopy(state)
        self.events = []
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0
        self.autocommit = None
        self.session_calls = []

    def cursor(self):
        return MemoryCursor(self)

    def set_session(self, **kwargs):
        self.session_calls.append(kwargs)

    def maybe_fail(self, operation):
        if operation == self.fail_on:
            raise RuntimeError(f"forced_{operation}")

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1
        self.state.clear()
        self.state.update(copy.deepcopy(self.snapshot))

    def close(self):
        self.close_count += 1


class ConnectionFactory:
    def __init__(self, proof, state=None, *, fail_on=None) -> None:
        self.proof = proof
        self.state = state if state is not None else {}
        self.fail_on = fail_on
        self.calls = []
        self.connections = []

    def __call__(self, mode):
        self.calls.append(mode)
        connection = MemoryConnection(
            self.state,
            self.proof,
            fail_on=self.fail_on if mode == "write" else None,
        )
        self.connections.append(connection)
        return connection


class EmbedRecorder:
    def __init__(self, *, fail=False, dimensions=1536) -> None:
        self.fail = fail
        self.dimensions = dimensions
        self.calls = []

    def __call__(self, text, *, model, dimensions):
        self.calls.append((text, model, dimensions))
        if self.fail:
            raise RuntimeError("external failure")
        return [0.001] * self.dimensions


class AaronProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proof = build_aaron_projection(ROOT)

    def test_builds_exact_single_row_projection(self) -> None:
        self.assertEqual(self.proof.entity_id, "H0175")
        self.assertEqual(self.proof.source["name"], "STEPBible TIPNR")
        self.assertEqual(self.proof.source["slug"], "stepbible-tipnr")
        self.assertEqual(self.proof.source["license_status"], "licensed")
        self.assertEqual(self.proof.source["visibility"], "hidden")
        self.assertEqual(self.proof.alias["alias_key"], "stepbible tipnr")
        self.assertEqual(self.proof.document["title"], "STEPBible TIPNR person H0175")
        self.assertEqual(self.proof.document["source_kind"], "biblical_context")
        self.assertEqual(self.proof.document["citation_mode"], "citable")
        self.assertEqual(self.proof.document["bible_references"], [
            "Exo.4.14", "Exo.4.27", "Luk.1.5", "Act.7.40",
        ])
        self.assertEqual(len(self.proof.chunks), 1)
        self.assertEqual(self.proof.chunks[0]["chunk_index"], 0)
        self.assertEqual(self.proof.chunks[0]["content"], EXPECTED_TEXT)
        self.assertEqual(
            self.proof.chunks[0]["bible_references"],
            ["Exo.4.14", "Exo.4.27", "Luk.1.5", "Act.7.40"],
        )
        self.assertEqual(self.proof.policy["policy_class"], "general_context")
        self.assertEqual(self.proof.policy["protected_topic_keys"], [])
        self.assertIsNone(self.proof.policy["issue_key"])
        self.assertIsNone(self.proof.policy["viewpoint_key"])
        self.assertEqual(self.proof.policy["classifier_kind"], "deterministic")
        self.assertEqual(
            self.proof.policy["reason_codes"],
            ["phase0_allowlisted_structural_fields"],
        )

    def test_canonical_text_uses_only_phase_2_fields(self) -> None:
        self.assertEqual(canonical_proof_text(self.proof.record), EXPECTED_TEXT)
        for excluded in (
            "Aaron",
            "High Priest",
            "Moses' brother",
            "relationship",
            "description",
            "comparison",
        ):
            self.assertNotIn(excluded, EXPECTED_TEXT)

    def test_projection_is_byte_stable_with_distinct_valid_ids(self) -> None:
        first = projection_report(self.proof)
        second = projection_report(build_aaron_projection(ROOT))
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
        ids = {
            self.proof.source["id"],
            self.proof.alias["id"],
            self.proof.document["id"],
            self.proof.chunks[0]["id"],
        }
        self.assertEqual(len(ids), 4)
        for value in ids:
            self.assertEqual(str(uuid.UUID(value)), value)

    def test_refuses_mutated_or_non_aaron_record(self) -> None:
        wrong_id = copy.deepcopy(self.proof.record)
        wrong_id["entity_id"] = "H0071"
        with self.assertRaisesRegex(ProofContractError, "proof_record_mismatch"):
            validate_aaron_record(wrong_id)

        extra_field = copy.deepcopy(self.proof.record)
        extra_field["description"] = "forbidden"
        with self.assertRaisesRegex(ProofContractError, "proof_record_fields_changed"):
            validate_aaron_record(extra_field)

    def test_report_contains_no_unserializable_or_authorization_state(self) -> None:
        report = projection_report(self.proof)
        encoded = canonical_json_bytes(report)
        self.assertEqual(json.loads(encoded), report)
        self.assertNotIn("database_write_authorized", report)
        self.assertNotIn("external_model_call_authorized", report)


class PreviewTests(unittest.TestCase):
    def test_preview_reports_exact_zero_effect_contract(self) -> None:
        report = build_preview(ROOT)
        self.assertFalse(report["database_write_authorized"])
        self.assertFalse(report["external_model_call_authorized"])
        self.assertEqual(
            report["counts"],
            {
                "sources": 1,
                "aliases": 1,
                "documents": 1,
                "chunks": 1,
                "policy_rows": 1,
            },
        )
        self.assertEqual(report["embedding"]["request_count"], 1)
        self.assertEqual(report["embedding"]["maximum_spend_usd"], "0.01")
        self.assertGreater(report["embedding"]["input_utf8_bytes"], 0)
        self.assertEqual(
            report["reconciliation"],
            {
                "attempted": 1,
                "stored": 0,
                "errored": 0,
                "skipped": 1,
                "reason": "preview_only",
            },
        )
        payload_hash = report["payload_sha256"]
        without_hash = dict(report)
        del without_hash["payload_sha256"]
        self.assertEqual(len(payload_hash), 64)
        self.assertNotEqual(payload_hash, "0" * 64)

    def test_preview_executes_with_network_and_external_modules_blocked(self) -> None:
        forbidden = {"psycopg2", "openai", "dotenv"}
        real_import = __import__

        def guarded_import(name, *args, **kwargs):
            if name.split(".", 1)[0] in forbidden:
                raise AssertionError(f"forbidden import: {name}")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import), patch.object(
            socket, "socket", side_effect=AssertionError("network attempted")
        ):
            report = build_preview(ROOT)
        self.assertEqual(report["schema_version"], "biblical_context_phase6_ingest_preview.v1")

    def test_cli_requires_fixtures_and_prints_canonical_json(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(preview_main(["--fixtures"]), 0)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed, build_preview(ROOT))

        with self.assertRaises(SystemExit):
            preview_main([])

    def test_preview_refuses_output_outside_local(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "proof.json"
            with self.assertRaisesRegex(PreviewPathError, "outside_local"):
                preview_main(["--fixtures", "--output", str(outside)])


class ApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proof = build_aaron_projection(ROOT)
        self.directory = self.enterContext(tempfile.TemporaryDirectory())

    def write_approval(self, value: dict[str, object]) -> Path:
        path = Path(self.directory) / "approval.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_accepts_only_exact_attended_approval(self) -> None:
        path = self.write_approval(valid_approval())
        self.assertEqual(
            validate_approval(path, self.proof, date(2026, 9, 1)),
            valid_approval(),
        )

    def test_rejects_missing_false_additional_stale_and_wrong_identity(self) -> None:
        mutations = []
        missing = valid_approval()
        del missing["embedding_request_authorized"]
        mutations.append(missing)
        false_authorization = valid_approval()
        false_authorization["single_database_transaction_authorized"] = False
        mutations.append(false_authorization)
        additional = valid_approval()
        additional["batch_size"] = 2
        mutations.append(additional)
        stale = valid_approval()
        stale["operation_date"] = "2026-08-31"
        mutations.append(stale)
        wrong_identity = valid_approval()
        wrong_identity["entity_id"] = "H0071"
        mutations.append(wrong_identity)
        wrong_cost = valid_approval()
        wrong_cost["maximum_spend_usd"] = "1.00"
        mutations.append(wrong_cost)

        for index, value in enumerate(mutations):
            with self.subTest(index=index):
                path = self.write_approval(value)
                with self.assertRaises(ApprovalError):
                    validate_approval(path, self.proof, date(2026, 9, 1))

    def test_rejects_symlink_and_oversized_file(self) -> None:
        target = self.write_approval(valid_approval())
        link = Path(self.directory) / "approval-link.json"
        link.symlink_to(target)
        with self.assertRaisesRegex(ApprovalError, "approval_not_regular"):
            validate_approval(link, self.proof, date(2026, 9, 1))

        target.write_text("{" + (" " * 8192) + "}", encoding="utf-8")
        with self.assertRaisesRegex(ApprovalError, "approval_too_large"):
            validate_approval(target, self.proof, date(2026, 9, 1))


class WriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proof = build_aaron_projection(ROOT)
        self.approval = valid_approval()

    def test_state_inspection_distinguishes_clean_complete_and_partial(self) -> None:
        clean_connection = MemoryConnection({}, self.proof)
        self.assertEqual(
            inspect_state(clean_connection.cursor(), self.proof).kind,
            "clean",
        )

        complete_connection = MemoryConnection(exact_state(self.proof), self.proof)
        verdict = inspect_state(complete_connection.cursor(), self.proof)
        self.assertEqual(verdict.kind, "exact_complete")
        self.assertEqual(verdict.policy_id, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

        partial_connection = MemoryConnection(
            {"source": copy.deepcopy(self.proof.source)}, self.proof
        )
        with self.assertRaisesRegex(StateConflictError, "proof_state_conflict"):
            inspect_state(partial_connection.cursor(), self.proof)

    def test_state_inspection_rejects_extra_matching_document_or_chunk(self) -> None:
        for key, singular in (("documents", "document"), ("chunks", "chunk")):
            state = exact_state(self.proof)
            expected = copy.deepcopy(state[singular])
            extra = copy.deepcopy(expected)
            extra["id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
            state[key] = [expected, extra]
            with self.subTest(key=key), self.assertRaisesRegex(
                StateConflictError, "proof_state_conflict"
            ):
                inspect_state(MemoryConnection(state, self.proof).cursor(), self.proof)

    def test_state_inspection_accepts_psycopg_uuid_values(self) -> None:
        state = exact_state(self.proof)
        for row_name, fields in (
            ("source", ("id",)),
            ("alias", ("id", "source_id")),
            ("document", ("id", "source_id")),
            ("chunk", ("id", "document_id")),
        ):
            for field in fields:
                state[row_name][field] = uuid.UUID(state[row_name][field])
        state["policies"][0]["id"] = uuid.UUID(state["policies"][0]["id"])
        state["policies"][0]["chunk_id"] = uuid.UUID(
            state["policies"][0]["chunk_id"]
        )
        self.assertEqual(
            inspect_state(MemoryConnection(state, self.proof).cursor(), self.proof).kind,
            "exact_complete",
        )

    def test_embedding_failure_opens_no_write_connection(self) -> None:
        factory = ConnectionFactory(self.proof)
        embed = EmbedRecorder(fail=True)
        with self.assertRaisesRegex(ProofApplyError, "embedding_failed"):
            apply_single_proof(factory, embed, self.proof, self.approval)
        self.assertEqual(factory.calls, ["preflight"])
        self.assertEqual(len(embed.calls), 1)
        self.assertEqual(factory.state, {})

    def test_malformed_embedding_opens_no_write_connection(self) -> None:
        factory = ConnectionFactory(self.proof)
        embed = EmbedRecorder(dimensions=2)
        with self.assertRaisesRegex(ProofApplyError, "embedding_invalid"):
            apply_single_proof(factory, embed, self.proof, self.approval)
        self.assertEqual(factory.calls, ["preflight"])
        self.assertEqual(factory.state, {})

    def test_exact_complete_skips_before_embedding(self) -> None:
        factory = ConnectionFactory(self.proof, exact_state(self.proof))
        embed = EmbedRecorder()
        result = apply_single_proof(factory, embed, self.proof, self.approval)
        self.assertEqual(embed.calls, [])
        self.assertEqual(factory.calls, ["preflight"])
        self.assertEqual(
            result["reconciliation"],
            {"attempted": 1, "stored": 0, "errored": 0, "skipped": 1},
        )
        self.assertEqual(result["reason"], "exact_proof_already_complete")

    def test_success_commits_exact_projection_in_required_order(self) -> None:
        factory = ConnectionFactory(self.proof)
        embed = EmbedRecorder()
        result = apply_single_proof(factory, embed, self.proof, self.approval)
        write = factory.connections[1]
        self.assertEqual(factory.calls, ["preflight", "write"])
        self.assertEqual(len(embed.calls), 1)
        self.assertEqual(write.commit_count, 1)
        self.assertEqual(write.rollback_count, 0)
        self.assertEqual(factory.state, exact_state(self.proof))
        self.assertEqual(
            result["reconciliation"],
            {"attempted": 1, "stored": 1, "errored": 0, "skipped": 0},
        )
        joined = "\n".join(write.events)
        self.assertIn("statement_timeout", joined)
        self.assertIn("lock_timeout", joined)
        for marker in (
            "SET LOCAL",
            "/* phase6:insert_source */",
            "/* phase6:insert_alias */",
            "/* phase6:insert_document */",
            "/* phase6:insert_chunk */",
            "/* phase6:insert_policy */",
            "/* phase6:stamp_complete */",
        ):
            self.assertIn(marker, joined)

    def test_policy_failure_rolls_back_every_staged_row(self) -> None:
        factory = ConnectionFactory(self.proof, fail_on="policy_insert")
        result = apply_single_proof(
            factory, EmbedRecorder(), self.proof, self.approval
        )
        write = factory.connections[1]
        self.assertEqual(write.commit_count, 0)
        self.assertEqual(write.rollback_count, 1)
        self.assertEqual(factory.state, {})
        self.assertEqual(
            result["reconciliation"],
            {"attempted": 1, "stored": 0, "errored": 1, "skipped": 0},
        )

    def test_write_connection_failure_reports_bounded_spend_and_error(self) -> None:
        preflight = MemoryConnection({}, self.proof)
        calls = []

        def factory(mode):
            calls.append(mode)
            if mode == "preflight":
                return preflight
            raise RuntimeError("write connection unavailable")

        result = apply_single_proof(
            factory, EmbedRecorder(), self.proof, self.approval
        )
        self.assertEqual(calls, ["preflight", "write"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "write_connection_failed")
        self.assertEqual(result["embedding"]["maximum_spend_usd"], "0.01")
        self.assertEqual(
            result["reconciliation"],
            {"attempted": 1, "stored": 0, "errored": 1, "skipped": 0},
        )

    def test_partial_state_fails_before_embedding(self) -> None:
        state = {"source": copy.deepcopy(self.proof.source)}
        factory = ConnectionFactory(self.proof, state)
        embed = EmbedRecorder()
        with self.assertRaisesRegex(StateConflictError, "proof_state_conflict"):
            apply_single_proof(factory, embed, self.proof, self.approval)
        self.assertEqual(embed.calls, [])
        self.assertEqual(factory.calls, ["preflight"])


class ReconcileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proof = build_aaron_projection(ROOT)

    def test_fresh_readonly_reconciliation_verifies_exact_hidden_proof(self) -> None:
        identity_factory = ConnectionFactory(self.proof, exact_state(self.proof))
        retrieval_state = {
            "current_user": "postgres",
            "retrieval_vector_count": 0,
            "retrieval_fts_count": 0,
        }
        retrieval_factory = ConnectionFactory(self.proof, retrieval_state)
        report = reconcile_single_proof(
            identity_factory, retrieval_factory, self.proof
        )
        identity_connection = identity_factory.connections[0]
        retrieval_connection = retrieval_factory.connections[0]
        self.assertEqual(identity_factory.calls, ["identity"])
        self.assertEqual(retrieval_factory.calls, ["retrieval"])
        self.assertEqual(
            identity_connection.session_calls,
            [{"readonly": True, "autocommit": True}],
        )
        self.assertEqual(
            retrieval_connection.session_calls,
            [{"readonly": True, "autocommit": True}],
        )
        self.assertEqual(report["status"], "verified")
        self.assertEqual(
            report["database_connections"],
            {
                "identity": "newwine_readonly_analysis",
                "retrieval": "postgres (read-only session)",
            },
        )
        self.assertEqual(
            report["reconciliation"],
            {"attempted": 1, "stored": 1, "errored": 0, "skipped": 0},
        )
        self.assertEqual(report["retrieval_matches"], {"vector": 0, "fts": 0})

    def test_reconciliation_rejects_wrong_role_or_retrieval_leak(self) -> None:
        wrong_role = exact_state(self.proof)
        wrong_role["current_user"] = "postgres"
        with self.assertRaisesRegex(ReconciliationError, "readonly_role_mismatch"):
            reconcile_single_proof(
                ConnectionFactory(self.proof, wrong_role),
                ConnectionFactory(self.proof),
                self.proof,
            )

        leaked = {
            "current_user": "postgres",
            "retrieval_vector_count": 1,
        }
        with self.assertRaisesRegex(ReconciliationError, "hidden_retrieval_leak"):
            reconcile_single_proof(
                ConnectionFactory(self.proof, exact_state(self.proof)),
                ConnectionFactory(self.proof, leaked),
                self.proof,
            )

    def test_reconciliation_rejects_metadata_drift(self) -> None:
        drifted = exact_state(self.proof)
        drifted["source"]["visibility"] = "shown"
        with self.assertRaisesRegex(StateConflictError, "proof_state_conflict"):
            reconcile_single_proof(
                ConnectionFactory(self.proof, drifted),
                ConnectionFactory(self.proof),
                self.proof,
            )

    def test_reconciliation_rejects_retrieval_session_that_is_not_readonly(self) -> None:
        retrieval_state = {
            "current_user": "postgres",
            "transaction_read_only": "off",
        }
        with self.assertRaisesRegex(
            ReconciliationError, "retrieval_session_not_readonly"
        ):
            reconcile_single_proof(
                ConnectionFactory(self.proof, exact_state(self.proof)),
                ConnectionFactory(self.proof, retrieval_state),
                self.proof,
            )

    def test_attempt_audit_distinguishes_clean_rollback_and_exact_commit(self) -> None:
        clean_identity = ConnectionFactory(self.proof)
        unused_retrieval = ConnectionFactory(self.proof)
        clean = reconcile_attempt(clean_identity, unused_retrieval, self.proof)
        self.assertEqual(clean["status"], "absent")
        self.assertEqual(unused_retrieval.calls, [])
        self.assertEqual(
            clean["reconciliation"],
            {"attempted": 1, "stored": 0, "errored": 1, "skipped": 0},
        )

        committed = reconcile_attempt(
            ConnectionFactory(self.proof, exact_state(self.proof)),
            ConnectionFactory(self.proof, {"current_user": "postgres"}),
            self.proof,
        )
        self.assertEqual(committed["status"], "verified")
        self.assertEqual(
            committed["reconciliation"],
            {"attempted": 1, "stored": 1, "errored": 0, "skipped": 0},
        )


class ApplyReportTests(unittest.TestCase):
    def test_post_commit_verifier_error_preserves_apply_result(self) -> None:
        proof = build_aaron_projection(ROOT)
        apply_factory = ConnectionFactory(proof)
        embed = EmbedRecorder()
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            same_day = {**valid_approval(), "operation_date": date.today().isoformat()}
            approval_path.write_text(json.dumps(same_day), encoding="utf-8")
            output = io.StringIO()
            with (
                patch(
                    "ingest_biblical_context_batch._load_apply_dependencies",
                    return_value=(apply_factory, embed),
                ),
                patch(
                    "reconcile_biblical_context_batch._load_reconcile_dependencies",
                    return_value=(ConnectionFactory(proof), ConnectionFactory(proof)),
                ),
                patch(
                    "reconcile_biblical_context_batch.reconcile_attempt",
                    side_effect=ReconciliationError("retrieval_permission_denied"),
                ),
                contextlib.redirect_stdout(output),
            ):
                exit_code = apply_main(["--approval-file", str(approval_path)])

        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "committed_reconciliation_failed")
        self.assertEqual(report["apply"]["status"], "stored")
        self.assertEqual(
            report["verification_error"],
            {
                "kind": "ReconciliationError",
                "reason": "retrieval_permission_denied",
            },
        )
        self.assertEqual(len(embed.calls), 1)


class CliCapabilityTests(unittest.TestCase):
    def test_apply_cli_exposes_no_source_entity_limit_or_batch_selector(self) -> None:
        for arguments in (
            ["--source", "other"],
            ["--entity", "H0071"],
            ["--limit", "2"],
            ["--batch-size", "2"],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                apply_main(arguments)

    def test_apply_cli_validates_approval_before_loading_external_dependencies(self) -> None:
        missing = Path(self.enterContext(tempfile.TemporaryDirectory())) / "missing.json"
        with patch(
            "ingest_biblical_context_batch._load_apply_dependencies",
            side_effect=AssertionError("dependencies loaded"),
        ):
            with self.assertRaisesRegex(ApprovalError, "approval_missing"):
                apply_main(["--approval-file", str(missing)])

    def test_reconcile_cli_has_readonly_verify_mode_only(self) -> None:
        for arguments in (["--apply"], ["--source", "other"]):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                reconcile_main(arguments)


if __name__ == "__main__":
    unittest.main()
