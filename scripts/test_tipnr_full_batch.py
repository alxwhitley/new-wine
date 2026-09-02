#!/usr/bin/env python3
"""Contract tests for the remaining TIPNR corpus and its 20 atomic batches.

Requires the pinned artifact via TIPNR_TEST_ARTIFACT.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import tipnr_full_batch_contract as contract  # noqa: E402
from biblical_context_ingest_contract import (  # noqa: E402
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    build_aaron_projection,
)
from biblical_context_tooling import canonical_json_bytes, canonical_sha256  # noqa: E402
from parse_tipnr_context import (  # noqa: E402
    TIPNR_ARTIFACT_BYTES,
    TIPNR_ARTIFACT_SHA256,
)
from tipnr_full_batch_contract import (  # noqa: E402
    BATCH_COUNT,
    BATCH_SIZE,
    COMPLETED_COUNT,
    EXPECTED_ROW_TOTAL,
    FINAL_BATCH_SIZE,
    MAXIMUM_SPEND_USD,
    REMAINING_BY_TYPE,
    REMAINING_COUNT,
    FullBatchContractError,
    build_full_batch_packet,
    full_batch_packet_report,
    full_batch_summary,
)
from tipnr_hidden_pilot_contract import EXPECTED_SELECTION, build_pilot_packet  # noqa: E402


FIXTURE = ROOT / "scripts" / "fixtures" / "biblical_context" / "tipnr_full_batch_expected.json"

# Field families the approved Phase 0/2 allowlist excludes. None may appear in
# any serialized packet, text, fixture, or sample byte.
_PROHIBITED_MARKERS = (
    "@Briefest", "@Brief=", "@Short=", "@Article=",
    "Excluded generated prose", "Excluded summary", "Excluded map URL",
    "translated_name", "ambiguity", "relationship", "relatives",
    "father", "mother", "siblings", "spouse", "children", "tribe",
)



def _imported_modules(path: Path) -> set[str]:
    """Return every top-level module name imported by a source file."""

    import ast

    tree = ast.parse(path.read_text("utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


_FORBIDDEN_IMPORTS = frozenset({
    "psycopg2", "openai", "requests", "httpx", "urllib", "urllib3",
    "socket", "boto3", "aiohttp",
})
_WRITE_VERB_MARKERS = ("INSERT INTO", "UPDATE ", "DELETE FROM", ".commit()")


def _declared_cli_flags(path: Path) -> set[str]:
    """Return every flag literal actually registered with argparse."""

    import ast

    tree = ast.parse(path.read_text("utf-8"))
    flags: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
        ):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    flags.add(arg.value)
    return flags


def _artifact() -> Path:
    value = os.environ.get("TIPNR_TEST_ARTIFACT")
    if not value:
        raise unittest.SkipTest("TIPNR_TEST_ARTIFACT is not set")
    path = Path(value)
    if not path.is_file():
        raise unittest.SkipTest("TIPNR_TEST_ARTIFACT does not exist")
    return path


class _PacketMixin(unittest.TestCase):
    packet = None

    @classmethod
    def setUpClass(cls):
        cls.artifact = _artifact()
        if _PacketMixin.packet is None:
            _PacketMixin.packet = build_full_batch_packet(ROOT, cls.artifact)
        cls.packet = _PacketMixin.packet


class TipnrFullBatchContractTests(_PacketMixin):
    """Pin artifact identity, counts, ordering, batch geometry, and hashes."""

    def test_artifact_identity_is_pinned(self):
        payload = self.artifact.read_bytes()
        self.assertEqual(len(payload), TIPNR_ARTIFACT_BYTES)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), TIPNR_ARTIFACT_SHA256)

    def test_phase7_hashes_and_counts_are_required(self):
        self.assertEqual(contract.PHASE7_INVENTORY_SHA256,
                         "edb6dece3a9d2772ec9dfb21a80d192225ec14878084e5b30cb38ea667b80040")
        self.assertEqual(contract.PHASE7_ELIGIBLE_SHA256,
                         "1c7fdf4f7d587fdcfa7cf076732f913ef9b1066d50a0a5de9e227c7c1cf80cc2")
        self.assertEqual(contract.EXPECTED_OUTCOME_COUNTS, {
            "duplicate": 0, "eligible": 3959, "malformed": 172,
            "prohibited": 16, "skipped": 115,
        })
        self.assertEqual(contract.EXPECTED_ELIGIBLE_BY_TYPE,
                         {"person": 3055, "place": 904})

    def test_remaining_identities_are_exactly_3939(self):
        items = self.packet.items
        self.assertEqual(len(items), REMAINING_COUNT)
        self.assertEqual(REMAINING_COUNT, 3939)
        self.assertEqual(len({item.entity_id for item in items}), REMAINING_COUNT)
        by_type = {"person": 0, "place": 0}
        for item in items:
            by_type[item.entity_type] += 1
        self.assertEqual(by_type, REMAINING_BY_TYPE)
        self.assertEqual(by_type, {"person": 3045, "place": 894})

    def test_aaron_is_in_the_remaining_set_with_the_artifact_projection(self):
        """Production holds only the reduced fixture Aaron, never this one."""

        matches = [item for item in self.packet.items if item.entity_id == "H0175"]
        self.assertEqual(len(matches), 1)
        aaron = matches[0]
        self.assertEqual(aaron.entity_type, "person")
        self.assertEqual(len(aaron.document["bible_references"]), 352)

        fixture_proof = build_aaron_projection(ROOT)
        self.assertNotEqual(aaron.record["record_sha256"],
                            fixture_proof.record["record_sha256"])
        self.assertNotEqual(aaron.document["id"], fixture_proof.document["id"])
        self.assertEqual(len(fixture_proof.document["bible_references"]), 4)

    def test_completed_pilot_identities_are_excluded(self):
        remaining_ids = {item.entity_id for item in self.packet.items}
        self.assertEqual(len(EXPECTED_SELECTION), COMPLETED_COUNT)
        for _, entity_id, _ in EXPECTED_SELECTION:
            self.assertNotIn(entity_id, remaining_ids)
        self.assertEqual(REMAINING_COUNT + COMPLETED_COUNT, 3959)

    def test_canonical_order_is_people_then_places_by_entity_id(self):
        items = self.packet.items
        types = [item.entity_type for item in items]
        self.assertEqual(types, ["person"] * 3045 + ["place"] * 894)
        people = [item.entity_id for item in items[:3045]]
        places = [item.entity_id for item in items[3045:]]
        self.assertEqual(people, sorted(people))
        self.assertEqual(places, sorted(places))

    def test_batch_geometry_is_nineteen_full_batches_and_one_remainder(self):
        batches = self.packet.batches
        self.assertEqual(len(batches), BATCH_COUNT)
        self.assertEqual(len(batches), 20)
        sizes = [batch.size for batch in batches]
        self.assertEqual(sizes, [BATCH_SIZE] * 19 + [FINAL_BATCH_SIZE])
        self.assertEqual(sizes, [200] * 19 + [139])
        self.assertEqual(sum(sizes), 3939)
        self.assertEqual([batch.index for batch in batches], list(range(1, 21)))

    def test_batches_partition_the_remaining_items_in_order(self):
        rebuilt = [item.entity_id for batch in self.packet.batches for item in batch.items]
        self.assertEqual(rebuilt, [item.entity_id for item in self.packet.items])
        self.assertEqual(len(set(rebuilt)), REMAINING_COUNT)
        for batch in self.packet.batches:
            self.assertEqual(batch.first_entity_id, batch.items[0].entity_id)
            self.assertEqual(batch.last_entity_id, batch.items[-1].entity_id)

    def test_batch_and_packet_hashes_are_stable_and_distinct(self):
        hashes = [batch.batch_sha256 for batch in self.packet.batches]
        self.assertEqual(len(set(hashes)), BATCH_COUNT)
        for value in hashes:
            self.assertRegex(value, r"^[0-9a-f]{64}$")
        self.assertRegex(self.packet.packet_sha256, r"^[0-9a-f]{64}$")
        again = build_full_batch_packet(ROOT, self.artifact)
        self.assertEqual(again.packet_sha256, self.packet.packet_sha256)
        self.assertEqual([b.batch_sha256 for b in again.batches], hashes)

    def test_packet_report_hash_covers_every_projection(self):
        report = full_batch_packet_report(self.packet)
        self.assertEqual(report["packet_sha256"], self.packet.packet_sha256)
        mutated = copy.deepcopy(report)
        mutated.pop("packet_sha256")
        mutated["batches"][0]["items"][0]["document"]["title"] = "tampered"
        self.assertNotEqual(canonical_sha256(mutated), self.packet.packet_sha256)

    def test_deterministic_sample_is_ten_frozen_ids(self):
        sample = self.packet.sample_ids
        self.assertEqual(len(sample), 10)
        items = self.packet.items
        people = [i.entity_id for i in items if i.entity_type == "person"]
        places = [i.entity_id for i in items if i.entity_type == "place"]
        expected = []
        for subset in (people, places):
            last = len(subset) - 1
            expected.extend(subset[index] for index in
                            (0, last // 4, last // 2, (3 * last) // 4, last))
        self.assertEqual(list(sample), expected)


class TipnrFullBatchPricingTests(_PacketMixin):
    """Freeze rendered bytes, token estimate, request ceiling, and row totals."""

    def test_rendered_bytes_match_the_sum_of_item_texts(self):
        total = sum(len(item.text.encode("utf-8")) for item in self.packet.items)
        self.assertEqual(self.packet.rendered_bytes, total)
        self.assertEqual(
            sum(batch.rendered_bytes for batch in self.packet.batches), total
        )

    def test_token_estimate_is_conservative(self):
        self.assertEqual(self.packet.estimated_tokens,
                         (self.packet.rendered_bytes + 2) // 3)
        self.assertGreaterEqual(self.packet.estimated_tokens * 3,
                                self.packet.rendered_bytes)

    def test_request_ceiling_is_one_per_remaining_item(self):
        self.assertEqual(self.packet.embedding_request_ceiling, REMAINING_COUNT)
        self.assertEqual(self.packet.embedding_request_ceiling, 3939)

    def test_cost_ceiling_is_not_widened_by_a_lower_estimate(self):
        self.assertEqual(self.packet.maximum_spend_usd, MAXIMUM_SPEND_USD)
        self.assertEqual(MAXIMUM_SPEND_USD, "0.02441808")
        self.assertLessEqual(Decimal(self.packet.estimated_cost_usd),
                             Decimal(MAXIMUM_SPEND_USD))

    def test_row_totals_are_three_per_item_across_twenty_transactions(self):
        self.assertEqual(self.packet.row_total, EXPECTED_ROW_TOTAL)
        self.assertEqual(self.packet.row_total, 11817)
        self.assertEqual(REMAINING_COUNT * 3, 11817)
        self.assertEqual(len(self.packet.batches), 20)

    def test_global_totals_reflect_the_corrected_aaron_resolution(self):
        totals = full_batch_summary(self.packet)["global_totals_after_ingest"]
        self.assertEqual(totals, {
            "current_policies": 3959,
            "documents": 3960,
            "chunks": 3960,
            "inert_superseded_documents": 1,
            "propositions": 0,
        })


class TipnrFullBatchRefusalTests(_PacketMixin):
    """The contract refuses caller steering and any projection drift."""

    def test_builder_exposes_no_selection_limit_offset_or_source_override(self):
        signature = inspect.signature(contract.build_full_batch_packet)
        self.assertEqual(list(signature.parameters), ["root", "artifact_path"])
        forbidden = ("select", "limit", "offset", "entity", "source", "url",
                     "count", "batch", "apply", "commit")
        text = inspect.getsource(contract.build_full_batch_packet)
        for name in forbidden:
            self.assertNotIn(f"{name}=", signature.parameters)
        self.assertNotIn("argparse", text)

    def test_alternate_artifact_is_refused(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as handle:
            handle.write(b"not the pinned artifact")
            temp = Path(handle.name)
        try:
            with self.assertRaises(Exception):
                build_full_batch_packet(ROOT, temp)
        finally:
            temp.unlink(missing_ok=True)

    def test_unrecognized_record_field_is_refused(self):
        record = copy.deepcopy(self.packet.items[0].record)
        record["unexpected"] = "value"
        with self.assertRaises(FullBatchContractError):
            contract.build_item(record, {"source_kind": "biblical_context",
                                         "citation_mode": "citable",
                                         "url": "https://example.invalid"}, "sid")

    def test_drifted_record_checksum_is_refused(self):
        record = copy.deepcopy(self.packet.items[0].record)
        record["record_sha256"] = "0" * 64
        with self.assertRaises(FullBatchContractError):
            contract.build_item(record, {"source_kind": "biblical_context",
                                         "citation_mode": "citable",
                                         "url": "https://example.invalid"}, "sid")

    def test_drift_in_a_completed_pilot_projection_is_refused(self):
        original = contract.EXPECTED_SELECTION
        drifted = tuple(
            (entity_type, entity_id, "0" * 64) if index == 0 else row
            for index, row in enumerate(original)
            for entity_type, entity_id, _ in [row]
        )
        contract.EXPECTED_SELECTION = drifted
        try:
            with self.assertRaises(FullBatchContractError):
                build_full_batch_packet(ROOT, self.artifact)
        finally:
            contract.EXPECTED_SELECTION = original

    def test_removing_a_completed_identity_is_refused(self):
        original = contract.EXPECTED_SELECTION
        contract.EXPECTED_SELECTION = original[:-1]
        try:
            with self.assertRaises(FullBatchContractError):
                build_full_batch_packet(ROOT, self.artifact)
        finally:
            contract.EXPECTED_SELECTION = original


class TipnrFullBatchPayloadBoundaryTests(_PacketMixin):
    """No excluded TIPNR field family may reach any serialized byte."""

    def test_item_text_carries_only_allowlisted_structural_lines(self):
        allowed_prefixes = ("Dataset:", "Revision:", "Entity ID:", "Entity type:", "Form ")
        for item in (self.packet.items[0], self.packet.items[-1],
                     self.packet.items[len(self.packet.items) // 2]):
            for line in item.text.splitlines():
                self.assertTrue(line.startswith(allowed_prefixes), line)

    def test_serialized_packet_contains_no_prohibited_marker(self):
        payload = canonical_json_bytes(full_batch_packet_report(self.packet))
        lowered = payload.decode("utf-8").lower()
        for marker in _PROHIBITED_MARKERS:
            self.assertNotIn(marker.lower(), lowered, marker)

    def test_summary_and_sample_bytes_contain_no_prohibited_marker(self):
        summary = canonical_json_bytes(full_batch_summary(self.packet))
        lowered = summary.decode("utf-8").lower()
        for marker in _PROHIBITED_MARKERS:
            self.assertNotIn(marker.lower(), lowered, marker)

    def test_records_expose_only_the_approved_field_families(self):
        for item in self.packet.items[:50]:
            self.assertEqual(set(item.record), {
                "dataset_id", "artifact_revision", "entity_id", "entity_type",
                "original_language_forms", "record_sha256",
            })
            for form in item.record["original_language_forms"]:
                self.assertEqual(set(form), {
                    "dstrong", "estrong", "source_script_form", "osis_references",
                })


class TipnrFullBatchProjectionParityTests(_PacketMixin):
    """The shared projection must not fork from the Phase 8 pilot contract."""

    def test_projection_reproduces_the_pilot_items_byte_for_byte(self):
        pilot = build_pilot_packet(ROOT, self.artifact)
        proof = build_aaron_projection(ROOT)
        registration = {
            "source_kind": proof.document["source_kind"],
            "citation_mode": proof.document["citation_mode"],
            "url": proof.document["url"],
        }
        source_id = str(proof.source["id"])
        for pilot_item in pilot.items:
            rebuilt = contract.build_item(pilot_item.record, registration, source_id)
            self.assertEqual(rebuilt.document, pilot_item.document)
            self.assertEqual(rebuilt.chunk, pilot_item.chunk)
            self.assertEqual(rebuilt.policy, pilot_item.policy)
            self.assertEqual(rebuilt.text, pilot_item.text)
            self.assertEqual(rebuilt.identity, pilot_item.identity)
            self.assertEqual(rebuilt.rendered_sha256, pilot_item.rendered_sha256)

    def test_every_policy_is_a_current_general_context_row(self):
        for item in self.packet.items:
            self.assertEqual(item.policy["policy_class"], "general_context")
            self.assertTrue(item.policy["is_current"])
            self.assertEqual(item.policy["protected_topic_keys"], [])
            self.assertIsNone(item.policy["issue_key"])
            self.assertIsNone(item.policy["viewpoint_key"])
            self.assertEqual(item.policy["classifier_kind"], "deterministic")
            self.assertIsNone(item.policy["model"])
            self.assertIsNone(item.policy["prompt_fingerprint"])

    def test_documents_are_hidden_source_bound_and_uniquely_identified(self):
        proof = build_aaron_projection(ROOT)
        source_id = str(proof.source["id"])
        document_ids, chunk_ids, file_paths = set(), set(), set()
        for item in self.packet.items:
            self.assertEqual(item.document["source_id"], source_id)
            self.assertEqual(item.document["source_kind"], "biblical_context")
            self.assertEqual(item.chunk["document_id"], item.document["id"])
            self.assertEqual(item.chunk["chunk_index"], 0)
            self.assertEqual(item.policy["chunk_id"], item.chunk["id"])
            document_ids.add(item.document["id"])
            chunk_ids.add(item.chunk["id"])
            file_paths.add(item.document["file_path"])
        self.assertEqual(len(document_ids), REMAINING_COUNT)
        self.assertEqual(len(chunk_ids), REMAINING_COUNT)
        self.assertEqual(len(file_paths), REMAINING_COUNT)

    def test_embedding_model_and_dimensions_are_pinned(self):
        summary = full_batch_summary(self.packet)
        self.assertEqual(summary["embedding_model"], EMBEDDING_MODEL)
        self.assertEqual(summary["embedding_model"], "text-embedding-3-small")
        self.assertEqual(summary["embedding_dimensions"], EMBEDDING_DIMENSIONS)
        self.assertEqual(summary["embedding_dimensions"], 1536)


class TipnrFullBatchCapabilityTests(unittest.TestCase):
    """The contract module must hold no external capability."""

    def test_module_imports_no_network_database_or_model_dependency(self):
        imported = _imported_modules(ROOT / "scripts" / "tipnr_full_batch_contract.py")
        self.assertEqual(imported & _FORBIDDEN_IMPORTS, set())
        self.assertNotIn("dotenv", imported)

    def test_module_defines_no_write_or_apply_entrypoint(self):
        source = (ROOT / "scripts" / "tipnr_full_batch_contract.py").read_text("utf-8")
        for marker in _WRITE_VERB_MARKERS:
            self.assertNotIn(marker, source, marker)


class TipnrFullBatchFixtureTests(_PacketMixin):
    """The compact expected fixture pins the frozen packet forever."""

    def test_expected_fixture_matches_the_rebuilt_summary(self):
        if not FIXTURE.is_file():
            self.skipTest("fixture not generated yet")
        expected = json.loads(FIXTURE.read_text("utf-8"))
        self.assertEqual(expected, full_batch_summary(self.packet))

    def test_fixture_is_canonical_bytes(self):
        if not FIXTURE.is_file():
            self.skipTest("fixture not generated yet")
        expected = json.loads(FIXTURE.read_text("utf-8"))
        self.assertEqual(FIXTURE.read_bytes(), canonical_json_bytes(expected))


# ---------------------------------------------------------------------------
# Packet 2 — preview and preflight
# ---------------------------------------------------------------------------

import preview_tipnr_full_batch as preview_module  # noqa: E402
import preflight_tipnr_full_batch as preflight_module  # noqa: E402
from preflight_tipnr_full_batch import (  # noqa: E402
    CandidateState,
    FullBatchPreflightError,
    _resolve_prefix,
    classify_item,
    preflight_full_batch,
)
from preview_tipnr_full_batch import build_full_batch_preview  # noqa: E402


class _FakeCursor:
    """A cursor that answers only the exact read-only preflight queries."""

    def __init__(self, fixture):
        self.fixture = fixture
        self._rows = []
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        matches = [marker for marker in self.fixture if marker in sql]
        if not matches:
            raise AssertionError(f"unexpected query: {sql[:80]}")
        marker = max(matches, key=len)
        rows = self.fixture[marker]
        self._rows = rows(params) if callable(rows) else list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConnection:
    def __init__(self, fixture):
        self.fixture = fixture
        self.readonly = None
        self.closed = False

    def set_session(self, readonly=None, autocommit=None):
        self.readonly = readonly

    def cursor(self):
        return _FakeCursor(self.fixture)

    def close(self):
        self.closed = True


def _clean_fixture(source_id, alias_id):
    return {
        "transaction_read_only": [("on",)],
        "current_user": [("newwine_readonly_analysis",)],
        "097_table": [(True,)],
        "097_constraints": [(name,) for name in preflight_module._EXPECTED_CONSTRAINTS],
        "097_indexes": [(name,) for name in preflight_module._EXPECTED_INDEXES],
        "097_triggers": [(name,) for name in preflight_module._EXPECTED_TRIGGERS],
        "fullbatch:source": [(source_id, "STEPBible TIPNR", "licensed", "hidden")],
        "fullbatch:alias": [(alias_id, "stepbible tipnr")],
        "fullbatch:documents": [],
        "fullbatch:chunks": [],
        "fullbatch:policies": [],
        "fullbatch:propositions": [],
        "fullbatch:source_totals": [(0,)],
        "fullbatch:source_propositions": [(0,)],
    }


class TipnrFullBatchPreviewTests(_PacketMixin):
    """The preview is byte-stable, complete, and incapable of any effect."""

    def test_preview_declares_every_authorization_false(self):
        report = build_full_batch_preview(ROOT, self.artifact)
        for key in ("database_write_authorized", "external_model_call_authorized",
                    "deployment_authorized", "visibility_change_authorized",
                    "feature_enablement_authorized"):
            self.assertIs(report[key], False, key)

    def test_preview_reports_exact_counts_and_ceilings(self):
        report = build_full_batch_preview(ROOT, self.artifact)
        self.assertEqual(report["counts"], {
            "items": 3939, "documents": 3939, "chunks": 3939,
            "policy_rows": 3939, "embedding_requests": 3939,
            "transactions": 20, "rows_total": 11817,
        })
        packet = report["packet"]
        self.assertEqual(packet["packet_sha256"], self.packet.packet_sha256)
        self.assertEqual(len(packet["batches"]), 20)
        self.assertEqual(packet["maximum_spend_usd"], "0.02441808")
        self.assertEqual(packet["embedding_model"], "text-embedding-3-small")
        self.assertEqual(packet["embedding_dimensions"], 1536)

    def test_preview_discloses_payload_categories_and_exclusions(self):
        report = build_full_batch_preview(ROOT, self.artifact)
        disclosed = report["payload_categories"]["disclosed"]
        self.assertIn("osis_references", disclosed)
        self.assertIn("source_script_form", disclosed)
        excluded = report["payload_categories"]["excluded"]
        self.assertIn("generated_prose", excluded)
        self.assertIn("translated_name_comparisons", excluded)
        self.assertIn("relationships_and_relatives", excluded)

    def test_preview_reconciliation_is_explicitly_zero_effect(self):
        report = build_full_batch_preview(ROOT, self.artifact)
        self.assertEqual(report["reconciliation"], {
            "attempted": 3939, "stored": 0, "errored": 0,
            "skipped": 3939, "reason": "preview_only",
        })

    def test_preview_samples_are_the_ten_frozen_ids(self):
        report = build_full_batch_preview(ROOT, self.artifact)
        self.assertEqual(sorted(report["samples"]), sorted(self.packet.sample_ids))

    def test_preview_is_byte_stable(self):
        first = canonical_json_bytes(build_full_batch_preview(ROOT, self.artifact))
        second = canonical_json_bytes(build_full_batch_preview(ROOT, self.artifact))
        self.assertEqual(first, second)

    def test_preview_module_has_no_external_capability(self):
        path = ROOT / "scripts" / "preview_tipnr_full_batch.py"
        self.assertEqual(_imported_modules(path) & _FORBIDDEN_IMPORTS, set())
        source = path.read_text("utf-8")
        for marker in _WRITE_VERB_MARKERS:
            self.assertNotIn(marker, source, marker)

    def test_preview_registers_only_artifact_and_output_flags(self):
        """No --apply, selection, limit, offset, URL, or entity override exists."""

        path = ROOT / "scripts" / "preview_tipnr_full_batch.py"
        self.assertEqual(_declared_cli_flags(path), {"--artifact", "--output"})

    def test_preview_cli_rejects_selection_and_apply_flags(self):
        for argv in (["--apply"], ["--limit", "5"], ["--offset", "10"],
                     ["--entity", "H0175"], ["--url", "https://example.invalid"]):
            with self.assertRaises(SystemExit):
                preview_module.main([*argv, "--artifact", str(self.artifact)])


class TipnrFullBatchPreflightTests(_PacketMixin):
    """Prefix resumability, strict rejection, and read-only capability."""

    def _source_ids(self):
        return str(self.packet.source["id"]), str(self.packet.alias["id"])

    def _run(self, fixture):
        return preflight_full_batch(
            lambda mode: _FakeConnection(fixture),
            self.packet,
            invariant_checker=lambda: {"biblical_context_answer_enabled": False},
        )

    def test_all_clean_state_reports_first_batch(self):
        report = self._run(_clean_fixture(*self._source_ids()))
        self.assertEqual(report["candidate_state"], "all_clean")
        self.assertEqual(report["next_batch_index"], 1)
        self.assertEqual(report["next_batch_sha256"],
                         self.packet.batches[0].batch_sha256)
        self.assertEqual(report["remaining_ceilings"], {
            "embedding_requests": 3939, "rows": 11817, "transactions": 20,
        })
        self.assertIs(report["database_write_authorized"], False)
        self.assertIs(report["external_model_call_authorized"], False)

    def _completed_fixture(self, count):
        """Simulate an exact-complete prefix of `count` items."""

        source_id, alias_id = self._source_ids()
        fixture = _clean_fixture(source_id, alias_id)
        items = self.packet.items[:count]
        fixture["fullbatch:documents"] = [
            (i.document["id"], i.document["title"], i.document["original_title"],
             i.document["author"], i.document["source_name"], i.document["source_type"],
             i.document["source_kind"], i.document["citation_mode"], i.document["source"],
             i.document["topic_tags"], i.document["bible_references"],
             i.document["file_path"], i.document["is_copyrighted"],
             i.document["full_text"], i.document["source_id"], i.document["url"],
             "2026-09-01T00:00:00+00:00")
            for i in items
        ]
        fixture["fullbatch:chunks"] = [
            (i.chunk["id"], i.chunk["document_id"], i.chunk["content"],
             i.chunk["chunk_index"], i.chunk["bible_references"], 1536)
            for i in items
        ]
        fixture["fullbatch:policies"] = [
            ("00000000-0000-0000-0000-%012d" % n, i.policy["chunk_id"],
             i.policy["policy_class"], i.policy["protected_topic_keys"],
             i.policy["issue_key"], i.policy["viewpoint_key"],
             i.policy["classifier_kind"], i.policy["rule_version"],
             i.policy["model"], i.policy["prompt_fingerprint"],
             i.policy["reason_codes"], i.policy["is_current"])
            for n, i in enumerate(items)
        ]
        fixture["fullbatch:source_totals"] = [(count,)]
        return fixture

    def test_whole_batch_prefix_reports_the_next_batch(self):
        report = self._run(self._completed_fixture(400))
        self.assertEqual(report["candidate_state"], "exact_complete_prefix")
        self.assertEqual(report["counts"]["exact_complete"], 400)
        self.assertEqual(report["counts"]["completed_batches"], 2)
        self.assertEqual(report["next_batch_index"], 3)
        self.assertEqual(report["remaining_ceilings"], {
            "embedding_requests": 3539, "rows": 10617, "transactions": 18,
        })

    def test_all_exact_complete_reports_no_next_batch(self):
        report = self._run(self._completed_fixture(3939))
        self.assertEqual(report["candidate_state"], "all_exact_complete")
        self.assertIsNone(report["next_batch_index"])
        self.assertIsNone(report["next_batch_sha256"])
        self.assertEqual(report["remaining_ceilings"], {
            "embedding_requests": 0, "rows": 0, "transactions": 0,
        })

    def test_partial_batch_is_rejected(self):
        with self.assertRaises(FullBatchPreflightError) as caught:
            self._run(self._completed_fixture(250))
        self.assertIn("partial_batch", str(caught.exception))

    def test_partial_item_is_rejected(self):
        fixture = self._completed_fixture(200)
        fixture["fullbatch:policies"] = fixture["fullbatch:policies"][:-1]
        with self.assertRaises(FullBatchPreflightError) as caught:
            self._run(fixture)
        self.assertIn("policy_cardinality", str(caught.exception))

    def test_unstamped_ingest_is_rejected(self):
        fixture = self._completed_fixture(200)
        fixture["fullbatch:documents"] = [
            row[:-1] + (None,) for row in fixture["fullbatch:documents"]
        ]
        with self.assertRaises(FullBatchPreflightError) as caught:
            self._run(fixture)
        self.assertIn("ingest_not_stamped", str(caught.exception))

    def test_projection_drift_is_rejected(self):
        fixture = self._completed_fixture(200)
        first = list(fixture["fullbatch:documents"][0])
        first[1] = "tampered title"
        fixture["fullbatch:documents"][0] = tuple(first)
        with self.assertRaises(FullBatchPreflightError) as caught:
            self._run(fixture)
        self.assertIn("document_projection_drift", str(caught.exception))

    def test_proposition_presence_is_rejected(self):
        fixture = self._completed_fixture(200)
        fixture["fullbatch:source_propositions"] = [(1,)]
        with self.assertRaises(FullBatchPreflightError) as caught:
            self._run(fixture)
        self.assertIn("propositions_present", str(caught.exception))

    def test_visibility_drift_is_rejected(self):
        source_id, alias_id = self._source_ids()
        fixture = _clean_fixture(source_id, alias_id)
        fixture["fullbatch:source"] = [
            (source_id, "STEPBible TIPNR", "licensed", "shown")
        ]
        with self.assertRaises(FullBatchPreflightError) as caught:
            self._run(fixture)
        self.assertIn("visibility_drift", str(caught.exception))

    def test_role_drift_is_rejected(self):
        source_id, alias_id = self._source_ids()
        fixture = _clean_fixture(source_id, alias_id)
        fixture["current_user"] = [("postgres",)]
        with self.assertRaises(FullBatchPreflightError) as caught:
            self._run(fixture)
        self.assertIn("readonly_role_mismatch", str(caught.exception))

    def test_writable_session_is_rejected(self):
        source_id, alias_id = self._source_ids()
        fixture = _clean_fixture(source_id, alias_id)
        fixture["transaction_read_only"] = [("off",)]
        with self.assertRaises(FullBatchPreflightError) as caught:
            self._run(fixture)
        self.assertIn("not_readonly", str(caught.exception))

    def test_migration_drift_is_rejected(self):
        source_id, alias_id = self._source_ids()
        for key, reason in (("097_triggers", "trigger_drift"),
                            ("097_indexes", "index_drift"),
                            ("097_constraints", "constraint_drift")):
            fixture = _clean_fixture(source_id, alias_id)
            fixture[key] = []
            with self.assertRaises(FullBatchPreflightError) as caught:
                self._run(fixture)
            self.assertIn(reason, str(caught.exception), key)

    def test_disabled_row_level_security_is_rejected(self):
        source_id, alias_id = self._source_ids()
        fixture = _clean_fixture(source_id, alias_id)
        fixture["097_table"] = [(False,)]
        with self.assertRaises(FullBatchPreflightError) as caught:
            self._run(fixture)
        self.assertIn("rls_disabled", str(caught.exception))

    def test_out_of_order_completion_is_rejected(self):
        states = [CandidateState("a", "clean"), CandidateState("b", "exact_complete")]
        states += [CandidateState(str(n), "clean") for n in range(3937)]
        with self.assertRaises(FullBatchPreflightError) as caught:
            _resolve_prefix(self.packet, states)
        self.assertIn("out_of_order", str(caught.exception))

    def test_preflight_loads_no_write_or_embedding_dependency(self):
        path = ROOT / "scripts" / "preflight_tipnr_full_batch.py"
        imported = _imported_modules(path)
        self.assertNotIn("openai", imported)
        source = path.read_text("utf-8")
        for marker in (*_WRITE_VERB_MARKERS, "SUPABASE_DB_URL"):
            self.assertNotIn(marker, source, marker)
        self.assertIn("READONLY_ANALYSIS_DB_URL", source)
        self.assertEqual(_declared_cli_flags(path),
                         {"--artifact", "--verify", "--output"})

    def test_preflight_requires_the_verify_flag(self):
        with self.assertRaises(SystemExit):
            preflight_module.main(["--artifact", str(self.artifact)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
