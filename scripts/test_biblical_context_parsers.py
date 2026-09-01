#!/usr/bin/env python3
"""Deterministic tests for Phase 2 biblical-context tooling.

No network, database, model, embedding, retrieval, or answer-path access.
"""

from __future__ import annotations

import copy
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
