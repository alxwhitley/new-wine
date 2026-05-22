"""
Source filter service — queries source_toggles for disabled sources.
Caches result for 60 seconds to avoid per-request DB queries.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

_cache = None  # type: Dict | None
_cache_ts = 0.0
CACHE_TTL = 60  # seconds


def get_disabled_filters():
    # type: () -> Dict
    """Return dict of disabled source filters from source_toggles table.

    Returns:
        {
            'source_kinds': List[str],   # disabled source_kind values
            'source_names': List[str],   # disabled source_name values
            'include_copyrighted': bool, # True if copyrighted toggle is enabled
        }
    """
    global _cache, _cache_ts

    now = time.time()
    if _cache is not None and (now - _cache_ts) < CACHE_TTL:
        return _cache

    result = {
        "source_kinds": [],   # type: List[str]
        "source_names": [],   # type: List[str]
        "include_copyrighted": True,
    }

    try:
        db = get_supabase()
        rows = db.table("source_toggles").select("*").eq("enabled", False).execute()
        for row in (rows.data or []):
            id_type = row.get("identifier_type")
            identifier = row.get("source_identifier")
            if id_type == "source_kind":
                result["source_kinds"].append(identifier)
            elif id_type == "source_name":
                result["source_names"].append(identifier)
            elif id_type == "global" and identifier == "copyrighted":
                result["include_copyrighted"] = False
    except Exception:
        logger.warning("Failed to fetch source_toggles, using defaults (all enabled)")

    _cache = result
    _cache_ts = now
    return result


def is_chunk_disabled(chunk, filters=None):
    # type: (dict, Dict | None) -> bool
    """Check if a chunk should be filtered out based on disabled toggles."""
    if filters is None:
        filters = get_disabled_filters()

    source_kind = chunk.get("source_kind", "")
    if source_kind in filters["source_kinds"]:
        return True

    author = chunk.get("author") or ""
    for name in filters["source_names"]:
        if name.lower() in author.lower():
            return True

    return False
