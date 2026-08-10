"""Safe path construction for identifier-derived coordinator artifacts."""

import os
from typing import Optional

from harness_contracts.v1.packet import is_harness_id


def validate_harness_id(value: str, path: str = "identifier") -> str:
    """Return a safe harness identifier or raise before filesystem use."""
    if not is_harness_id(value):
        raise ValueError(f"unsafe harness identifier at {path}: {value!r}")
    return value


def safe_state_path(
    state_root: str,
    *literal_parts: str,
    identifier: str,
    identifier_suffix: str = "",
    suffix: Optional[str] = None,
) -> str:
    """Build an identifier-derived path and prove it remains under state_root."""
    safe_id = validate_harness_id(identifier, "identifier")
    root = os.path.realpath(state_root)
    parts = [root, *literal_parts, safe_id + identifier_suffix]
    if suffix is not None:
        parts.append(suffix)
    candidate = os.path.realpath(os.path.join(*parts))
    if os.path.commonpath((root, candidate)) != root:
        raise ValueError("constructed path escapes state root")
    return candidate
