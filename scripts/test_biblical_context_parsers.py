#!/usr/bin/env python3
"""Deterministic tests for Phase 2 biblical-context tooling.

No network, database, model, embedding, retrieval, or answer-path access.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


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
    TipnrItemError,
    TipnrSchemaError,
    parse_tipnr_entity,
    parse_tipnr_file,
)


FIXTURE_DIR = SCRIPTS / "fixtures" / "biblical_context"
TIPNR_FIXTURE = FIXTURE_DIR / "tipnr_minimal.txt"
TIPNR_META = FIXTURE_DIR / "tipnr_minimal.meta.json"


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
