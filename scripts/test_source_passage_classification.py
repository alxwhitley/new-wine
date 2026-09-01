#!/usr/bin/env python3
"""Phase 3 deterministic passage-policy tests.

No network, model, database connection, or filesystem write is permitted.

Run: python3.12 scripts/test_source_passage_classification.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from classify_source_passages import (  # noqa: E402
    ClassificationRefused,
    classify_source_field,
    is_answer_eligible,
)
from apply_migration_097 import (  # noqa: E402
    MigrationValidationError,
    database_environment,
    validate_migration,
)


class DeterministicClassificationTests(unittest.TestCase):
    def test_every_approved_structural_field_maps_to_general_context(self) -> None:
        approved = {
            "stepbible_tipnr": (
                "entity_type",
                "entity_id",
                "original_language.dstrong",
                "original_language.estrong",
                "original_language.source_script_form",
                "osis_references",
            ),
            "openbible_structured_data:bible_geocoding": (
                "place_id",
                "place_name",
                "place_types",
                "osis_references",
                "candidate_identifications[].modern_id",
                "candidate_identifications[].name",
                "candidate_identifications[].confidence_score",
            ),
        }
        for dataset_id, field_paths in approved.items():
            for field_path in field_paths:
                with self.subTest(dataset_id=dataset_id, field_path=field_path):
                    result = classify_source_field(dataset_id, field_path)
                    self.assertEqual(result.policy_class, "general_context")
                    self.assertEqual(result.classifier_kind, "deterministic")
                    self.assertIsNone(result.model)
                    self.assertIsNone(result.prompt_fingerprint)
                    self.assertEqual(result.reason_codes, ("approved_structural_field",))
                    self.assertTrue(is_answer_eligible(result.policy_class))

    def test_prohibited_and_freeform_fields_fail_closed(self) -> None:
        refused = (
            ("openbible_structured_data:cross_references", "from_verse"),
            ("tyndale_open_resources:open_bible_dictionary", "entry_text"),
            ("tyndale_open_resources:open_study_notes", "note_text"),
            ("openbible_structured_data:bible_geocoding", "linked_data.description"),
            ("stepbible_tipnr", "brief_description"),
            ("unknown_dataset", "place_id"),
            ("stepbible_tipnr", "unknown_field"),
        )
        for dataset_id, field_path in refused:
            with self.subTest(dataset_id=dataset_id, field_path=field_path):
                result = classify_source_field(dataset_id, field_path)
                self.assertEqual(result.policy_class, "uncertain")
                self.assertFalse(is_answer_eligible(result.policy_class))

    def test_invalid_or_model_classification_is_refused(self) -> None:
        for dataset_id, field_path in (("", "place_id"), ("stepbible_tipnr", "")):
            with self.subTest(dataset_id=dataset_id, field_path=field_path):
                with self.assertRaises(ClassificationRefused):
                    classify_source_field(dataset_id, field_path)

        with self.assertRaises(ClassificationRefused):
            classify_source_field(
                "stepbible_tipnr",
                "entity_id",
                classifier_kind="model",
            )

    def test_absent_mixed_and_uncertain_are_answer_ineligible(self) -> None:
        for policy_class in (None, "mixed", "uncertain", "not_registered"):
            with self.subTest(policy_class=policy_class):
                self.assertFalse(is_answer_eligible(policy_class))

        for policy_class in (
            "general_context",
            "orthodox_viewpoint",
            "protected_spirit_filled",
        ):
            with self.subTest(policy_class=policy_class):
                self.assertTrue(is_answer_eligible(policy_class))


class MigrationContractTests(unittest.TestCase):
    def test_verify_uses_only_the_readonly_environment(self) -> None:
        verify_path, verify_key = database_environment("verify")
        apply_path, apply_key = database_environment("apply")
        self.assertEqual(verify_path.name, ".env.readonly-analysis")
        self.assertEqual(verify_key, "READONLY_ANALYSIS_DB_URL")
        self.assertEqual(apply_path.name, ".env")
        self.assertEqual(apply_key, "SUPABASE_DB_URL")

    def test_dry_run_validates_sql_without_database_configuration(self) -> None:
        env = dict(os.environ)
        env.pop("SUPABASE_DB_URL", None)
        env.pop("READONLY_ANALYSIS_DB_URL", None)
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "apply_migration_097.py"), "--dry-run"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("database_connection=none", completed.stdout)
        self.assertIn("migration=097_source_passage_policy.sql", completed.stdout)
        self.assertIn("status=valid", completed.stdout)

    def test_dry_run_rejects_weakened_schema_contracts(self) -> None:
        sql = (ROOT / "migrations" / "097_source_passage_policy.sql").read_text(
            encoding="utf-8"
        )
        self.assertGreater(len(validate_migration(sql)), 0)
        weakened_variants = (
            sql.replace(
                "policy_class IN ('general_context', 'orthodox_viewpoint', 'protected_spirit_filled', 'mixed', 'uncertain')",
                "policy_class IN ('general_context')",
            ),
            sql.replace("AND model IS NULL", "AND model IS NOT NULL", 1),
            sql.replace("AND OLD.is_current", "AND true", 1),
            sql.replace(
                "GRANT SELECT ON source_passage_policy_versions TO newwine_readonly_analysis",
                "REVOKE ALL ON source_passage_policy_versions FROM newwine_readonly_analysis",
            ),
            sql.replace(
                "REVOKE ALL ON source_passage_policy_versions FROM service_role",
                "GRANT ALL ON source_passage_policy_versions TO service_role",
            ),
        )
        for weakened in weakened_variants:
            with self.subTest(mutation=weakened):
                with self.assertRaises(MigrationValidationError):
                    validate_migration(weakened)


if __name__ == "__main__":
    unittest.main(verbosity=2)
