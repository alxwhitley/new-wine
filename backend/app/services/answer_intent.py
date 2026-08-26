"""Shared fail-closed routing intent for teacher-specific answer requests."""
from __future__ import annotations

import logging
import re
from typing import Iterable, Optional, Set

from app.db.supabase import get_supabase
from app.services.source_resolver import normalize_alias_key

logger = logging.getLogger(__name__)

_teacher_aliases_cache = None  # type: Optional[Set[str]]
_teacher_aliases_load_failed = False

_RETRIEVAL_INTENT_RE = re.compile(
    r"\bwhich\s+teachers?\b"
    r"|\bwhat\s+(?:do|does)\s+.{0,40}?\bteachers?\b"
    r"|\bwho\s+teaches?\b"
    r"|\bteachers?\s+(?:say|teach|believe|think)\b",
    re.IGNORECASE,
)


def _load_teacher_aliases() -> Set[str]:
    result = get_supabase().table("source_aliases").select("alias_key").execute()
    return {row["alias_key"] for row in (result.data or []) if row.get("alias_key")}


def _ensure_teacher_aliases() -> None:
    global _teacher_aliases_cache, _teacher_aliases_load_failed
    if _teacher_aliases_cache is not None or _teacher_aliases_load_failed:
        return
    try:
        _teacher_aliases_cache = _load_teacher_aliases()
        logger.info(
            "Loaded %d source aliases for teacher-specific answer routing",
            len(_teacher_aliases_cache),
        )
    except Exception:
        logger.exception(
            "Failed to load source aliases; teacher-specific answer routing "
            "is failing closed for this process"
        )
        _teacher_aliases_load_failed = True


def contains_teacher_alias(question: str, aliases: Iterable[str]) -> bool:
    """Return whether a normalized question contains a known source alias."""
    normalized = normalize_alias_key(question)
    return any(alias in normalized for alias in aliases)


def mentions_named_teacher(question: str) -> bool:
    """Detect a named corpus teacher; load failure returns True (fail closed)."""
    _ensure_teacher_aliases()
    if _teacher_aliases_load_failed:
        return True
    return contains_teacher_alias(question, _teacher_aliases_cache or set())


def is_teacher_retrieval_intent(question: str) -> bool:
    """Detect questions explicitly requesting teacher attribution or a list."""
    return bool(_RETRIEVAL_INTENT_RE.search(question))


def requires_teacher_specific_retrieval(question: str) -> bool:
    """Shared veto for answer routes that can erase requested attribution."""
    return mentions_named_teacher(question) or is_teacher_retrieval_intent(question)
