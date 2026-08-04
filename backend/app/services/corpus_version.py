"""Shared corpus-version signal (Stage 2).

`corpus_version()` (migration 079) is the single source of truth for "has the
corpus content that determines an answer changed?" -- derived from the document
set, source license/visibility, the disabled-source set, and safe_mode. It is
used in BOTH places (Alex's call): the async reuse key (producer.current_policy)
and chat.py's informational SSE meta.

This wrapper is cached (60s, like source_filter) and FAIL-SAFE: any error returns
the last cached value or a constant fallback, NEVER raising -- so adding it to the
live answer path's meta can never break an answer.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_TTL = 60.0
_FALLBACK = "corpus-unknown"
_lock = threading.Lock()
_cache_value = None  # type: Optional[str]
_cache_ts = 0.0


def get_corpus_version(supabase=None) -> str:
    """Return the current corpus version string. Cached 60s; never raises."""
    global _cache_value, _cache_ts
    now = time.monotonic()
    if _cache_value is not None and (now - _cache_ts) < _TTL:
        return _cache_value
    try:
        if supabase is None:
            from app.db.supabase import get_supabase
            supabase = get_supabase()
        res = supabase.rpc("corpus_version").execute()
        data = res.data
        # PostgREST returns a scalar function's result directly; be defensive.
        if isinstance(data, str):
            v = data
        elif isinstance(data, list) and data:
            first = data[0]
            v = first if isinstance(first, str) else (
                next(iter(first.values())) if isinstance(first, dict) and first else None
            )
        elif isinstance(data, dict) and data:
            v = next(iter(data.values()))
        else:
            v = None
        if not v or not isinstance(v, str):
            return _cache_value or _FALLBACK
        with _lock:
            _cache_value = v
            _cache_ts = now
        return v
    except Exception:
        logger.warning("corpus_version() RPC failed -- using cached/fallback", exc_info=False)
        return _cache_value or _FALLBACK
