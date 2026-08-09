"""O2 packet state transition tests."""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
scripts_dir = os.path.join(_REPO_ROOT, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from harness_contracts.v1.transition import validate_transition


class TestTransitionValidation(unittest.TestCase):
    def test_allowed_transitions_pass(self):
        allowed = [
            ("BLOCKED", "READY"),
            ("READY", "RUNNING"),
            ("RUNNING", "REVIEW"),
            ("RUNNING", "READY"),
            ("RUNNING", "QUARANTINED"),
            ("RUNNING", "HUMAN_REQUIRED"),
            ("REVIEW", "ACCEPTED"),
            ("REVIEW", "REVISE"),
            ("REVIEW", "QUARANTINED"),
            ("REVIEW", "HUMAN_REQUIRED"),
            ("REVISE", "READY"),
        ]
        for before, after in allowed:
            with self.subTest(before=before, after=after):
                result = validate_transition(before, after)
                self.assertTrue(result["valid"], result["errors"])

    def test_terminal_states_reject_transitions(self):
        for terminal in ("ACCEPTED", "QUARANTINED", "HUMAN_REQUIRED"):
            with self.subTest(terminal=terminal):
                result = validate_transition(terminal, "READY")
                self.assertFalse(result["valid"])
                self.assertIn("INVALID_TRANSITION", [e["code"] for e in result["errors"]])

    def test_invalid_transition_fails(self):
        result = validate_transition("BLOCKED", "ACCEPTED")
        self.assertFalse(result["valid"])
        self.assertIn("INVALID_TRANSITION", [e["code"] for e in result["errors"]])

    def test_self_transition_fails(self):
        result = validate_transition("READY", "READY")
        self.assertFalse(result["valid"])
        self.assertIn("INVALID_TRANSITION", [e["code"] for e in result["errors"]])

    def test_unknown_state_fails(self):
        result = validate_transition("UNKNOWN", "READY")
        self.assertFalse(result["valid"])
        self.assertIn("INVALID_ENUM", [e["code"] for e in result["errors"]])


if __name__ == "__main__":
    unittest.main()
