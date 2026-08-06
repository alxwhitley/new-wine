"""
Exact-substring verifier for quote candidates (Project 3 quote rail).

A quote is valid only if it is found, character-for-character, inside the
content of exactly one committed chunk -- never assembled across a chunk
boundary (a quote must live entirely inside one retrievable unit), and
never accepted on a lookup failure. Fail-closed: anything that cannot be
positively verified is rejected, not passed through with a warning.

This is a pre-check the review tool calls before it will let a quote be
saved as approved (see app.routers.quotes). The database itself re-checks
the same rule independently, against the immutable captured snapshot rather
than a live chunk re-read, via the trg_enforce_quote_approval_gates trigger
(migration 082) -- that trigger is the authoritative backstop; this
function exists to give the reviewer an immediate, specific reason before
anything is written.
"""
from __future__ import annotations

from typing import NamedTuple, Optional


class QuoteVerification(NamedTuple):
    valid: bool
    reason: Optional[str]


def verify_quote_exact_match(db, chunk_id: str, quote_text: str) -> QuoteVerification:
    """Check quote_text against the live content of exactly one chunk.

    db is a Supabase client (app.db.supabase.get_supabase()). Any lookup
    failure or missing/empty content is a rejection, never a silent pass.
    """
    if not quote_text or not quote_text.strip():
        return QuoteVerification(False, "quote_text is empty")

    try:
        result = db.table("chunks").select("content").eq("id", chunk_id).limit(1).execute()
    except Exception as e:
        return QuoteVerification(False, "chunk lookup failed: %s" % e)

    if not result.data:
        return QuoteVerification(False, "chunk %s not found" % chunk_id)

    chunk_content = result.data[0]["content"]
    if not chunk_content:
        return QuoteVerification(False, "chunk %s has no content" % chunk_id)

    if quote_text not in chunk_content:
        return QuoteVerification(
            False, "quote_text is not an exact substring of chunk %s" % chunk_id
        )

    return QuoteVerification(True, None)
