"""O2 JSON Schema contract tests.

Loads the four required JSON Schema files under schemas/harness/v1/ and
proves they:
- exist and parse as UTF-8 JSON;
- set additionalProperties: false at every object level (root + nested);
- declare required fields that match the accepted Python validator shapes.

Uses only the Python 3.9 standard library.
"""

import json
import os
import re
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts")
_SCHEMAS_DIR = os.path.join(_REPO_ROOT, "schemas", "harness", "v1")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


# Accepted object shapes extracted from the authoritative Python validators.
# Each entry maps a schema title to {path: set(required fields)}.
ACCEPTED_SHAPES = {
    "packet.schema.json": {
        "": {
            "schema_version",
            "packet_id",
            "objective",
            "dependency_ids",
            "lane",
            "assigned_worker",
            "starting_revision",
            "worktree",
            "writable_paths",
            "forbidden_surfaces",
            "required_context",
            "premise_checks",
            "acceptance_criteria",
            "verification_commands",
            "budgets",
            "network_policy",
            "checkpoint_artifacts",
            "rollback",
            "human_stop_conditions",
            "sonnet_reassignment_allowed",
            "created_by",
            "packet_sha256",
        },
        "/assigned_worker": {"worker_id", "provider", "model"},
        "/worktree": {"path", "branch"},
        "/required_context/items": {"path", "sha256"},
        "/premise_checks/items": {"check_id", "command_id", "expected"},
        "/acceptance_criteria/items": {"criterion_id", "statement", "required_evidence_ids"},
        "/verification_commands/items": {
            "command_id",
            "argv",
            "cwd",
            "timeout_seconds",
            "expected_exit_code",
            "expected_evidence_ids",
        },
        "/budgets": {
            "max_turns",
            "wall_clock_seconds",
            "retry_limit",
            "max_output_bytes",
            "cost_class",
            "allowance_limit",
        },
        "/checkpoint_artifacts/items": {"artifact_id", "path", "required_for_fallback"},
        "/rollback": {"method", "allowed_commands"},
        "/rollback/allowed_commands/items": {"argv", "cwd"},
        "/created_by": {"role", "session_id", "model"},
    },
    "worker-result.schema.json": {
        "": {
            "schema_version",
            "result_id",
            "packet_id",
            "packet_sha256",
            "attempt",
            "worker",
            "started_at",
            "finished_at",
            "starting_revision",
            "ending_revision",
            "outcome",
            "changed_files",
            "commands",
            "evidence",
            "criteria",
            "checkpoints",
            "remaining_criterion_ids",
            "fallback",
            "human_required_reasons",
            "budgets",
            "result_sha256",
        },
        "/worker": {"worker_id", "session_id", "lane", "provider", "model"},
        "/changed_files/items": {"path", "status", "before_sha256", "after_sha256"},
        "/commands/items": {
            "command_id",
            "argv",
            "cwd",
            "timestamps",
            "exit_code",
            "outcome",
            "stdout_sha256",
            "stderr_sha256",
        },
        "/commands/items/timestamps": {"started_at", "finished_at"},
        "/evidence/items": {
            "evidence_id",
            "kind",
            "criterion_ids",
            "command_id",
            "artifact_path",
            "artifact_sha256",
            "summary",
        },
        "/criteria/items": {"criterion_id", "status", "evidence_ids"},
        "/checkpoints/items": {"artifact_id", "path", "sha256"},
        "/fallback": {"reason", "provider_evidence_id", "reassign_to"},
        "/budgets": {"turns_used", "output_bytes", "retry_count", "allowance_used"},
    },
    "opus-verdict.schema.json": {
        "": {
            "schema_version",
            "verdict_id",
            "packet_id",
            "packet_sha256",
            "result_id",
            "result_sha256",
            "reviewer",
            "reviewed_at",
            "verdict",
            "criterion_findings",
            "global_findings",
            "required_corrections",
            "human_decisions_required",
            "next_state",
            "integration_revision",
            "verdict_sha256",
        },
        "/reviewer": {"role", "session_id", "model"},
        "/criterion_findings/items": {"criterion_id", "finding", "evidence_ids", "reason"},
        "/global_findings/items": {"rule_id", "finding", "evidence_ids", "reason"},
    },
    "replay-bundle.schema.json": {
        "": {
            "schema_version",
            "packet",
            "prior_state_event",
            "dependency_states",
            "worker_result",
            "opus_verdict",
            "validator_version",
            "bundle_sha256",
        },
        "/prior_state_event": {"from_state", "to_state", "event_at"},
        "/dependency_states": set(),
        "/dependency_states/items": {
            "packet_id",
            "state",
            "evidence_id",
            "upstream_packet_sha256",
            "upstream_result_sha256",
            "upstream_verdict_sha256",
            "upstream_bundle_sha256",
        },
    },
}


_SCHEMA_FILES = {
    "packet": "packet.schema.json",
    "worker_result": "worker-result.schema.json",
    "opus_verdict": "opus-verdict.schema.json",
    "replay_bundle": "replay-bundle.schema.json",
}


def _load_schema(filename: str):
    path = os.path.join(_SCHEMAS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _object_paths(schema, _path=""):
    """Yield JSON Pointer paths to every object subschema.

    Traverses properties, items, and additionalProperties when they are
    themselves schemas.  Stops at primitive/enum/reference leaves.
    """
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield _path
        for key, sub in schema.get("properties", {}).items():
            yield from _object_paths(sub, f"{_path}/{key}")
        items = schema.get("items")
        if isinstance(items, dict):
            yield from _object_paths(items, f"{_path}/items")
        if isinstance(schema.get("additionalProperties"), dict):
            yield from _object_paths(
                schema["additionalProperties"], f"{_path}/additionalProperties"
            )
        for key in ("allOf", "anyOf", "oneOf"):
            for i, sub in enumerate(schema.get(key, [])):
                yield from _object_paths(sub, f"{_path}/{key}/{i}")
    elif isinstance(schema, list):
        for i, sub in enumerate(schema):
            yield from _object_paths(sub, f"{_path}/{i}")


def _required_at_path(schema, path: str):
    """Return the set of required fields declared at the object schema path."""
    node = schema
    parts = [p for p in path.split("/") if p]
    for part in parts:
        if not isinstance(node, dict):
            return set()
        if part == "items":
            node = node.get("items", {})
        elif part == "additionalProperties":
            node = node.get("additionalProperties", {})
        elif part in node.get("properties", {}):
            node = node["properties"][part]
        else:
            return set()
    if not isinstance(node, dict):
        return set()
    return set(node.get("required", []))


class TestSchemaFilesExist(unittest.TestCase):
    def test_all_four_schema_files_exist(self):
        for name, filename in _SCHEMA_FILES.items():
            with self.subTest(name=name):
                path = os.path.join(_SCHEMAS_DIR, filename)
                self.assertTrue(
                    os.path.isfile(path),
                    f"Schema file missing: {filename}",
                )


class TestSchemasAreUtf8Json(unittest.TestCase):
    def test_all_schemas_parse_as_utf8_json(self):
        for name, filename in _SCHEMA_FILES.items():
            with self.subTest(name=name):
                schema = _load_schema(filename)
                self.assertIsInstance(schema, dict)
                self.assertEqual(schema.get("$schema"), "http://json-schema.org/draft-07/schema#")


class TestAdditionalPropertiesFalse(unittest.TestCase):
    def test_every_object_has_additionalProperties_false(self):
        failures = []
        for name, filename in _SCHEMA_FILES.items():
            schema = _load_schema(filename)
            for path in _object_paths(schema):
                node = schema
                parts = [p for p in path.split("/") if p]
                for part in parts:
                    if part == "items":
                        node = node["items"]
                    elif part == "additionalProperties":
                        node = node["additionalProperties"]
                    else:
                        node = node["properties"][part]
                if node.get("additionalProperties") is not False:
                    failures.append((filename, path or "<root>"))
        self.assertEqual(
            failures,
            [],
            "Objects missing additionalProperties: false",
        )


class TestRequiredFieldParity(unittest.TestCase):
    def test_required_fields_match_accepted_shapes(self):
        failures = []
        for filename, shapes in ACCEPTED_SHAPES.items():
            schema = _load_schema(filename)
            for path, expected_required in shapes.items():
                actual_required = _required_at_path(schema, path)
                if actual_required != expected_required:
                    failures.append(
                        (
                            filename,
                            path or "<root>",
                            f"expected={sorted(expected_required)}",
                            f"actual={sorted(actual_required)}",
                        )
                    )
        self.assertEqual(failures, [], "Required-field mismatch against accepted Python shapes")


class TestSchemaTitles(unittest.TestCase):
    def test_top_level_titles(self):
        expected = {
            "packet.schema.json": "Harness Contract v1 Packet",
            "worker-result.schema.json": "Harness Contract v1 Worker Result",
            "opus-verdict.schema.json": "Harness Contract v1 Opus Verdict",
            "replay-bundle.schema.json": "Harness Contract v1 Replay Bundle",
        }
        for filename, expected_title in expected.items():
            with self.subTest(filename=filename):
                schema = _load_schema(filename)
                self.assertEqual(schema.get("title"), expected_title)


class TestPathPatternsRejectWindowsAbsolute(unittest.TestCase):
    """Every repo-relative path pattern in the JSON schemas must reject POSIX absolute, drive-qualified, and UNC paths."""

    def _path_pattern_nodes(self, schema, _path=""):
        if isinstance(schema, dict):
            if schema.get("type") == "string" and "pattern" in schema:
                pattern = schema["pattern"]
                if pattern.startswith("^(?!/)"):
                    yield _path, pattern
            for key, sub in schema.get("properties", {}).items():
                yield from self._path_pattern_nodes(sub, f"{_path}/{key}")
            items = schema.get("items")
            if isinstance(items, dict):
                yield from self._path_pattern_nodes(items, f"{_path}/items")

    def test_all_repo_relative_patterns_reject_windows_absolute(self):
        windows_paths = [
            r"C:\outside\owned.py",
            "C:/outside/owned.py",
            r"\\server\share\owned.py",
        ]
        failures = []
        for filename in _SCHEMA_FILES.values():
            schema = _load_schema(filename)
            for path, pattern in self._path_pattern_nodes(schema):
                compiled = re.compile(pattern)
                for windows_path in windows_paths:
                    if compiled.match(windows_path):
                        failures.append((filename, path or "<root>", windows_path))
        self.assertEqual(failures, [], "Schema path pattern accepted a Windows absolute path")


if __name__ == "__main__":
    unittest.main()
