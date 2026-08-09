"""Canonical JSON serialization and SHA-256 hashing for contract v1."""

import hashlib
import json
from typing import Any, Dict, Optional, Set


def canonical_bytes(value: Any, omit: Optional[Set[str]] = None) -> bytes:
    """Return deterministic UTF-8 JSON bytes for ``value``.

    If ``omit`` is supplied, those top-level keys are removed before
    serialization.  This is used for self-referential digests such as
    ``packet_sha256``.
    """
    if omit:
        value = {k: v for k, v in value.items() if k not in omit}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_sha256(data: bytes) -> str:
    """Return lowercase hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()
