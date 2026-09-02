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
        source = (ROOT / "scripts" / "tipnr_full_batch_contract.py").read_text("utf-8")
        for forbidden in ("psycopg2", "openai", "requests", "httpx", "urllib",
                          "socket", "boto3", "dotenv"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_module_defines_no_write_or_apply_entrypoint(self):
        source = (ROOT / "scripts" / "tipnr_full_batch_contract.py").read_text("utf-8")
        for forbidden in ("INSERT", "UPDATE ", "DELETE", "--apply", "commit()"):
            self.assertNotIn(forbidden, source, forbidden)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
