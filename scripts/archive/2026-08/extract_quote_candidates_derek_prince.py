#!/usr/bin/env python3
"""
Extract quote candidates from Derek Prince non-book material and land them as
PENDING only.  This script does NOT approve anything; it runs the existing
quote verifier and inserts passing candidates with status='pending'.  Refusals
are logged to quote_verification_log exactly like the existing pipeline.

Scope:
  teacher = Derek Prince
  source_type != 'book'
  source_kind != 'commentary'

Per-document candidate volume (2026-08-13): the per-document cap is
length-scaled, not a flat count. By default a document's target is
round(word_count / WORDS_PER_QUOTE_TARGET), floor 1, soft ceiling
MAX_QUOTES_PER_DOC_CEILING -- calibrated against this corpus's own real
document lengths (382-14,662 words, median ~8,652) so a typical
book-chapter-length document here lands close to 15 and a short document
still gets at least 1 attempt. Pass --per-doc-limit / --max-attempts-per-doc
explicitly to override the length-scaled defaults for all documents in a run.

Run from repo root:
  python3 scripts/extract_quote_candidates_derek_prince.py --dry-run --limit 10
  python3 scripts/extract_quote_candidates_derek_prince.py --max-quotes 250

Long job:
  nohup python3 scripts/extract_quote_candidates_derek_prince.py --max-quotes 250 \
      > logs/extract_prince_$(date +%Y%m%d_%H%M%S).log 2>&1 &
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse

# Allow imports from backend/app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

import psycopg2
from psycopg2.extensions import connection

# Suppress the urllib3/LibreSSL warning before any HTTP client is imported.
warnings.simplefilter("ignore")

from app.db.supabase import get_supabase
from app.services.quote_verifier import verify_quote_candidate
from app.services.quotes import _log_quote_decision

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)
# Suppress noisy HTTP-client debug logs from the Supabase REST calls.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# ── Hard-wired corpus facts ─────────────────────────────────────────────────
PRINCE_SOURCE_ID = "17be391b-d025-4178-8543-3e84da675c5d"
PRINCE_NAME = "Derek Prince"
DEFAULT_MAX_QUOTES = 250

# Length-scaled per-document target (2026-08-13, replaces the flat
# per-doc-limit=1 cap -- Alex's explicit decision). Calibrated against this
# corpus's own real document-length distribution (382-14,662 words, median
# ~8,652 across the 496 in-scope documents, measured live 2026-08-13): at
# WORDS_PER_QUOTE_TARGET=580, the median document lands at ~15 quotes, a
# 382-word document floors at 1, and the longest (~14.7k words) lands at ~25,
# comfortably under the soft ceiling.
WORDS_PER_QUOTE_TARGET = 580
MAX_QUOTES_PER_DOC_CEILING = 30
# How many candidates to verify per document before giving up, as a
# multiple of the target. Historically (flat limit=1) 8 attempts found a
# passing candidate almost every time; this keeps a similar per-quote
# buffer at higher targets rather than a flat constant that would starve
# a 15-quote target after 8 tries.
ATTEMPTS_PER_QUOTE_TARGET = 6
DEFAULT_MAX_ATTEMPTS_PER_DOC_FLOOR = 8

# Sentence splitter: capture from non-whitespace start up to and including a
# terminal punctuation mark and an optional closing quote/guillemet.
_SENT_RE = re.compile(r"[^.!?]*[.!?]+[\"\'’”»]?")

# Candidates that begin with these words rarely stand alone out of context.
_WEAK_START_WORDS = {
    "and", "but", "or", "so", "then", "there", "here", "now", "well", "oh",
    "ah", "yes", "no", "okay", "all", "why", "what", "where", "when", "who",
    "how", "if", "because", "for", "yet", "nor", "nevertheless", "however",
    "moreover", "furthermore", "therefore", "thus", "consequently", "meanwhile",
    "instead", "otherwise", "anyhow", "anyway", "right", "listen", "look",
    "see", "say", "said", "tell", "told", "ask", "asked", "think", "thought",
    "know", "knew", "suppose", "perhaps", "maybe", "well,", "okay,",
}

# Oral/audience/interaction markers that make a candidate a bad standalone quote.
_BAD_PHRASES = {
    "applause", "laughter", "amen", "hallelujah", "somebody", "everybody",
    "anybody", "nobody", "are you there", "turn to", "look at", "find and",
    "read out", "stand up", "raise your", "lift up", "open your", "close your",
    "write down", "say it", "say after", "repeat after", "follow me",
    "can you", "could you", "would you", "will you", "do you", "did you",
    "have you", "has he", "is it", "is this", "is that", "are they",
    "come on", "look here", "you see",
}

# Positive signals: core theological vocabulary.  A candidate that hits several
# of these is more likely to be devotionally/quotably dense.
_THEO_WORDS = {
    "god", "jesus", "christ", "holy spirit", "spirit", "lord", "father",
    "faith", "love", "pray", "prayer", "salvation", "sin", "cross",
    "resurrection", "atonement", "redemption", "grace", "mercy", "truth",
    "word", "scripture", "bible", "believe", "obey", "disciple", "kingdom",
    "heaven", "eternal", "life", "death", "devil", "demon", "heal",
    "miracle", "blessing", "curse", "covenant", "baptism", "fast",
    "fasting", "tongues", "prophecy", "apostle", "church", "gospel",
    "worship", "praise", "thanksgiving", "repent", "forgive",
    "justification", "sanctification", "righteous", "holiness", "power",
    "authority", "victory", "peace", "joy", "hope", "patient", "wait",
    "suffer", "endure", "overcome", "grace", "sacrifice", "blood",
    "redemption", "redeem", "ransom", "intercession", "mediator",
}

# Phrases that often introduce scripture reading, not a standalone thought.
_TRANSITIONAL_PHRASES = {
    "then we read", "then in verse", "in verse", "chapter", "verse", "passage",
    "read with me", "look at verse", "turn with me", "open your bibles",
}

# Long double-quote-delimited spans, regardless of what precedes them.
# Confirmed empirically 2026-08-13: all 20 Derek Prince documents that had
# produced zero approved quotes under the old flat per-doc-limit=1 cap had a
# single surviving candidate dominated by a directly-quoted passage (usually
# Scripture) -- a defect class the deterministic verifier's exact-substring/
# boundary/speaker checks do not catch, because the quoted text really is an
# exact, well-bounded substring spoken by the credited teacher; the problem
# is that most of the candidate's own words are not the teacher's, they are
# the passage's. This mirrors quote_subchunk_exclusion.py's block-quotation
# detector but does not require its ":—"/"writes:" lead-in marker, since
# Prince often opens a quotation with nothing more than "He says," or no
# lead-in clause at all.
_RE_LONG_DOUBLE_QUOTE = re.compile(r"[“\"][^”\"]{80,}?[”\"]", re.DOTALL)


def _get_psycopg2_conn() -> connection:
    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def _admin_user_id(cur) -> str:
    """Return an admin user_id for provenance.  Fail hard if none exists."""
    cur.execute(
        "SELECT user_id FROM user_roles WHERE role = 'admin' ORDER BY created_at LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("no admin user found in user_roles")
    return row[0]


def target_quotes_for_document(word_count: int) -> int:
    """Length-scaled per-document quote target (2026-08-13).

    round(word_count / WORDS_PER_QUOTE_TARGET), floored at 1 so every
    document still gets one attempt, soft-capped at
    MAX_QUOTES_PER_DOC_CEILING as a sanity valve (never realistically binds
    against this corpus's own length distribution -- the longest in-scope
    document lands around 25).
    """
    if word_count <= 0:
        return 1
    target = round(word_count / WORDS_PER_QUOTE_TARGET)
    return max(1, min(target, MAX_QUOTES_PER_DOC_CEILING))


def target_attempts_for_document(target_quotes: int) -> int:
    """Attempt budget for a document's target -- a multiple of the target,
    floored at the old flat default so a target=1 document keeps the same
    8-attempt buffer it always had."""
    return max(target_quotes * ATTEMPTS_PER_QUOTE_TARGET, DEFAULT_MAX_ATTEMPTS_PER_DOC_FLOOR)


def split_sentences(text: str) -> List[Tuple[int, int, str]]:
    """Return (start, end, sentence_text) spans for text.

    Start is the first non-whitespace character of the sentence; end is after
    the sentence-terminal punctuation (and optional closing quote).  The span
    is guaranteed to be an exact substring of text.
    """
    out: List[Tuple[int, int, str]] = []
    for m in _SENT_RE.finditer(text):
        raw = m.group()
        leading_ws = len(raw) - len(raw.lstrip())
        start = m.start() + leading_ws
        end = m.end()
        sentence = text[start:end]
        if sentence:
            out.append((start, end, sentence))
    return out


def _score_candidate(text: str) -> int:
    """Return a quality score; <=0 means do not attempt verification."""
    length = len(text)
    if length < 120 or length > 500:
        return -100

    stripped = text.strip()
    if not stripped:
        return -100
    first_char = stripped[0]
    if not first_char.isalpha() or first_char.islower() or first_char.isdigit():
        return -100

    low = text.lower()
    words = low.split()
    first_word = words[0] if words else ""
    if first_word in _WEAK_START_WORDS:
        return -100

    for phrase in _BAD_PHRASES:
        if phrase in low:
            return -100

    digits = sum(ch.isdigit() for ch in text)
    if digits > length * 0.12:
        return -100

    colons = text.count(":")
    if colons > 2:
        return -100

    transitional_hits = sum(1 for ph in _TRANSITIONAL_PHRASES if ph in low)
    if transitional_hits > 1:
        return -100

    # Verse-per-line / poetic block formatting (any blank-line break inside a
    # 120-500 char, 1-3-sentence candidate) is a strong, corpus-specific
    # signal of quoted scripture text laid out one line per verse rather
    # than the teacher's own flowing sentences -- confirmed empirically
    # 2026-08-13: a candidate can be two consecutive Bible verses split by a
    # single blank line with no quotation marks and no framing prose at all
    # (e.g. 1 Peter 5:9-10), so even one occurrence is treated as
    # disqualifying, not just a penalty. See _RE_LONG_DOUBLE_QUOTE's comment
    # for the related quotation-mark-based signal.
    if "\n\n" in text:
        return -100

    # Long double-quote-delimited spans -- almost always a directly quoted
    # passage, not the teacher's own sentence, in this corpus.
    quoted_chars = sum(len(m.group()) for m in _RE_LONG_DOUBLE_QUOTE.finditer(text))
    quote_fraction = quoted_chars / length if length else 0.0
    if quote_fraction > 0.40:
        return -100

    score = 0
    if 150 <= length <= 320:
        score += 35
    elif length <= 380:
        score += 20

    for word in _THEO_WORDS:
        if word in low:
            score += 4

    # Slight preference for declarative, complete sentences.
    if text.rstrip().endswith((".", "!", "?", "'", '"', "’", "”", "»")):
        score += 5

    # Penalize questions and scripture-heavy callouts.
    if "?" in text:
        score -= 5
    if transitional_hits:
        score -= 10
    if quote_fraction > 0.15:
        score -= 10

    return score


def _topic_for_document(topic_tags) -> str:
    if topic_tags and len(topic_tags) > 0 and topic_tags[0]:
        return str(topic_tags[0]).strip()
    return "Derek Prince teaching"


def generate_candidates(chunk_content: str) -> List[Tuple[int, int, str, int]]:
    """Return candidate (start, end, text, score) spans from one chunk."""
    sentences = split_sentences(chunk_content)
    if not sentences:
        return []

    candidates: List[Tuple[int, int, str, int]] = []
    n = len(sentences)
    for i in range(n):
        for j in range(i, min(i + 3, n)):
            start = sentences[i][0]
            end = sentences[j][1]
            text = chunk_content[start:end]
            if start == 0 or end == len(chunk_content):
                # Boundary-proximity will refuse; skip to save verifier calls.
                continue
            s = _score_candidate(text)
            if s > 0:
                candidates.append((start, end, text, s))
    # Highest score first.
    candidates.sort(key=lambda x: x[3], reverse=True)
    return candidates


def load_existing_quote_texts(cur) -> set:
    cur.execute("SELECT quote_text FROM quotes")
    return {row[0] for row in cur.fetchall()}


def main():
    parser = argparse.ArgumentParser(
        description="Extract Derek Prince non-book quote candidates to pending status"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidates without inserting",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of documents processed (useful for dry-run slices)",
    )
    parser.add_argument(
        "--max-quotes",
        type=int,
        default=DEFAULT_MAX_QUOTES,
        help=f"Ceiling on pending quotes to insert (default {DEFAULT_MAX_QUOTES})",
    )
    parser.add_argument(
        "--per-doc-limit",
        type=int,
        default=None,
        help=(
            "Max pending quotes per document. Default: length-scaled per "
            f"document (round(word_count / {WORDS_PER_QUOTE_TARGET}), floor 1, "
            f"soft ceiling {MAX_QUOTES_PER_DOC_CEILING}). Pass an integer to "
            "override with a flat cap for every document in this run."
        ),
    )
    parser.add_argument(
        "--max-attempts-per-doc",
        type=int,
        default=None,
        help=(
            "Max candidates to verify per document before giving up. "
            f"Default: length-scaled (target * {ATTEMPTS_PER_QUOTE_TARGET}, "
            f"floor {DEFAULT_MAX_ATTEMPTS_PER_DOC_FLOOR}). Pass an integer to "
            "override with a flat cap for every document in this run."
        ),
    )
    parser.add_argument(
        "--doc-ids-file",
        type=str,
        default=None,
        help=(
            "Path to a file containing UUID document ids (one per line). "
            "If provided, only those documents are processed."
        ),
    )
    args = parser.parse_args()

    supabase_db = get_supabase()
    conn = _get_psycopg2_conn()
    # Use a single read-committed connection for everything.
    if args.dry_run:
        conn.set_session(readonly=True)
    cur = conn.cursor()

    admin_user_id = _admin_user_id(cur)
    logger.info("Running as admin user %s", admin_user_id)

    existing_texts = load_existing_quote_texts(cur)
    logger.info("Found %d existing quote rows to de-duplicate against", len(existing_texts))

    # ── Scope query ─────────────────────────────────────────────────────────
    cur.execute(
        """
        SELECT id, title, source_type, source_kind, topic_tags
        FROM documents
        WHERE source_id = %s
          AND source_type != 'book'
          AND source_kind != 'commentary'
        ORDER BY title
        """,
        (PRINCE_SOURCE_ID,),
    )
    docs = cur.fetchall()
    if args.doc_ids_file:
        allowed_ids = set(Path(args.doc_ids_file).read_text().split())
        docs = [d for d in docs if str(d[0]) in allowed_ids]
        logger.info(
            "Restricted scope to %d documents from %s",
            len(docs),
            args.doc_ids_file,
        )
    logger.info(
        "Scope: %d Derek Prince non-book documents (%d sermon + %d magazine_article)",
        len(docs),
        sum(1 for d in docs if d[3] == "sermon_transcript"),
        sum(1 for d in docs if d[3] == "magazine_article"),
    )

    if args.limit:
        docs = docs[: args.limit]
        logger.info("Limited to first %d documents for this run", len(docs))

    attempted_docs = 0
    docs_with_zero = 0
    errors = 0
    accepted_count = 0
    refusal_count = 0
    seen_this_run: set = set()

    for doc_idx, (doc_id, title, source_type, source_kind, topic_tags) in enumerate(docs, 1):
        try:
            if accepted_count >= args.max_quotes:
                logger.info(
                    "Reached ceiling of %d pending quotes; stopping.", args.max_quotes
                )
                break

            attempted_docs += 1
            topic = _topic_for_document(topic_tags)

            # Fetch eligible chunks for this document.
            cur.execute(
                """
                SELECT id, chunk_index, content, quote_ineligible_reason
                FROM chunks
                WHERE document_id = %s
                ORDER BY chunk_index
                """,
                (doc_id,),
            )
            chunks = cur.fetchall()
            if not chunks:
                logger.warning("[%d/%d] %s — no chunks", doc_idx, len(docs), title)
                docs_with_zero += 1
                continue

            word_count = sum(
                len(content.split()) for _, _, content, _ in chunks if content
            )
            doc_target = (
                args.per_doc_limit
                if args.per_doc_limit is not None
                else target_quotes_for_document(word_count)
            )
            doc_max_attempts = (
                args.max_attempts_per_doc
                if args.max_attempts_per_doc is not None
                else target_attempts_for_document(doc_target)
            )

            # Gather top-scoring candidates across all eligible chunks.
            all_candidates: List[Tuple[str, int, str, int]] = []  # (chunk_id, chunk_index, text, score)
            chunk_content_by_id: dict = {}
            for chunk_id, chunk_index, content, ineligible_reason in chunks:
                if not content or ineligible_reason:
                    continue
                chunk_content_by_id[chunk_id] = content
                for start, end, text, score in generate_candidates(content):
                    all_candidates.append((chunk_id, chunk_index, text, score))

            all_candidates.sort(key=lambda x: x[3], reverse=True)

            doc_inserted = 0
            attempts = 0
            for chunk_id, chunk_index, text, score in all_candidates:
                if accepted_count >= args.max_quotes:
                    break
                if doc_inserted >= doc_target:
                    break
                if attempts >= doc_max_attempts:
                    break
                if text in existing_texts or text in seen_this_run:
                    continue

                attempts += 1
                verification = verify_quote_candidate(
                    supabase_db, chunk_id, text, PRINCE_SOURCE_ID
                )

                if verification.valid:
                    if args.dry_run:
                        accepted_count += 1
                        doc_inserted += 1
                        logger.info(
                            "[DRY RUN] ACCEPT doc=%s chunk=%d score=%d text=%r",
                            title,
                            chunk_index,
                            score,
                            text[:200],
                        )
                        continue

                    # Capture immutable snapshot (full source chunk text) and insert as PENDING.
                    cur.execute(
                        """
                        INSERT INTO quote_source_revisions (chunk_id, passage_text, captured_by)
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        (chunk_id, chunk_content_by_id[chunk_id], admin_user_id),
                    )
                    revision_id = cur.fetchone()[0]
                    reviewer_note = (
                        f"Deterministic extraction from {source_type} '{title}' "
                        f"chunk {chunk_index}. Pending review; not approved."
                    )
                    cur.execute(
                        """
                        INSERT INTO quotes
                        (source_revision_id, teacher_source_id, quote_text, topic,
                         reviewer_note, status, created_by)
                        VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                        """,
                        (
                            revision_id,
                            PRINCE_SOURCE_ID,
                            text,
                            topic,
                            reviewer_note,
                            admin_user_id,
                        ),
                    )
                    conn.commit()
                    seen_this_run.add(text)
                    existing_texts.add(text)
                    accepted_count += 1
                    doc_inserted += 1
                    logger.info(
                        "INSERTED pending quote %d/%d doc=%s chunk=%d score=%d (target=%d)",
                        accepted_count,
                        args.max_quotes,
                        title,
                        chunk_index,
                        score,
                        doc_target,
                    )

                    # Log acceptance the same way the existing pipeline does.
                    _log_quote_decision(
                        supabase_db,
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        teacher_source_id=PRINCE_SOURCE_ID,
                        quote_text=text,
                        decision="accepted",
                        rule="accepted",
                        reason=None,
                        submitted_by=admin_user_id,
                    )
                else:
                    refusal_count += 1
                    if args.dry_run:
                        logger.info(
                            "[DRY RUN] REFUSE doc=%s chunk=%d rule=%s reason=%s text=%r",
                            title,
                            chunk_index,
                            verification.rule,
                            verification.reason,
                            text[:200],
                        )
                        continue

                    _log_quote_decision(
                        supabase_db,
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        teacher_source_id=PRINCE_SOURCE_ID,
                        quote_text=text,
                        decision="refused",
                        rule=verification.rule,
                        reason=verification.reason,
                        submitted_by=admin_user_id,
                    )

            if doc_inserted == 0:
                docs_with_zero += 1
                logger.info(
                    "[%d/%d] %s — zero candidates accepted (target=%d, attempts=%d/%d)",
                    doc_idx, len(docs), title, doc_target, attempts, doc_max_attempts,
                )
            else:
                logger.info(
                    "[%d/%d] %s — %d/%d quotes inserted (attempts=%d/%d)",
                    doc_idx, len(docs), title, doc_inserted, doc_target, attempts, doc_max_attempts,
                )

        except Exception as exc:
            errors += 1
            logger.exception("[%d/%d] %s — error during processing: %s", doc_idx, len(docs), title, exc)

    cur.close()
    conn.close()

    logger.info("=" * 60)
    logger.info("Run complete (dry_run=%s)", args.dry_run)
    logger.info("Documents attempted: %d", attempted_docs)
    logger.info("Pending quotes inserted: %d", accepted_count)
    logger.info("Documents that produced zero accepted candidates: %d", docs_with_zero)
    logger.info("Verifier refusals logged: %d", refusal_count)
    logger.info("Errors: %d", errors)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        sys.exit(1)
