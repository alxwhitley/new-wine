from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import anthropic

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Hardcoded FALLBACK default for the answer/position generation model ID.
# The LIVE value normally comes from generation_model_config (DB, migration
# 081) via get_generation_model() below -- every generation call site (chat
# answer stream, teacher card, position papers, async producer,
# positions.py) calls that function, not this constant, directly. This
# constant is what every call site falls back to if that row is
# unreachable, missing, or malformed. thinking is disabled explicitly at
# each call site regardless of which model is live (Sonnet 5 defaults
# adaptive-thinking ON, which would eat the max_tokens budget).
GENERATION_MODEL = "claude-sonnet-5"

_anthropic_client = None
_guardrails_text = None

_model_cache = None  # type: Optional[str]
_model_cache_ts = 0.0
MODEL_CACHE_TTL = 60  # seconds -- matches source_filter.get_disabled_filters()


def get_anthropic_client():
    # type: () -> anthropic.Anthropic
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def get_generation_model():
    # type: () -> str
    """The live answer-generation model ID, read from generation_model_config
    (migration 081, one shared row) with a 60s in-process cache -- the same
    pattern as source_filter.get_disabled_filters(). Every generation call
    site calls this instead of referencing GENERATION_MODEL directly, so a
    live model change (an UPDATE to that row) takes effect for every process
    -- sync backend and async worker alike -- within one cache TTL, no
    redeploy.

    Falls back to GENERATION_MODEL (hardcoded) and logs a warning if the row
    is missing, the value is empty/whitespace-only, or the DB read fails for
    any reason -- never blocks or fails the caller's request. No allow-list:
    any non-empty value is accepted and used as-is, deliberately (Alex's
    call) -- an unfamiliar model ID is not treated as invalid.
    """
    global _model_cache, _model_cache_ts

    now = time.time()
    if _model_cache is not None and (now - _model_cache_ts) < MODEL_CACHE_TTL:
        return _model_cache

    value = GENERATION_MODEL
    try:
        db = get_supabase()
        result = db.table("generation_model_config").select("model").eq("id", 1).limit(1).execute()
        rows = result.data or []
        candidate = ((rows[0].get("model") if rows else None) or "").strip()
        if candidate:
            value = candidate
        else:
            logger.warning(
                "generation_model_config row missing/empty model value -- "
                "falling back to GENERATION_MODEL=%r", GENERATION_MODEL,
            )
    except Exception:
        logger.warning(
            "Failed to read generation_model_config -- falling back to "
            "GENERATION_MODEL=%r", GENERATION_MODEL,
        )

    _model_cache = value
    _model_cache_ts = now
    return value


def get_guardrails_text() -> str:
    """Theological guardrails text, shared by every LLM call in this backend
    that represents a source document's or teacher's views (chat.py's main
    answer stream, study.py's teacher-position synthesis). Loaded once, from
    the same theological_guardrails.txt file the main answer stream has
    always used.
    """
    global _guardrails_text
    if _guardrails_text is None:
        app_dir = Path(__file__).resolve().parent.parent
        _guardrails_text = (app_dir / "theological_guardrails.txt").read_text() + (
            "\n\nRepresent the views of the source documents faithfully and accurately, "
            "even when those views reflect traditional or complementarian theology. "
            "Do not editorialize or add modern qualifications unless they appear in the source material."
        )
    return _guardrails_text
