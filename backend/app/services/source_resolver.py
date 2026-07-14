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


def is_source_servable(db, source_id: str) -> bool:
    """Return True if this source may currently be served, using the exact
    same predicate as migration 049/056's SQL gate:

        s.license_status IN ('public_domain', 'owned')
        OR (NOT safe_mode_on AND s.visibility = 'shown')

    safe_mode is read fresh on every call — it is a global kill switch and
    must never be cached across requests.
    """
    safe_mode_result = (
        db.table("app_settings").select("value").eq("key", "safe_mode").limit(1).execute()
    )
    safe_mode_on = bool(safe_mode_result.data) and safe_mode_result.data[0]["value"] == "on"

    source_result = (
        db.table("sources").select("license_status, visibility").eq("id", source_id).limit(1).execute()
    )
    if not source_result.data:
        return False

    row = source_result.data[0]
    if row["license_status"] in ("public_domain", "owned"):
        return True
    return (not safe_mode_on) and row["visibility"] == "shown"
