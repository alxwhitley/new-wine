"""
Canonical home for source-alias normalization, shared by the backend
(reference verification, this module) and scripts/source_resolver.py
(ingest-time attribution). Do not fork this function — scripts/source_resolver.py
imports it from here rather than defining its own copy (see Task 3).
"""
from __future__ import annotations

import re
from typing import Optional


def normalize_alias_key(s: Optional[str]) -> str:
    """Lowercase, trim, collapse internal whitespace to a single space.

    This is the sole normalization contract for source_aliases.alias_key.
    It must match the Python normalization used when migration 050 was seeded:
        re.sub(r'\\s+', ' ', s.lower().strip())
    """
    if not s:
        return ""
    return re.sub(r'\s+', ' ', s.lower().strip())
