"""
Automatic verifier for quote candidates (Project 3 quote rail).

Tightened 2026-08-08 to be the sole gate, not a pre-check backstopped by a
human reviewer's judgment -- see CLAUDE.md "Settled product decisions
(2026-08-08)". Every check here is deterministic (string matching, position
arithmetic, a document lookup) -- none of it is an LLM/AI judgment call,
same posture as the exact-substring check this module already had. A
candidate is accepted only if it passes ALL of:

  1. exact-substring match -- found, character-for-character, inside the
     content of exactly one committed chunk, never assembled across a chunk
     boundary, never accepted on a lookup failure.
  2. whole-chunk exclusion zone -- the chunk must not be flagged
     chunks.quote_ineligible_reason.
  3. sub-chunk exclusion zone -- the candidate must not overlap an embedded
     non-teacher span inside the chunk (translator footnotes, third-party
     block quotations, catechism/directory inserts). Detected deterministically
     by app.services.quote_subchunk_exclusion; see that module for the exact
     pattern set and its conservative limits.
  4. boundary proximity / sentence completeness -- the candidate must not
     sit flush against either edge of the chunk, must begin immediately
     after another sentence's terminal punctuation (never chunk position 0,
     which cannot be verified against whatever preceded this chunk), and
     must itself end on terminal punctuation. This is the automatic form of
     the standing "no words trimmed at either end" rule (CLAUDE.md Settled
     decision #16, 2026-08-03 section) -- with no human catching a subtle
     mid-sentence trim, this errs toward refusing more real quotes, not
     fewer, at any boundary that cannot be positively confirmed clean.
  5. single-paragraph span -- the candidate must not contain an internal
     blank-line paragraph break (`\\n\\n`). Open/close terminal punctuation
     alone does not stop a quote from swallowing the next section's opening
     sentence after a paragraph break (live failure: Derek Prince, "The New
     Testament Evangelist", approved quote ending "...Holy Spirit." then
     "\\n\\nWe come to the seventh unity..."). Refusing multi-paragraph
     spans is the automatic form of that section-boundary rule. Single
     newlines inside a paragraph remain allowed.
  6. speaker confirmation -- the attributed teacher_source_id must equal the
     source document's own source_id. A strong content match is not
     confirmation -- this is the concrete, checkable form that rule takes
     for written, already-attributed documents (see the Savchuk case in
     CLAUDE.md Landmines, the case that motivated this rule).

Checks 1, 2, and 6 are re-checked independently by the database itself
against the immutable captured snapshot, via the trg_enforce_quote_approval_
gates trigger (migration 082, gate 4 revised by migration 085's speaker
gate) -- that trigger is the authoritative backstop for those three. Checks 3
(sub-chunk exclusion), 4 (boundary/sentence-completeness), and 5
(single-paragraph span) are deliberately Python-only, accepted narrower
boundaries (same posture as services/quotes.py's per-work quote-text cap) --
there is exactly one write path, create_and_approve_quote(), and it always
runs these checks before any INSERT is attempted.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

from app.services.quote_subchunk_exclusion import (
    candidate_overlaps_excluded_subspan,
    detect_excluded_subspans,
)


class QuoteVerification(NamedTuple):
    valid: bool
    reason: Optional[str]
    rule: str


# Characters that can legitimately end a sentence -- ASCII and the curly/
# guillemet quote marks this corpus's public-domain and licensed sources
# actually use. A candidate must both begin right after one of these (never
# at chunk position 0) and end its own text on one of these.
_SENTENCE_TERMINAL_CHARS = set('.!?"\'’”»')


def verify_quote_exact_match(db, chunk_id: str, quote_text: str) -> QuoteVerification:
    """Check quote_text against the live content of exactly one chunk.

    db is a Supabase client (app.db.supabase.get_supabase()). Any lookup
    failure or missing/empty content is a rejection, never a silent pass.
    Kept as a standalone, narrowly-scoped check (scripts/test_quote_verifier.py
    exercises it directly) -- verify_quote_candidate() below is the
    orchestrating function every real caller should use instead.
    """
    if not quote_text or not quote_text.strip():
        return QuoteVerification(False, "quote_text is empty", "empty_text")

    try:
        result = db.table("chunks").select("content").eq("id", chunk_id).limit(1).execute()
    except Exception as e:
        return QuoteVerification(False, "chunk lookup failed: %s" % e, "chunk_lookup_failed")

    if not result.data:
        return QuoteVerification(False, "chunk %s not found" % chunk_id, "chunk_not_found")

    chunk_content = result.data[0]["content"]
    if not chunk_content:
        return QuoteVerification(False, "chunk %s has no content" % chunk_id, "chunk_empty")

    if quote_text not in chunk_content:
        return QuoteVerification(
            False, "quote_text is not an exact substring of chunk %s" % chunk_id, "not_exact_substring"
        )

    return QuoteVerification(True, None, "exact_match")


def _is_near_chunk_boundary(chunk_content: str, start: int, end: int) -> bool:
    """True if the candidate sits flush against either edge of the chunk --
    position 0 cannot be checked against whatever text preceded this chunk
    in the source document, and the chunk's own end cannot be checked
    against whatever follows. Either is treated as unverifiable, not safe."""
    return start == 0 or end == len(chunk_content)


def _has_clean_sentence_boundaries(chunk_content: str, start: int, end: int) -> bool:
    """The text immediately preceding the candidate (once trailing
    whitespace is stripped) must end on sentence-terminal punctuation --
    i.e. the candidate genuinely opens a new sentence, not a fragment
    concatenated onto the tail of the previous one. The candidate's own
    text must likewise end on sentence-terminal punctuation. Both fail
    closed: no preceding text, or an empty/unpunctuated candidate, refuses."""
    preceding = chunk_content[:start].rstrip()
    if not preceding or preceding[-1] not in _SENTENCE_TERMINAL_CHARS:
        return False
    candidate = chunk_content[start:end].rstrip()
    if not candidate or candidate[-1] not in _SENTENCE_TERMINAL_CHARS:
        return False
    return True


def _has_internal_paragraph_break(quote_text: str) -> bool:
    """True if the candidate spans more than one blank-line-separated
    paragraph. A single paragraph may still contain ordinary newlines."""
    if not quote_text:
        return False
    paragraphs = [p for p in quote_text.split("\n\n") if p.strip()]
    return len(paragraphs) > 1


def verify_quote_candidate(
    db, chunk_id: str, quote_text: str, teacher_source_id: str
) -> QuoteVerification:
    """The full tightened verifier -- every check a candidate must pass to
    be saved as approved. Runs exact-match first (needed to locate the
    candidate's position for the boundary check), then exclusion-zone,
    boundary/sentence-completeness, and speaker-confirmation, in that order.
    The first failing check's reason is returned; nothing partial-passes."""
    exact = verify_quote_exact_match(db, chunk_id, quote_text)
    if not exact.valid:
        return exact

    try:
        chunk_result = (
            db.table("chunks")
            .select("content, document_id, quote_ineligible_reason")
            .eq("id", chunk_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        return QuoteVerification(False, "chunk lookup failed: %s" % e, "chunk_lookup_failed")
    if not chunk_result.data:
        return QuoteVerification(False, "chunk %s not found" % chunk_id, "chunk_not_found")

    chunk_row = chunk_result.data[0]
    chunk_content = chunk_row["content"]

    if chunk_row.get("quote_ineligible_reason"):
        return QuoteVerification(
            False,
            "chunk %s is a known exclusion zone: %s" % (chunk_id, chunk_row["quote_ineligible_reason"]),
            "exclusion_zone",
        )

    start = chunk_content.find(quote_text)
    end = start + len(quote_text)

    # Sub-chunk exclusion: embedded non-teacher text (translator notes,
    # third-party block quotations, catechism inserts) inside a chunk that
    # also contains legitimate teacher material.
    excluded_subspans = detect_excluded_subspans(chunk_content)
    overlaps, sub_reason = candidate_overlaps_excluded_subspan(
        chunk_content, quote_text, excluded_subspans
    )
    if overlaps:
        return QuoteVerification(
            False,
            "candidate overlaps a sub-chunk exclusion zone (%s)" % sub_reason,
            "subchunk_exclusion",
        )

    if _is_near_chunk_boundary(chunk_content, start, end):
        return QuoteVerification(
            False,
            "candidate sits flush against a chunk boundary (start=%d, end=%d, chunk_len=%d) -- "
            "cannot verify it isn't truncated relative to the surrounding source text"
            % (start, end, len(chunk_content)),
            "boundary_proximity",
        )

    if not _has_clean_sentence_boundaries(chunk_content, start, end):
        return QuoteVerification(
            False,
            "candidate does not open and close on clean sentence boundaries -- "
            "refusing rather than risking a trim that reverses meaning",
            "boundary_proximity",
        )

    if _has_internal_paragraph_break(quote_text):
        return QuoteVerification(
            False,
            "candidate contains an internal blank-line paragraph break -- "
            "refusing rather than allowing a quote to swallow the next section",
            "internal_paragraph_break",
        )

    document_id = chunk_row.get("document_id")
    try:
        doc_result = db.table("documents").select("source_id").eq("id", document_id).limit(1).execute()
    except Exception as e:
        return QuoteVerification(False, "document lookup failed: %s" % e, "speaker_unconfirmed")
    if not doc_result.data:
        return QuoteVerification(
            False, "document %s not found -- cannot confirm speaker" % document_id, "speaker_unconfirmed"
        )

    document_source_id = doc_result.data[0]["source_id"]
    if document_source_id != teacher_source_id:
        return QuoteVerification(
            False,
            "teacher_source_id %s does not match the source document's own source_id %s -- "
            "a content match is not confirmation" % (teacher_source_id, document_source_id),
            "speaker_unconfirmed",
        )

    return QuoteVerification(True, None, "accepted")
