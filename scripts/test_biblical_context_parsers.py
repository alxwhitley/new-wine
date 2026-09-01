#!/usr/bin/env python3
"""Deterministic tests for Phase 2 biblical-context tooling.

No network, database, model, embedding, retrieval, or answer-path access.
"""

from __future__ import annotations

import copy
import ast
import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
MANIFEST_DIR = ROOT / "docs" / "ingestion" / "source_manifests"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from biblical_context_tooling import (  # noqa: E402
    ContractError,
    canonical_json_bytes,
    canonical_sha256,
    compile_ingestion_policies,
    compile_registration_preview,
    load_approved_manifests,
)
from parse_tipnr_context import (  # noqa: E402
    TIPNR_ARTIFACT_BYTES,
    TIPNR_ARTIFACT_SHA256,
    TipnrItemError,
    TipnrRecordOutcome,
    TipnrSchemaError,
    TipnrStructuralRecord,
    classify_tipnr_record,
    classify_tipnr_text,
    parse_tipnr_entity,
    parse_tipnr_file,
    scan_tipnr_records,
    split_tipnr_records,
    verify_tipnr_artifact,
)
from parse_openbible_context import (  # noqa: E402
    OpenBibleItemError,
    OpenBibleSchemaError,
    parse_openbible_file,
    parse_openbible_place,
)
from preview_biblical_context_tooling import (  # noqa: E402
    PreviewCollisionError,
    PreviewPathError,
    build_fixture_preview,
    main as preview_main,
    write_new_preview,
)


FIXTURE_DIR = SCRIPTS / "fixtures" / "biblical_context"
TIPNR_FIXTURE = FIXTURE_DIR / "tipnr_minimal.txt"
TIPNR_META = FIXTURE_DIR / "tipnr_minimal.meta.json"
OPENBIBLE_FIXTURE = FIXTURE_DIR / "openbible_ancient_minimal.jsonl"
OPENBIBLE_META = FIXTURE_DIR / "openbible_ancient_minimal.meta.json"


class ManifestCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifests = load_approved_manifests(MANIFEST_DIR)

    def test_compiles_exact_five_hidden_registration_rows(self) -> None:
        rows = compile_registration_preview(self.manifests)

        self.assertEqual(
            [row["slug"] for row in rows],
            [
                "openbible-bible-geocoding",
                "openbible-cross-references",
                "stepbible-tipnr",
                "tyndale-open-bible-dictionary",
                "tyndale-open-study-notes",
            ],
        )
        self.assertTrue(all(row["visibility"] == "hidden" for row in rows))
        self.assertTrue(all("id" not in row for row in rows))
        self.assertEqual(
            {
                row["slug"]
                for row in rows
                if row["ingestion_policy"] == "prohibited_in_v1"
            },
            {
                "openbible-cross-references",
                "tyndale-open-bible-dictionary",
                "tyndale-open-study-notes",
            },
        )

    def test_compiles_only_two_eligible_ingestion_policies(self) -> None:
        policies = compile_ingestion_policies(self.manifests)

        self.assertEqual(
            set(policies),
            {
                "stepbible_tipnr",
                "openbible_structured_data:bible_geocoding",
                "openbible_structured_data:cross_references",
                "tyndale_open_resources:open_bible_dictionary",
                "tyndale_open_resources:open_study_notes",
            },
        )
        self.assertEqual(
            {
                key
                for key, policy in policies.items()
                if policy["ingestion_policy"] == "eligible_for_phase_2_preview"
            },
            {
                "stepbible_tipnr",
                "openbible_structured_data:bible_geocoding",
            },
        )

    def test_rejects_unapproved_or_write_authorizing_manifests(self) -> None:
        unapproved = copy.deepcopy(self.manifests)
        unapproved["stepbible_tipnr"]["decision"]["status"] = "pending"
        with self.assertRaisesRegex(ContractError, "decision_not_approved"):
            compile_registration_preview(unapproved)

        write_authorized = copy.deepcopy(self.manifests)
        write_authorized["stepbible_tipnr"]["authorization"][
            "database_write_authorized"
        ] = True
        with self.assertRaisesRegex(ContractError, "authorization_boundary_changed"):
            compile_registration_preview(write_authorized)

    def test_rejects_schema_visibility_identity_and_dataset_drift(self) -> None:
        schema_drift = copy.deepcopy(self.manifests)
        schema_drift["stepbible_tipnr"]["schema_version"] = 2
        with self.assertRaisesRegex(ContractError, "unsupported_schema_version"):
            compile_registration_preview(schema_drift)

        visible = copy.deepcopy(self.manifests)
        visible["stepbible_tipnr"]["proposed_registration"]["source_rows"][0][
            "visibility"
        ] = "shown"
        with self.assertRaisesRegex(ContractError, "registration_not_hidden"):
            compile_registration_preview(visible)

        duplicate_slug = copy.deepcopy(self.manifests)
        duplicate_slug["tyndale_open_resources"]["proposed_registration"][
            "source_rows"
        ][0]["slug"] = "stepbible-tipnr"
        with self.assertRaisesRegex(ContractError, "duplicate_registration_slug"):
            compile_registration_preview(duplicate_slug)

        duplicate_alias = copy.deepcopy(self.manifests)
        duplicate_alias["openbible_structured_data"]["proposed_registration"][
            "source_rows"
        ][0]["aliases"] = ["STEPBible   TIPNR"]
        with self.assertRaisesRegex(ContractError, "duplicate_registration_alias"):
            compile_registration_preview(duplicate_alias)

        unknown_dataset = copy.deepcopy(self.manifests)
        unknown_dataset["unknown_dataset"] = unknown_dataset.pop("stepbible_data")
        unknown_dataset["unknown_dataset"]["dataset_id"] = "unknown_dataset"
        with self.assertRaisesRegex(ContractError, "unsupported_dataset"):
            compile_registration_preview(unknown_dataset)

    def test_canonical_json_and_checksum_are_byte_stable(self) -> None:
        value = {"beta": [2, 1], "alpha": "\N{GREEK SMALL LETTER ALPHA}"}

        self.assertEqual(
            canonical_json_bytes(value),
            b'{"alpha":"\xce\xb1","beta":[2,1]}\n',
        )
        self.assertEqual(canonical_sha256(value), canonical_sha256(value))
        self.assertRegex(canonical_sha256(value), r"^[0-9a-f]{64}$")


class TipnrParserTests(unittest.TestCase):
    REVISION = "02843f07cbb5009e00999a7c0efead6430dbb6e7"

    def test_fixture_identity_matches_pinned_metadata(self) -> None:
        metadata = json.loads(TIPNR_META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["revision"], self.REVISION)
        self.assertEqual(metadata["fixture_bytes"], TIPNR_FIXTURE.stat().st_size)
        self.assertEqual(
            metadata["fixture_sha256"],
            __import__("hashlib").sha256(TIPNR_FIXTURE.read_bytes()).hexdigest(),
        )
        self.assertEqual(metadata["selected_entity_ids"], ["H0175", "H0071", "H0011"])

    def test_single_person_item_projects_only_approved_fields(self) -> None:
        lines = TIPNR_FIXTURE.read_text(encoding="utf-8").splitlines()
        record = parse_tipnr_entity(lines[:9], artifact_revision=self.REVISION)

        expected = {
            "dataset_id": "stepbible_tipnr",
            "artifact_revision": self.REVISION,
            "entity_id": "H0175",
            "entity_type": "person",
            "original_language_forms": [
                {
                    "dstrong": "H0175",
                    "estrong": "H0175",
                    "source_script_form": "אַהֲרֹן",
                    "osis_references": ["Exo.4.14", "Exo.4.27"],
                },
                {
                    "dstrong": "G0002",
                    "estrong": "G0002",
                    "source_script_form": "Ἀαρών",
                    "osis_references": ["Luk.1.5", "Act.7.40"],
                },
            ],
        }
        expected["record_sha256"] = canonical_sha256(expected)
        self.assertEqual(record, expected)
        serialized = canonical_json_bytes(record).decode("utf-8")
        for excluded in ("High Priest", "Moses' brother", "STEP link", "Total"):
            self.assertNotIn(excluded, serialized)

    def test_file_previews_person_and_place_but_skips_other(self) -> None:
        result = parse_tipnr_file(TIPNR_FIXTURE, artifact_revision=self.REVISION)

        self.assertEqual(
            result["counts"],
            {
                "attempted": 3,
                "previewed": 2,
                "malformed": 0,
                "duplicate": 0,
                "skipped": 1,
                "prohibited": 0,
            },
        )
        self.assertEqual(
            [(row["entity_id"], row["entity_type"]) for row in result["records"]],
            [("H0175", "person"), ("H0071", "place")],
        )
        self.assertEqual(result["reason_counts"], {"not_v1_entity_type": 1})
        self.assertEqual(result["checksum"], canonical_sha256(result["records"]))
        self.assertEqual(
            canonical_json_bytes(result),
            canonical_json_bytes(
                parse_tipnr_file(TIPNR_FIXTURE, artifact_revision=self.REVISION)
            ),
        )

    def test_place_preserves_both_source_forms_in_order(self) -> None:
        lines = TIPNR_FIXTURE.read_text(encoding="utf-8").splitlines()
        place = parse_tipnr_entity(lines[9:17], artifact_revision=self.REVISION)

        self.assertEqual(place["entity_id"], "H0071")
        self.assertEqual(
            [form["dstrong"] for form in place["original_language_forms"]],
            ["H0071", "H0549H"],
        )

    def test_duplicate_entities_are_refused_not_merged(self) -> None:
        text = TIPNR_FIXTURE.read_text(encoding="utf-8")
        first_record = "\n".join(text.splitlines()[:9])
        duplicate_path = Path(self.enterContext(__import__("tempfile").TemporaryDirectory())) / "duplicate.txt"
        duplicate_path.write_text(first_record + "\n" + first_record + "\n", encoding="utf-8")

        result = parse_tipnr_file(duplicate_path, artifact_revision=self.REVISION)

        self.assertEqual(result["counts"]["attempted"], 2)
        self.assertEqual(result["counts"]["previewed"], 1)
        self.assertEqual(result["counts"]["duplicate"], 1)
        self.assertEqual(result["reason_counts"], {"duplicate_entity_id": 1})

    def test_schema_and_item_mutations_fail_closed(self) -> None:
        lines = TIPNR_FIXTURE.read_text(encoding="utf-8").splitlines()[:9]

        with self.assertRaisesRegex(TipnrSchemaError, "unknown_entity_marker"):
            parse_tipnr_entity(
                ["$========== DOCTRINE", *lines[1:]],
                artifact_revision=self.REVISION,
            )
        with self.assertRaisesRegex(TipnrSchemaError, "unknown_directive"):
            parse_tipnr_entity(
                [*lines, "@Doctrine= forbidden"],
                artifact_revision=self.REVISION,
            )
        with self.assertRaisesRegex(TipnrItemError, "abbreviated_reference"):
            parse_tipnr_entity(
                [line.replace("Exo.4.14; Exo.4.27", "Exo.4.14ff") for line in lines],
                artifact_revision=self.REVISION,
            )
        with self.assertRaisesRegex(TipnrItemError, "form_identity_invalid"):
            parse_tipnr_entity(
                [line.replace("H0175«H0175=", "H0175=") for line in lines],
                artifact_revision=self.REVISION,
            )
        with self.assertRaisesRegex(TipnrSchemaError, "row_shape_changed"):
            parse_tipnr_entity(
                [lines[0], "too\tfew", lines[2]],
                artifact_revision=self.REVISION,
            )


class TipnrFullArtifactContractTests(unittest.TestCase):
    def test_artifact_verifier_accepts_only_exact_pinned_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tipnr.txt"
            path.write_bytes(b"pinned")
            with (
                mock.patch("parse_tipnr_context.TIPNR_ARTIFACT_BYTES", 6),
                mock.patch(
                    "parse_tipnr_context.TIPNR_ARTIFACT_SHA256",
                    hashlib.sha256(b"pinned").hexdigest(),
                ),
            ):
                self.assertEqual(verify_tipnr_artifact(path), b"pinned")
                path.write_bytes(b"mutate")
                with self.assertRaisesRegex(
                    TipnrSchemaError, "artifact_sha256_mismatch"
                ):
                    verify_tipnr_artifact(path)

    def test_artifact_verifier_checks_size_before_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tipnr.txt"
            path.write_bytes(b"short")
            with self.assertRaisesRegex(
                TipnrSchemaError, "artifact_size_mismatch"
            ):
                verify_tipnr_artifact(path)

        self.assertEqual(TIPNR_ARTIFACT_BYTES, 7_916_469)
        self.assertEqual(
            TIPNR_ARTIFACT_SHA256,
            "69f69d80d8a329576915a397d815bd6ff1849d8954d071c57b0ac4453aee180e",
        )

    def test_scanner_preserves_every_marker_record_in_source_order(self) -> None:
        text = "\n".join(
            (
                "$==========PERSON(s)",
                "header",
                "",
                "$========== PERSON(s)",
                "\t".join(("Name=H0001", "x", "x", "x", "x", "x", "x", "x", "x")),
                "– Named\t\tH0001«H0001=א\t\tGen.1.1",
            )
        )

        records = scan_tipnr_records(text)

        self.assertEqual([row.ordinal for row in records], [1, 2])
        self.assertEqual(records[0].marker_shape, "person_no_space")
        self.assertEqual(records[0].marker_class, "documentation")
        self.assertEqual(records[1].marker_shape, "person_spaced")
        self.assertEqual(records[1].marker_class, "person")
        self.assertEqual(records[1].form_shapes, (("Named", 5),))

    def test_scanner_rejects_unknown_marker_and_directive(self) -> None:
        with self.assertRaisesRegex(TipnrSchemaError, "unknown_entity_marker"):
            scan_tipnr_records("$========== DOCTRINE\nrow")
        with self.assertRaisesRegex(TipnrSchemaError, "unknown_directive"):
            scan_tipnr_records(
                "\n".join(
                    (
                        "$========== PERSON(s)",
                        "Name=H0001\t\t\t\t\t\t\t\t",
                        "@Doctrine=value",
                    )
                )
            )

    def test_scanner_rejects_unknown_entity_shapes(self) -> None:
        marker = "$========== PERSON(s)"
        primary = "\t".join(
            ("Name=H0001", "x", "x", "x", "x", "x", "x", "x", "x")
        )
        with self.assertRaisesRegex(TipnrSchemaError, "unknown_significance"):
            scan_tipnr_records(
                "\n".join(
                    (
                        marker,
                        primary,
                        "– Relationship\t\tH0001«H0001=א\t\tGen.1.1",
                    )
                )
            )
        with self.assertRaisesRegex(TipnrSchemaError, "unknown_line_shape"):
            scan_tipnr_records("\n".join((marker, primary, "Relationship")))
        with self.assertRaisesRegex(TipnrSchemaError, "row_shape_changed"):
            scan_tipnr_records("\n".join((marker, "Name=H0001\ttoo-few")))

    def test_documentation_markers_are_bound_to_first_three_ordinals(self) -> None:
        with self.assertRaisesRegex(
            TipnrSchemaError, "documentation_record_sequence_changed"
        ):
            scan_tipnr_records("$==========PLACE\nheader")


class TipnrRecordOutcomeTests(unittest.TestCase):
    REVISION = "02843f07cbb5009e00999a7c0efead6430dbb6e7"

    @staticmethod
    def _primary(identity: str, width: int) -> str:
        return "\t".join((identity, *("x" for _ in range(width - 1))))

    def _classify(self, text: str) -> TipnrRecordOutcome:
        lines = split_tipnr_records(text)[0]
        profile = scan_tipnr_records(text)[0]
        return classify_tipnr_record(
            lines,
            profile,
            artifact_revision=self.REVISION,
        )

    def test_documentation_and_noneligible_markers_are_explicit(self) -> None:
        documentation = self._classify("$==========PERSON(s)\nheader")
        combined = self._classify(
            "\n".join(
                (
                    "$========== PERSON+PLACE",
                    self._primary("Name=H0001", 8),
                )
            )
        )
        other = self._classify(
            "\n".join(
                (
                    "$========== OTHER",
                    self._primary("Name=H0002", 9),
                )
            )
        )

        self.assertEqual(
            (documentation.status, documentation.reason),
            ("skipped", "source_documentation"),
        )
        self.assertEqual(
            (combined.status, combined.reason),
            ("prohibited", "combined_entity_type"),
        )
        self.assertEqual(
            (other.status, other.reason),
            ("skipped", "not_v1_entity_type"),
        )
        self.assertIsNone(combined.projection)
        self.assertIsNone(other.projection)

    def test_group_form_projects_only_existing_allowlisted_fields(self) -> None:
        outcome = self._classify(
            "\n".join(
                (
                    "$========== PERSON(s)",
                    self._primary("Name=H0001", 9),
                    "– Group\tignored\tH0001«H0001=א\tignored\tGen.1.1",
                    "– Total\tignored\tignored\tignored\tignored",
                    "@Ambiguity=excluded relationship prose",
                )
            )
        )

        self.assertEqual(outcome.status, "eligible")
        self.assertEqual(outcome.reason, "allowlisted_projection")
        self.assertEqual(
            set(outcome.projection or {}),
            {
                "dataset_id",
                "artifact_revision",
                "entity_id",
                "entity_type",
                "original_language_forms",
                "record_sha256",
            },
        )
        serialized = canonical_json_bytes(asdict(outcome)).decode("utf-8")
        self.assertNotIn("excluded relationship prose", serialized)
        self.assertNotIn("ignored", serialized)

    def test_real_place_width_projects_without_fixture_widening(self) -> None:
        outcome = self._classify(
            "\n".join(
                (
                    "$========== PLACE",
                    self._primary("Place=H0002", 8),
                    "– Named\tignored\tH0002«H0002=ב\tignored\tExo.1.1",
                    "– Total\tignored\tignored\tignored\tignored",
                )
            )
        )

        self.assertEqual(outcome.status, "eligible")
        self.assertEqual((outcome.projection or {})["entity_type"], "place")
        self.assertEqual((outcome.projection or {})["entity_id"], "H0002")

    def test_duplicate_outcomes_are_symmetric_and_never_merged(self) -> None:
        record = "\n".join(
            (
                "$========== PERSON(s)",
                self._primary("Name=H0001", 9),
                "– Named\tignored\tH0001«H0001=א\tignored\tGen.1.1",
                "– Total\tignored\tignored\tignored\tignored",
            )
        )

        outcomes = classify_tipnr_text(
            f"{record}\n{record}\n", artifact_revision=self.REVISION
        )

        self.assertEqual([row.status for row in outcomes], ["duplicate", "duplicate"])
        self.assertEqual(
            [row.reason for row in outcomes],
            ["duplicate_entity_id", "duplicate_entity_id"],
        )
        self.assertTrue(all(row.projection is None for row in outcomes))

    def test_known_width_drift_is_malformed_not_a_partial_projection(self) -> None:
        lines = (
            "$========== PLACE",
            self._primary("Place=H0002", 8),
            "– Named\tignored\tH0002«H0002=ב\tignored\tExo.1.1\textra",
        )
        profile = TipnrStructuralRecord(
            ordinal=3624,
            marker_shape="place_spaced",
            marker_class="place",
            primary_width=8,
            form_shapes=(("Named", 6),),
            directive_keys=(),
            line_shape_codes=(),
        )

        outcome = classify_tipnr_record(
            lines,
            profile,
            artifact_revision=self.REVISION,
        )

        self.assertEqual((outcome.status, outcome.reason),
                         ("malformed", "row_shape_changed"))
        self.assertIsNone(outcome.projection)


class OpenBibleParserTests(unittest.TestCase):
    REVISION = "7eb18a5ee62f27b9b93bd6689ea272d76dd23b8f"

    def setUp(self) -> None:
        self.values = [
            json.loads(line)
            for line in OPENBIBLE_FIXTURE.read_text(encoding="utf-8").splitlines()
        ]

    def test_fixture_identity_matches_pinned_metadata(self) -> None:
        metadata = json.loads(OPENBIBLE_META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["revision"], self.REVISION)
        self.assertEqual(metadata["fixture_bytes"], OPENBIBLE_FIXTURE.stat().st_size)
        self.assertEqual(
            metadata["fixture_sha256"],
            __import__("hashlib").sha256(OPENBIBLE_FIXTURE.read_bytes()).hexdigest(),
        )
        self.assertEqual(metadata["selected_place_ids"], ["aea17b7", "ab9a5ec"])

    def test_single_place_projects_only_approved_fields(self) -> None:
        self.assertNotIn(
            "modern_id", self.values[0]["modern_associations"]["m39ac0b"]
        )
        record = parse_openbible_place(
            self.values[0], artifact_revision=self.REVISION
        )
        expected = {
            "dataset_id": "openbible_structured_data",
            "artifact_revision": self.REVISION,
            "place_id": "aea17b7",
            "place_name": "Abana",
            "place_types": ["river"],
            "osis_references": ["2Kgs.5.12"],
            "candidate_identifications": [
                {
                    "modern_id": "m39ac0b",
                    "name": "Barada River",
                    "confidence_score": 1000,
                }
            ],
        }
        expected["record_sha256"] = canonical_sha256(expected)
        self.assertEqual(record, expected)

        serialized = canonical_json_bytes(record).decode("utf-8")
        for excluded in (
            "geometry",
            "translation",
            "linked_data",
            "media",
            "readable",
            "url_slug",
            "identification_ids",
            "extra",
        ):
            self.assertNotIn(excluded, serialized)

    def test_association_free_place_is_preserved_without_invention(self) -> None:
        record = parse_openbible_place(
            self.values[1], artifact_revision=self.REVISION
        )

        self.assertEqual(record["place_id"], "ab9a5ec")
        self.assertEqual(record["place_name"], "Azazel")
        self.assertEqual(record["candidate_identifications"], [])
        self.assertEqual(
            record["osis_references"],
            ["Lev.16.8", "Lev.16.10", "Lev.16.26"],
        )

    def test_file_reconciles_two_real_records_deterministically(self) -> None:
        result = parse_openbible_file(
            OPENBIBLE_FIXTURE, artifact_revision=self.REVISION
        )

        self.assertEqual(
            result["counts"],
            {
                "attempted": 2,
                "previewed": 2,
                "malformed": 0,
                "duplicate": 0,
                "skipped": 0,
                "prohibited": 0,
            },
        )
        self.assertEqual(result["reason_counts"], {})
        self.assertEqual(result["checksum"], canonical_sha256(result["records"]))
        self.assertEqual(
            canonical_json_bytes(result),
            canonical_json_bytes(
                parse_openbible_file(
                    OPENBIBLE_FIXTURE, artifact_revision=self.REVISION
                )
            ),
        )

    def test_duplicate_place_ids_are_refused_not_merged(self) -> None:
        duplicate_path = Path(
            self.enterContext(__import__("tempfile").TemporaryDirectory())
        ) / "duplicate.jsonl"
        first = json.dumps(self.values[0], ensure_ascii=False, separators=(",", ":"))
        duplicate_path.write_text(first + "\n" + first + "\n", encoding="utf-8")

        result = parse_openbible_file(duplicate_path, artifact_revision=self.REVISION)

        self.assertEqual(result["counts"]["attempted"], 2)
        self.assertEqual(result["counts"]["previewed"], 1)
        self.assertEqual(result["counts"]["duplicate"], 1)
        self.assertEqual(result["reason_counts"], {"duplicate_place_id": 1})

    def test_root_and_nested_schema_drift_fails_closed(self) -> None:
        new_root = copy.deepcopy(self.values[0])
        new_root["doctrinal_summary"] = "must not pass through"
        with self.assertRaisesRegex(OpenBibleSchemaError, "unknown_root_field"):
            parse_openbible_place(new_root, artifact_revision=self.REVISION)

        new_verse_field = copy.deepcopy(self.values[0])
        new_verse_field["verses"][0]["doctrine"] = "must not pass through"
        with self.assertRaisesRegex(OpenBibleSchemaError, "unknown_verse_field"):
            parse_openbible_place(new_verse_field, artifact_revision=self.REVISION)

        new_association_field = copy.deepcopy(self.values[0])
        new_association_field["modern_associations"]["m39ac0b"][
            "description"
        ] = "must not pass through"
        with self.assertRaisesRegex(OpenBibleSchemaError, "unknown_association_field"):
            parse_openbible_place(
                new_association_field, artifact_revision=self.REVISION
            )

    def test_invalid_required_values_are_item_errors(self) -> None:
        missing_id = copy.deepcopy(self.values[0])
        del missing_id["id"]
        with self.assertRaisesRegex(OpenBibleItemError, "place_id_invalid"):
            parse_openbible_place(missing_id, artifact_revision=self.REVISION)

        boolean_score = copy.deepcopy(self.values[0])
        boolean_score["modern_associations"]["m39ac0b"]["score"] = True
        with self.assertRaisesRegex(OpenBibleItemError, "confidence_score_invalid"):
            parse_openbible_place(boolean_score, artifact_revision=self.REVISION)


class PreviewCliTests(unittest.TestCase):
    def test_fixture_preview_has_exact_reconciliation(self) -> None:
        preview = build_fixture_preview(ROOT)

        self.assertEqual(
            preview["schema_version"], "biblical_context_phase2_preview.v1"
        )
        self.assertIs(preview["database_write_authorized"], False)
        self.assertEqual(len(preview["registration_rows"]), 5)
        self.assertTrue(
            all(row["visibility"] == "hidden" for row in preview["registration_rows"])
        )
        self.assertEqual(
            preview["single_item_verification"],
            {"stepbible_tipnr": "passed", "openbible_geocoding": "passed"},
        )
        self.assertEqual(
            preview["datasets"]["stepbible_tipnr"]["counts"],
            {
                "attempted": 3,
                "previewed": 2,
                "malformed": 0,
                "duplicate": 0,
                "skipped": 1,
                "prohibited": 0,
            },
        )
        self.assertEqual(
            preview["datasets"]["openbible_structured_data:bible_geocoding"][
                "counts"
            ],
            {
                "attempted": 2,
                "previewed": 2,
                "malformed": 0,
                "duplicate": 0,
                "skipped": 0,
                "prohibited": 0,
            },
        )
        for dataset_key in (
            "openbible_structured_data:cross_references",
            "tyndale_open_resources:open_bible_dictionary",
            "tyndale_open_resources:open_study_notes",
        ):
            self.assertEqual(
                preview["datasets"][dataset_key]["counts"],
                {
                    "attempted": 1,
                    "previewed": 0,
                    "malformed": 0,
                    "duplicate": 0,
                    "skipped": 0,
                    "prohibited": 1,
                },
            )
        self.assertEqual(
            preview["totals"],
            {
                "attempted": 8,
                "previewed": 4,
                "malformed": 0,
                "duplicate": 0,
                "skipped": 1,
                "prohibited": 3,
            },
        )
        checksum_input = dict(preview)
        payload_sha256 = checksum_input.pop("payload_sha256")
        self.assertEqual(payload_sha256, canonical_sha256(checksum_input))

    def test_fixture_preview_is_byte_identical_across_runs(self) -> None:
        first = canonical_json_bytes(build_fixture_preview(ROOT))
        second = canonical_json_bytes(build_fixture_preview(ROOT))

        self.assertEqual(first, second)

    def test_local_preview_publication_is_create_new_and_collision_safe(self) -> None:
        local_test_dir = Path(
            self.enterContext(
                __import__("tempfile").TemporaryDirectory(dir=ROOT / "local")
            )
        )
        target = local_test_dir / "preview.json"
        payload = b'{"safe":true}\n'

        write_new_preview(target, payload)
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        write_new_preview(target, payload)
        with self.assertRaisesRegex(PreviewCollisionError, "different_bytes"):
            write_new_preview(target, b'{"safe":false}\n')

        symlink = local_test_dir / "symlink.json"
        symlink.symlink_to(target)
        with self.assertRaisesRegex(PreviewCollisionError, "not_regular"):
            write_new_preview(symlink, payload)

    def test_preview_refuses_output_outside_repository_local_directory(self) -> None:
        outside = Path(
            self.enterContext(__import__("tempfile").TemporaryDirectory())
        ) / "preview.json"

        with self.assertRaisesRegex(PreviewPathError, "outside_local"):
            write_new_preview(outside, b"{}\n")

    def test_cli_has_no_apply_or_discovery_mode(self) -> None:
        with self.assertRaises(SystemExit) as apply_exit:
            preview_main(["--fixtures", "--apply"])
        self.assertEqual(apply_exit.exception.code, 2)

        with self.assertRaises(SystemExit) as url_exit:
            preview_main(["--fixtures", "--url", "https://example.com"])
        self.assertEqual(url_exit.exception.code, 2)

    def test_phase2_modules_have_no_forbidden_imports_or_calls(self) -> None:
        paths = (
            SCRIPTS / "biblical_context_tooling.py",
            SCRIPTS / "parse_tipnr_context.py",
            SCRIPTS / "parse_openbible_context.py",
            SCRIPTS / "preview_biblical_context_tooling.py",
        )
        forbidden = {
            "supabase",
            "psycopg",
            "shared_ingest",
            "embedding",
            "proposition",
            "retrieval",
            "producer",
            "answer_toolbox",
        }

        found: list[str] = []
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.extend(alias.name.lower() for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    found.append((node.module or "").lower())
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        found.append(node.func.id.lower())
                    elif isinstance(node.func, ast.Attribute):
                        found.append(node.func.attr.lower())

        violations = sorted(
            value
            for value in found
            if any(blocked in value for blocked in forbidden)
        )
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
