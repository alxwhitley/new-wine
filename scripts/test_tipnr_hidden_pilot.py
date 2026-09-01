#!/usr/bin/env python3
"""Tests for the execution-ready, unexecuted Phase 8 TIPNR hidden pilot."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock
from datetime import date
import json


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from tipnr_hidden_pilot_contract import (  # noqa: E402
    SAMPLE_IDS,
    SELECTION_SHA256,
    build_pilot_packet,
    pilot_packet_report,
)
from biblical_context_ingest_contract import build_aaron_projection  # noqa: E402
from preview_tipnr_hidden_pilot import (  # noqa: E402
    build_pilot_preview,
    main as preview_main,
    write_new_pilot_preview,
)
from preflight_tipnr_hidden_pilot import (  # noqa: E402
    PilotPreflightError,
    preflight_pilot,
)
from apply_tipnr_hidden_pilot import (  # noqa: E402
    finalize_pilot_apply,
    PilotApplyError,
    PilotApprovalError,
    apply_pilot,
    validate_pilot_approval,
)
import apply_tipnr_hidden_pilot as pilot_apply  # noqa: E402
from reconcile_tipnr_hidden_pilot import (  # noqa: E402
    PilotReconciliationError,
    build_sample_report,
    reconcile_pilot,
)


EXPECTED_SELECTION = (
    ("person", "G0010", "5f791ad27a2902eb4422435b006cbb883899743b809f6786d7367d56183217b6"),
    ("person", "G0013", "f0b76e34a79d674af2d1362600b2b50bc63d7715e64a6c70e43dac4b35ff1565"),
    ("person", "G0078", "40c276c2fe9f9ee8fb54e9367953c3f3512be8218d56f143a8f82a446b16d4e5"),
    ("person", "G0107", "53988a7194f676b6b05db7f4fad96c9fd39d4e1821d3ac0087302c285b9cb2d7"),
    ("person", "G0132", "49c0e19a38133366a95c02ccaf036912c121692a98c5f9929a91aeb64f06e52d"),
    ("person", "G0207", "524273dd4cdb03f65a55eb1d05b5b4b84cacd46695058eb801005ec0362832fb"),
    ("person", "G0223G", "1037130044b799c3ac8e53248595278e2fc36210f54fb46873f218c6018ed5fa"),
    ("person", "G0223H", "1a8187197a906d2a7f2159b2d5a200ecaeb1cb068af85c2edc5d4aa0dd0a7255"),
    ("person", "G0223I", "71af8b3d2f8436c87836813f8b397051f7bbf15dba4461f637d4fdc4702927c1"),
    ("person", "G0223J", "3d965783438391d723cbaf1c3e4d52852f6fb45c8a6c0c6d3dbf41a54f8b1274"),
    ("place", "G0009", "b8db1dee76c7416fba5d45e3ad29f56951340cd4d23417c181364ed82b665614"),
    ("place", "G0098", "1ae34ab14cf2cda6ddf7928bcdf071cdcf4b4fbfe47862f44656cc6125fd6dd0"),
    ("place", "G0099", "4a034fd1f32510a0b56656ecd3c4b962de07dac64bb432073d624a43ea855698"),
    ("place", "G0116", "7b18e321b2ce1694ce2e5b08df32e4763f75626045cdebb184d310af30bfcb2d"),
    ("place", "G0137", "02c22cb23dfcd7855010bbc6478f9b82fc3516adfba4eb120c2215d917d906c3"),
    ("place", "G0222", "b5c77b572a3c906e9ab698f75a70892a5be0eb1734bf73733ea8397639a1c533"),
    ("place", "G0295", "bb0148822af539bab599009b7edcdbfc964f1907543971ddf22075e3ced2b326"),
    ("place", "G0490G", "379c668f35076ec02f97c9064088096d382a69f9bf74dbe86d1331e5c8c3d54f"),
    ("place", "G0490H", "2ed5af6fa2fe7126c2d992a3547255d28e8d231cc31f42abaf594532a1f39dd0"),
    ("place", "G0494", "28664288bc469b0f425f6855f909748296de5d1015821c5b99591acd107c9d24"),
)


def _artifact() -> Path:
    value = os.environ.get("TIPNR_TEST_ARTIFACT")
    if not value:
        raise unittest.SkipTest("TIPNR_TEST_ARTIFACT is not set")
    return Path(value)


class PilotPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = build_pilot_packet(ROOT, _artifact())

    def test_selects_exact_balanced_twenty_and_excludes_h0175(self) -> None:
        self.assertEqual(len(self.packet.items), 20)
        self.assertEqual(
            Counter(item.entity_type for item in self.packet.items),
            {"person": 10, "place": 10},
        )
        self.assertNotIn("H0175", [item.entity_id for item in self.packet.items])
        self.assertEqual(self.packet.selection_checksum, SELECTION_SHA256)
        self.assertEqual(
            tuple(
                (item.entity_type, item.entity_id, item.record["record_sha256"])
                for item in self.packet.items
            ),
            EXPECTED_SELECTION,
        )

    def test_projects_one_document_chunk_and_policy_per_item(self) -> None:
        self.assertEqual(len({item.document["id"] for item in self.packet.items}), 20)
        self.assertTrue(
            all(item.chunk["document_id"] == item.document["id"] for item in self.packet.items)
        )
        self.assertTrue(
            all(item.policy["chunk_id"] == item.chunk["id"] for item in self.packet.items)
        )
        self.assertTrue(
            all(item.policy["policy_class"] == "general_context" for item in self.packet.items)
        )

    def test_sample_and_serialized_packet_keep_only_approved_projection(self) -> None:
        self.assertEqual(self.packet.sample_ids, SAMPLE_IDS)
        report_text = repr(pilot_packet_report(self.packet)).lower()
        for excluded in ("briefest", "@brief", "@article", "@ambiguity", "relationship"):
            self.assertNotIn(excluded, report_text)


class PilotPreviewTests(unittest.TestCase):
    def test_preview_freezes_zero_effect_boundary(self) -> None:
        report = build_pilot_preview(ROOT, _artifact())
        self.assertIs(report["database_write_authorized"], False)
        self.assertIs(report["external_model_call_authorized"], False)
        self.assertEqual(report["counts"], {
            "items": 20, "documents": 20, "chunks": 20,
            "policy_rows": 20, "embedding_requests": 20,
        })
        self.assertEqual(report["maximum_spend_usd"], "0.01")
        self.assertEqual(report["reconciliation"], {
            "attempted": 20, "stored": 0, "errored": 0, "skipped": 20,
            "reason": "preview_only",
        })

    def test_preview_main_never_opens_network(self) -> None:
        with mock.patch("socket.socket", side_effect=AssertionError("network opened")):
            with mock.patch("sys.stdout"):
                self.assertEqual(preview_main(["--artifact", str(_artifact())]), 0)

    def test_preview_writer_is_create_new_and_byte_identical_only(self) -> None:
        local_root = ROOT / "local"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            target = Path(directory) / "preview.json"
            write_new_pilot_preview(target, b"same\n")
            write_new_pilot_preview(target, b"same\n")
            self.assertEqual(target.read_bytes(), b"same\n")
            with self.assertRaises(FileExistsError):
                write_new_pilot_preview(target, b"different\n")

    def test_preview_rejects_effect_and_selection_flags(self) -> None:
        for flag in ("--apply", "--limit", "--offset", "--entity-id"):
            with self.subTest(flag=flag), self.assertRaises(SystemExit):
                preview_main(["--artifact", str(_artifact()), flag, "1"])


class _PilotStateCursor:
    def __init__(self, state):
        self.state = state
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=()):
        if "phase8:transaction_read_only" in sql:
            self.result = (self.state.get("transaction_read_only", "on"),)
        elif "phase8:current_user" in sql:
            self.result = (self.state.get("current_user", "newwine_readonly_analysis"),)
        elif "phase8:retrieval_vector" in sql:
            self.result = (self.state.get("retrieval_vector_count", 0),)
        elif "phase8:retrieval_fts" in sql:
            self.result = (self.state.get("retrieval_fts_count", 0),)
        elif "phase8:source" in sql:
            self.result = self.state.get("source_rows", [])
        elif "phase8:alias" in sql:
            self.result = self.state.get("alias_rows", [])
        else:
            items = self.state.get("items", {})
            if "phase8:chunk" in sql:
                item_state = items.get(str(params[1]), {})
            elif "phase8:policies" in sql:
                item_state = next(
                    (
                        value for value in items.values()
                        if value.get("chunk", {}).get("id") == str(params[0])
                    ),
                    {},
                )
            else:
                item_state = items.get(str(params[0]), {})
            if "phase8:document" in sql:
                self.result = item_state.get("document")
            elif "phase8:chunk" in sql:
                self.result = item_state.get("chunk")
            elif "phase8:policies" in sql:
                self.result = item_state.get("policies", [])
            elif "phase8:propositions" in sql:
                self.result = (item_state.get("proposition_count", 0),)
            else:
                raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result if isinstance(self.result, list) else ([] if self.result is None else [self.result])


class _PilotStateConnection:
    def __init__(self, state):
        self.state = state
        self.session_calls = []
        self.closed = False

    def set_session(self, **kwargs):
        self.session_calls.append(kwargs)

    def cursor(self):
        return _PilotStateCursor(self.state)

    def close(self):
        self.closed = True


def _complete_item_state(item):
    return {
        "document": {**item.document, "ingest_completed_at": "set"},
        "chunk": {**item.chunk, "embedding_dimensions": 1536},
        "policies": [{"id": f"policy-{item.entity_id}", **item.policy}],
        "proposition_count": 0,
    }


class PilotPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = build_pilot_packet(ROOT, _artifact())

    def _run(self, state):
        connection = _PilotStateConnection(state)
        proof_calls = []

        def proof_verifier(identity_factory, retrieval_factory, proof):
            proof_calls.append(proof.entity_id)
            return {"status": "verified"}

        report = preflight_pilot(
            lambda mode: connection,
            lambda mode: None,
            self.packet,
            build_aaron_projection(ROOT),
            proof_verifier=proof_verifier,
            invariant_checker=lambda: None,
        )
        self.assertEqual(proof_calls, ["H0175"])
        self.assertEqual(connection.session_calls, [{"readonly": True, "autocommit": True}])
        return report

    def test_all_clean_requires_exact_h0175_verification(self) -> None:
        report = self._run({})
        self.assertEqual(report["candidate_state"], "all_clean")
        self.assertEqual(report["counts"], {"clean": 20, "exact_complete": 0})
        self.assertEqual(report["single_item_verification"]["status"], "verified")

    def test_all_exact_complete_is_idempotent(self) -> None:
        state = {"items": {
            item.document["id"]: _complete_item_state(item)
            for item in self.packet.items
        }}
        report = self._run(state)
        self.assertEqual(report["candidate_state"], "all_exact_complete")
        self.assertEqual(report["counts"], {"clean": 0, "exact_complete": 20})

    def test_mixed_state_fails_closed(self) -> None:
        state = {"items": {
            self.packet.items[0].document["id"]: _complete_item_state(self.packet.items[0])
        }}
        with self.assertRaisesRegex(PilotPreflightError, "candidate_state_mixed"):
            self._run(state)

    def test_partial_or_proposition_state_fails_closed(self) -> None:
        first = self.packet.items[0]
        for item_state in (
            {"document": {**first.document, "ingest_completed_at": None}},
            {"proposition_count": 1},
        ):
            with self.subTest(item_state=item_state), self.assertRaisesRegex(
                PilotPreflightError, "candidate_state_conflict"
            ):
                self._run({"items": {first.document["id"]: item_state}})


def _approval(packet, operation_date="2026-09-01"):
    return {
        "schema_version": "biblical_context_tipnr_hidden_pilot_approval.v1",
        "approved_by": "Alex Whitley",
        "operation_date": operation_date,
        "source_slug": "stepbible-tipnr",
        "packet_sha256": packet.packet_sha256,
        "selection_checksum": packet.selection_checksum,
        "item_count": 20,
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
        "maximum_embedding_requests": 20,
        "maximum_spend_usd": "0.01",
        "embedding_requests_authorized": True,
        "single_database_transaction_authorized": True,
    }


class PilotApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = build_pilot_packet(ROOT, _artifact())

    def test_approval_must_match_exact_packet_and_day(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approval.json"
            expected = _approval(self.packet)
            path.write_text(json.dumps(expected), encoding="utf-8")
            self.assertEqual(
                validate_pilot_approval(path, self.packet, date(2026, 9, 1)),
                expected,
            )
            for key, wrong in (
                ("packet_sha256", "0" * 64),
                ("item_count", 19),
                ("embedding_dimensions", 2),
                ("operation_date", "2026-08-31"),
                ("maximum_spend_usd", "1.00"),
                ("embedding_requests_authorized", False),
            ):
                mutated = dict(expected)
                mutated[key] = wrong
                path.write_text(json.dumps(mutated), encoding="utf-8")
                with self.subTest(key=key), self.assertRaisesRegex(
                    PilotApprovalError, "approval_scope_mismatch"
                ):
                    validate_pilot_approval(path, self.packet, date(2026, 9, 1))

    def test_all_vectors_finish_before_write_connection(self) -> None:
        events = []

        def embed(text, *, model, dimensions):
            entity = text.split("Entity ID: ", 1)[1].splitlines()[0]
            events.append(f"embed:{entity}")
            return [0.001] * dimensions

        def connection_factory(mode):
            events.append(f"connect:{mode}")
            raise RuntimeError("write unavailable")

        report = apply_pilot(
            connection_factory,
            embed,
            self.packet,
            _approval(self.packet),
            lambda: {"candidate_state": "all_clean"},
        )
        self.assertEqual(events[:20], [f"embed:{item.entity_id}" for item in self.packet.items])
        self.assertEqual(events[20], "connect:write")
        self.assertEqual(report["reconciliation"], {
            "attempted": 20, "stored": 0, "errored": 20, "skipped": 0,
        })

    def test_embedding_failure_reports_exact_progress_and_opens_no_write_connection(self) -> None:
        for fail_at in (1, 20):
            with self.subTest(fail_at=fail_at):
                connections = []
                calls = []

                def embed(text, **kwargs):
                    calls.append(text)
                    if len(calls) == fail_at:
                        raise RuntimeError("request failed")
                    return [0.001] * 1536

                report = apply_pilot(
                    lambda mode: connections.append(mode),
                    embed,
                    self.packet,
                    _approval(self.packet),
                    lambda: {"candidate_state": "all_clean"},
                )
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["reason"], "embedding_failed")
                self.assertEqual(report["embedding"], {
                    "requests_attempted": fail_at,
                    "requests_completed": fail_at - 1,
                    "requests_failed": 1,
                    "model": "text-embedding-3-small",
                    "dimensions": 1536,
                    "maximum_spend_usd": "0.01",
                })
                self.assertEqual(report["reconciliation"], {
                    "attempted": 20, "stored": 0, "errored": 20, "skipped": 0,
                })
                self.assertEqual(connections, [])

    def test_all_complete_skips_without_embedding_or_write(self) -> None:
        events = []
        report = apply_pilot(
            lambda mode: events.append(f"connect:{mode}"),
            lambda *args, **kwargs: events.append("embed"),
            self.packet,
            _approval(self.packet),
            lambda: {"candidate_state": "all_exact_complete"},
        )
        self.assertEqual(events, [])
        self.assertEqual(report["reconciliation"], {
            "attempted": 20, "stored": 0, "errored": 0, "skipped": 20,
        })

    def test_atomic_writer_commits_all_sixty_rows_once(self) -> None:
        connection = _PilotWriteConnection(self.packet)
        report = apply_pilot(
            lambda mode: connection,
            lambda text, **kwargs: [0.001] * 1536,
            self.packet,
            _approval(self.packet),
            lambda: {"candidate_state": "all_clean"},
        )
        self.assertEqual(connection.commit_count, 1)
        self.assertEqual(connection.rollback_count, 0)
        self.assertEqual(report["reconciliation"], {
            "attempted": 20, "stored": 20, "errored": 0, "skipped": 0,
        })
        self.assertEqual(len(connection.state), 20)
        self.assertTrue(all(row["document"]["ingest_completed_at"] == "set" for row in connection.state.values()))

    def test_post_commit_verifier_error_preserves_apply_evidence(self) -> None:
        apply_report = {
            "status": "stored",
            "reconciliation": {"attempted": 20, "stored": 20, "errored": 0, "skipped": 0},
        }

        def failed_verifier():
            raise RuntimeError("fresh verification unavailable")

        final = finalize_pilot_apply(apply_report, failed_verifier)
        self.assertEqual(final["status"], "committed_reconciliation_failed")
        self.assertEqual(final["apply"], apply_report)
        self.assertIsNone(final["verification"])
        self.assertEqual(final["verification_error"]["kind"], "RuntimeError")

    def test_attempt_evidence_is_content_addressed_and_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "local") as directory:
            evidence_dir = Path(directory)
            first_payload = b'{"status":"failed"}\n'
            first = pilot_apply.write_pilot_attempt_evidence(
                evidence_dir, first_payload
            )
            repeated = pilot_apply.write_pilot_attempt_evidence(
                evidence_dir, first_payload
            )
            second = pilot_apply.write_pilot_attempt_evidence(
                evidence_dir, b'{"status":"verified"}\n'
            )

            self.assertEqual(first, repeated)
            self.assertEqual(
                first.name,
                "tipnr_hidden_pilot_attempt_"
                "7fd0d3d434f0a0935c3b41f2e3a1f373bb10ee85dc2178c4e8c47e2f2e590ec6.json",
            )
            self.assertEqual(first.read_bytes(), first_payload)
            self.assertNotEqual(first, second)
            self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o600)

    def test_finalize_persists_failed_attempt_before_returning(self) -> None:
        apply_report = {
            "status": "failed",
            "reason": "write_connection_failed",
            "embedding": {
                "requests_attempted": 20,
                "requests_completed": 20,
                "requests_failed": 0,
                "model": "text-embedding-3-small",
                "dimensions": 1536,
                "maximum_spend_usd": "0.01",
            },
            "reconciliation": {
                "attempted": 20, "stored": 0, "errored": 20, "skipped": 0,
            },
        }

        def failed_verifier():
            raise RuntimeError("candidate_not_complete")

        with tempfile.TemporaryDirectory(dir=ROOT / "local") as directory:
            evidence_dir = Path(directory)
            final, payload = (
                pilot_apply.finalize_and_persist_pilot_apply(
                    apply_report, failed_verifier, evidence_dir
                )
            )
            evidence_paths = list(
                evidence_dir.glob("tipnr_hidden_pilot_attempt_*.json")
            )

            self.assertEqual(
                final["status"], "commit_outcome_unknown_reconciliation_failed"
            )
            self.assertEqual(final["apply"], apply_report)
            self.assertEqual(len(evidence_paths), 1)
            self.assertEqual(evidence_paths[0].read_bytes(), payload)
            self.assertEqual(json.loads(payload), final)
            self.assertEqual(stat.S_IMODE(evidence_paths[0].stat().st_mode), 0o600)


class _PilotWriteCursor:
    DOCUMENT_FIELDS = (
        "id", "title", "original_title", "author", "source_name", "source_type",
        "source_kind", "citation_mode", "source", "topic_tags", "bible_references",
        "file_path", "is_copyrighted", "full_text", "source_id", "url",
    )
    POLICY_FIELDS = (
        "chunk_id", "policy_class", "protected_topic_keys", "issue_key",
        "viewpoint_key", "classifier_kind", "rule_version", "model",
        "prompt_fingerprint", "reason_codes", "is_current",
    )

    def __init__(self, connection):
        self.connection = connection
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def _by_chunk(self, chunk_id):
        return next((row for row in self.connection.state.values() if row.get("chunk", {}).get("id") == str(chunk_id)), None)

    def execute(self, sql, params=()):
        if sql.strip().startswith("SET LOCAL"):
            self.result = None
        elif "phase8:source" in sql:
            self.result = [dict(self.connection.packet.source)]
        elif "phase8:alias" in sql:
            self.result = [dict(self.connection.packet.alias)]
        elif "phase8:document" in sql:
            row = self.connection.state.get(str(params[0]), {})
            self.result = row.get("document")
        elif "phase8:chunk" in sql:
            row = self.connection.state.get(str(params[1]), {})
            self.result = row.get("chunk")
        elif "phase8:policies" in sql:
            row = self._by_chunk(params[0]) or {}
            self.result = row.get("policies", [])
        elif "phase8:propositions" in sql:
            self.result = (0,)
        elif "phase8:insert_document" in sql:
            document = dict(zip(self.DOCUMENT_FIELDS, params))
            document["ingest_completed_at"] = None
            self.connection.state[str(document["id"])] = {"document": document}
            self.result = None
        elif "phase8:insert_chunk" in sql:
            row = self.connection.state[str(params[1])]
            row["chunk"] = {
                "id": params[0], "document_id": params[1], "content": params[2],
                "chunk_index": params[4], "bible_references": params[5],
                "embedding_dimensions": 1536,
            }
            self.result = None
        elif "phase8:insert_policy" in sql:
            row = self._by_chunk(params[0])
            policy_id = f"policy-{len([x for x in self.connection.state.values() if x.get('policies')]) + 1:02d}"
            row["policies"] = [{"id": policy_id, **dict(zip(self.POLICY_FIELDS, params))}]
            self.result = (policy_id,)
        elif "phase8:stamp_complete" in sql:
            for document_id in params[0]:
                self.connection.state[str(document_id)]["document"]["ingest_completed_at"] = "set"
            self.result = None
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result if isinstance(self.result, list) else ([] if self.result is None else [self.result])


class _PilotWriteConnection:
    def __init__(self, packet):
        self.packet = packet
        self.state = {}
        self.autocommit = None
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return _PilotWriteCursor(self)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1
        self.state.clear()

    def close(self):
        pass


class PilotReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = build_pilot_packet(ROOT, _artifact())

    def _identity_state(self):
        return {
            "source_rows": [dict(self.packet.source)],
            "alias_rows": [dict(self.packet.alias)],
            "items": {
                item.document["id"]: _complete_item_state(item)
                for item in self.packet.items
            },
        }

    def test_verified_report_reconciles_every_item_and_probe(self) -> None:
        identity = _PilotStateConnection(self._identity_state())
        retrieval = _PilotStateConnection({"current_user": "postgres"})
        report = reconcile_pilot(
            lambda mode: identity,
            lambda mode: retrieval,
            self.packet,
        )
        self.assertEqual(report["reconciliation"], {
            "attempted": 20, "stored": 20, "errored": 0, "skipped": 0,
        })
        self.assertEqual(report["retrieval_probes"], {
            "vector_attempted": 20, "vector_matches": 0,
            "fts_attempted": 20, "fts_matches": 0,
        })

    def test_one_retrieval_match_fails_closed(self) -> None:
        with self.assertRaisesRegex(PilotReconciliationError, "hidden_retrieval_leak"):
            reconcile_pilot(
                lambda mode: _PilotStateConnection(self._identity_state()),
                lambda mode: _PilotStateConnection({
                    "current_user": "postgres", "retrieval_fts_count": 1,
                }),
                self.packet,
            )

    def test_absent_candidate_cannot_be_verified(self) -> None:
        state = self._identity_state()
        state["items"] = {}
        with self.assertRaisesRegex(PilotReconciliationError, "candidate_not_complete"):
            reconcile_pilot(
                lambda mode: _PilotStateConnection(state),
                lambda mode: _PilotStateConnection({"current_user": "postgres"}),
                self.packet,
            )

    def test_sample_is_exact_first_middle_last_per_type(self) -> None:
        sample = build_sample_report(self.packet)
        self.assertEqual(
            [row["entity_id"] for row in sample["items"]],
            list(SAMPLE_IDS),
        )
        serialized = repr(sample).lower()
        for excluded in ("briefest", "@brief", "@article", "@ambiguity", "relationship"):
            self.assertNotIn(excluded, serialized)


if __name__ == "__main__":
    unittest.main()
