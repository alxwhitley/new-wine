"""Packet state transition validation for harness contract v1."""

from typing import Any, Dict

from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import PACKET_STATES


VALID_TRANSITIONS = {
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
}

TERMINAL_STATES = {"ACCEPTED", "QUARANTINED", "HUMAN_REQUIRED"}


def validate_transition(before: str, after: str) -> Dict[str, Any]:
    errors: list = []
    if before not in PACKET_STATES:
        errors.append(error("INVALID_ENUM", "", f"Unknown before state '{before}'"))
    if after not in PACKET_STATES:
        errors.append(error("INVALID_ENUM", "", f"Unknown after state '{after}'"))
    if errors:
        return invalid_result(sort_errors(errors))

    if before in TERMINAL_STATES:
        errors.append(error("INVALID_TRANSITION", "", f"Cannot transition out of terminal state '{before}'"))
    elif (before, after) not in VALID_TRANSITIONS:
        errors.append(error("INVALID_TRANSITION", "", f"Transition from '{before}' to '{after}' is not allowed"))

    if errors:
        return invalid_result(sort_errors(errors))
    return valid_result()
