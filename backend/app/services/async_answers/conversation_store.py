"""Conversation/message persistence for the async answer path (Stage 2, Project 1).

MIRRORS chat.py's `_save_conversation` row shape -- a `conversations` row plus a
user message and an assistant message (with citations + verified_references) -- so a
logged-in user's async-path answer lands in their history exactly as a live-path
answer would. Kept as a deliberate copy, not a shared import, so chat.py's LIVE path
stays byte-identical this pre-cutover session (same convention as producer.py /
metering.py). DRIFT POINT: unify at full cutover.

Why persistence lives on the RESULT-delivery side, not in the worker: a single
generation may be SHARED across users (single-flight/reuse). The worker completes ONE
job; it does not know who is reading it. Persistence must therefore be per-READER
(the authenticated /async-chat/result connection), each writing to their OWN
conversation -- so one shared generation still produces two separate histories.

Idempotency (the result GET is reconnectable -- "reconnecting is just another GET"):
message ids are DETERMINISTIC (uuid5 of conversation_id + job_id + role) and every
insert is `ON CONFLICT (id) DO NOTHING`, so re-delivering a completed job to the same
user never duplicates rows. Best-effort like chat.py: exceptions are swallowed and
logged, never breaking answer delivery.

Writes go over the async path's own direct-Postgres `Db` (psycopg2) -- the same
connection the worker/queue use. That connection is the Supabase direct role, which
BYPASSes RLS, exactly as chat.py's service-key supabase client does. The row shape is
identical either way.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, List, Optional

from psycopg2.extras import Json

from .db import dict_cursor

logger = logging.getLogger(__name__)

# Fixed namespace for deterministic (idempotent) conversation/message ids. A
# constant -- must never change, or reconnect idempotency and cross-turn
# continuity would break for already-issued ids.
_NS = uuid.UUID("6f2a9d1e-7c34-5b8a-9e21-3d4c5f6a7b80")


def resolve_conversation_id(supplied: Optional[str], job_id: str, user_id: str) -> str:
    """The conversation this reader's answer belongs to.

    If the client threaded one back (a continuing conversation), use it. Otherwise
    derive one deterministically from (job_id, user_id) -- stable across reconnect
    (so a re-GET resolves the SAME conversation) and DISTINCT per user (so a
    single-flight-shared job still yields one conversation per reader). The client
    stores the returned id and threads it on the next turn, matching chat.py's
    server-mints-then-client-reuses lifecycle.
    """
    if supplied:
        return str(supplied)
    return str(uuid.uuid5(_NS, "conv:%s:%s" % (job_id, user_id)))


def _message_id(conversation_id: str, job_id: str, role: str) -> str:
    return str(uuid.uuid5(_NS, "msg:%s:%s:%s" % (conversation_id, job_id, role)))


def assistant_message_id(conversation_id: str, job_id: str) -> str:
    """The deterministic id of the assistant message this job produces in this
    conversation -- returned to the client in the result meta (parity with
    chat.py's meta.message_id), and identical to what save_exchange() writes."""
    return _message_id(conversation_id, job_id, "assistant")


def save_exchange(
    db,
    user_id: str,
    conversation_id: str,
    question: str,
    answer: str,
    citations: Optional[List[Any]],
    verified_references: Optional[List[Any]],
    job_id: str,
) -> Optional[str]:
    """Idempotently persist one exchange (conversation + user msg + assistant msg).

    Returns the assistant message id on success, None on any failure. Best-effort:
    NEVER raises (a persistence failure must not break answer delivery, exactly as
    chat.py wraps _save_conversation in try/except). Safe to call repeatedly for the
    same (conversation, job) -- ON CONFLICT DO NOTHING makes reconnect a no-op.
    """
    try:
        user_mid = _message_id(conversation_id, job_id, "user")
        assistant_mid = _message_id(conversation_id, job_id, "assistant")
        # Title from the first question, matching chat.py. On an EXISTING
        # conversation (continuing turn) the ON CONFLICT DO NOTHING preserves the
        # original title, so this only names a genuinely new conversation.
        title = " ".join((question or "").split()[:6])

        def _write(conn):
            with dict_cursor(conn) as cur:
                cur.execute(
                    "INSERT INTO conversations (id, user_id, title) VALUES (%s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (conversation_id, user_id, title),
                )
                cur.execute(
                    "INSERT INTO messages (id, conversation_id, role, content) "
                    "VALUES (%s, %s, 'user', %s) ON CONFLICT (id) DO NOTHING",
                    (user_mid, conversation_id, question),
                )
                cur.execute(
                    "INSERT INTO messages (id, conversation_id, role, content, citations, verified_references) "
                    "VALUES (%s, %s, 'assistant', %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                    (
                        assistant_mid, conversation_id, answer,
                        Json(citations or []), Json(verified_references or []),
                    ),
                )

        db.run(_write)
        logger.info("[async] persisted exchange for user %s conversation %s (job %s)", user_id, conversation_id, job_id)
        return assistant_mid
    except Exception:
        logger.exception("[async] save_exchange failed for conversation %s (best-effort, ignored)", conversation_id)
        return None
