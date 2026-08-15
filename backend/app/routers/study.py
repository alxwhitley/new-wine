from __future__ import annotations

import re
import logging
from typing import Optional, List, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import require_user
from app.constants import ABBREV_TO_NAME, BOOK_MAP
from app.db.supabase import get_supabase
from app.services.embeddings import embed_text
from app.services.source_filter import get_disabled_filters, is_chunk_disabled
from app.services.source_resolver import is_source_servable
from app.services.llm_client import get_anthropic_client, get_guardrails_text, get_generation_model
from app.services.debate_topics import matched_debate_topic
from app.services.answer_toolbox import is_commentary_chunk, _ATTRIBUTION_REFUSAL
from app.services.reference_verifier import (
    build_retrieval_grounding,
    build_name_universe,
    ungrounded_prose_teachers,
)

logger = logging.getLogger(__name__)

router = APIRouter()

CORPUS_SOURCE_KINDS = {"sermon_transcript", "magazine_article", "word_study", "commentary"}

# SP4 teacher-card position synthesis. match_chunks/match_teacher_chunks
# supply no similarity threshold at all (confirmed by direct inspection of
# both RPCs' SQL, 2026-07-18 diagnostic) -- this floor is applied here,
# in Python, after retrieval. Starting default, empirically checked against
# this corpus's real query/chunk score distribution by
# scripts/test_teacher_card.py before this feature is considered verified.
TEACHER_POSITION_SIMILARITY_FLOOR = 0.3

# Issue 2 fix (2026-08-15 teacher-card session, closing the residual named
# at the 2026-08-15 mirror-unification Landmines entry): the bibliography
# ("works") display window and the document pool the commentary/word_study
# exclusion (Guard 2) draws candidates from are now DECOUPLED. Before this
# fix, both were the same single `.limit(20)` query -- a commentary/
# word_study-heavy teacher could have most or all of that 20-slot budget
# consumed by documents Guard 2 was going to filter out anyway, starving
# the real candidate pool `match_teacher_chunks` searches over.
# TEACHER_CARD_WORKS_LIMIT preserves the bibliography's exact prior
# behavior (top 20 by recency, unfiltered). TEACHER_CARD_CANDIDATE_DOC_LIMIT
# is the wider pool Guard 2's existing, unchanged `is_commentary_chunk()`
# filter now runs over -- deliberately not a second, duplicated SQL-level
# source_kind/source_type filter (that fallback logic -- source_kind, else
# source_type -- doesn't translate cleanly to a PostgREST `not.in.` filter
# once a NULL source_kind is in play, and forking it risks a subtly wrong
# second copy of the same rule).
TEACHER_CARD_WORKS_LIMIT = 20
TEACHER_CARD_CANDIDATE_DOC_LIMIT = 200

TEACHER_POSITION_PROMPT = (
    "You are summarizing what a specific teacher has said on a topic, based "
    "only on the excerpts provided below. Paraphrase in your own words — "
    "never quote more than a few words verbatim. Cite specific works by "
    "title when relevant. If the excerpts don't address the question, say "
    "so plainly rather than guessing or generalizing. Do not editorialize "
    "or add your own theological commentary — represent only what appears "
    "in the source material."
)

# Debate-topic variant (Project 2 phase 1, CLAUDE.md Settled decision #11 /
# app.services.debate_topics) -- selected instead of TEACHER_POSITION_PROMPT
# whenever matched_debate_topic(question) identifies one of the four named
# decision-#11 debate topics. Deliberately gated on matched_debate_topic(),
# NOT classify_topic() -- classify_topic()'s own DEBATE/SETTLED output
# defaults to DEBATE for every unmatched question (by design, see
# debate_topics.py's own docstring), so gating this prompt swap on
# classify_topic(question) == DEBATE would put the "teachers in this
# library genuinely disagree with one another" framing in front of the
# model for ordinary, uncontested topics too (tithing, deliverance, etc.)
# -- a false claim about the corpus for those questions, found live by
# scripts/test_debate_topics.py's own routing test during this build.
# matched_debate_topic() only returns non-None on an actual phrase-list hit
# against one of the four named topics, so this prompt only fires when it's
# actually true.
#
# Guards against the same failure scripts/positions.py's RESOLUTION_
# INSTRUCTION_TENSION exists to prevent for Calvinism/predestination (added
# after a confirmed case, Draft 15, where ordinary resolution wording
# stitched real Derek Prince statements into a one-sided conclusion his own
# words never actually asserted): without this, a teacher whose own
# excerpts show real uncertainty or an unresolved tension on a debate topic
# could get flattened into one confident stance the excerpts don't support
# -- misattributing a resolved position to a teacher who never took one
# (CLAUDE.md ranked failure mode 2). Unlike positions.py's tension prompt,
# this is not worded for one specific topic -- it fires for any of the four
# decision-#11 debate topics alike.
TEACHER_POSITION_DEBATE_PROMPT = (
    "You are summarizing what a specific teacher has said on a topic, based "
    "only on the excerpts provided below. This topic is one where teachers "
    "in this library genuinely disagree with one another — treat these "
    "excerpts as this one teacher's own view, not as a settled answer. "
    "Paraphrase in your own words — never quote more than a few words "
    "verbatim. Cite specific works by title when relevant. Present what "
    "the excerpts actually show, including any real tension, nuance, or "
    "unresolved question in how this teacher put it — do not resolve it "
    "into a cleaner, more confident stance than the excerpts themselves "
    "support. If the excerpts don't address the question, say so plainly "
    "rather than guessing or generalizing. Do not editorialize or add your "
    "own theological commentary — represent only what appears in the "
    "source material."
)


def _select_teacher_position_prompt(question: str) -> str:
    """Pure, directly-testable routing decision between the two prompts
    above -- factored out of get_teacher_card() so scripts/test_debate_
    topics.py can assert on it deterministically (no live LLM call, no DB)
    rather than only being provable by inspecting live model output."""
    return TEACHER_POSITION_DEBATE_PROMPT if matched_debate_topic(question) else TEACHER_POSITION_PROMPT


def parse_ref(ref: str):
    """Parse a human-readable verse reference into (abbreviation, chapter, verse).

    Handles formats like:
      "John 3:16", "1 Corinthians 13:4", "1Cor 13:4", "Gen 1:1"
    """
    ref = ref.strip()
    # Match: optional number prefix + book name, then chapter:verse
    m = re.match(
        r'^(\d?\s*[A-Za-z ]+?)\s+(\d+):(\d+)$',
        ref,
    )
    if not m:
        return None

    book_raw = m.group(1).strip().lower()
    chapter = int(m.group(2))
    verse = int(m.group(3))

    # Strip an ordinal suffix ("1st", "2nd", "3rd") glued directly onto the
    # leading digit BEFORE the space-insertion step below. Without this,
    # "1st samuel" normalizes to "1 st samuel" (space inserted after the
    # bare digit, "st" left stuck to "samuel") which matches no BOOK_MAP key
    # no matter how the map is widened. \b requires the suffix to end at a
    # non-word boundary so this never fires inside "1thessalonians"/"2third"
    # -style tokens where the letters "th"/"rd" are followed by more letters.
    book_raw = re.sub(r'^(\d)(?:st|nd|rd|th)\b', r'\1', book_raw)

    # Normalize spacing for numbered books: "1 cor" -> "1 cor", "1cor" -> "1 cor"
    book_normalized = re.sub(r'^(\d)\s*', r'\1 ', book_raw).strip()

    abbrev = BOOK_MAP.get(book_normalized)
    if not abbrev:
        # Try without trailing 's' (e.g. "psalms" already mapped, but just in case)
        abbrev = BOOK_MAP.get(book_normalized.rstrip('s'))

    if not abbrev:
        return None

    return abbrev, chapter, verse


@router.get("/lexicon")
async def get_lexicon_entry(
    strongs: str = Query(..., description="Strong's number, e.g. 'G3056'"),
    user_id: str = Depends(require_user),
):
    db = get_supabase()

    # List all lexicon documents for debugging
    all_lexicon = (
        db.table("documents")
        .select("id, title")
        .eq("source_kind", "lexicon")
        .execute()
    )
    for d in (all_lexicon.data or []):
        logger.info("LEXICON doc: id=%s title=%s", d["id"], d["title"])

    # Find TBESG document specifically (brief Strongs lexicon, not academic LSJ)
    doc = (
        db.table("documents")
        .select("id, title")
        .eq("source_kind", "lexicon")
        .ilike("title", "%TBESG%")
        .limit(1)
        .execute()
    )
    if not doc.data:
        logger.warning("LEXICON: No TBESG document found, returning None")
        return {"content": None}

    doc_id = doc.data[0]["id"]
    doc_title = doc.data[0]["title"]
    logger.info("LEXICON: Using doc_id=%s title=%s for strongs=%s", doc_id, doc_title, strongs)

    result = (
        db.table("chunks")
        .select("content")
        .eq("document_id", doc_id)
        .ilike("content", f"Strong's {strongs} %")
        .limit(1)
        .execute()
    )
    if result.data:
        logger.info("LEXICON: Found chunk for %s, content preview: %s", strongs, result.data[0]["content"][:120])
        return {"content": result.data[0]["content"]}

    logger.warning("LEXICON: No chunk found for strongs=%s in doc=%s", strongs, doc_id)
    return {"content": None}


OT_BOOKS = {
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT",
    "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR", "NEH",
    "EST", "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER",
    "LAM", "EZK", "DAN", "HOS", "JOL", "AMO", "OBA", "JON",
    "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL",
}


@router.get("/interlinear")
async def get_interlinear(verse_id: str = Query(..., description="SBL verse ID, e.g. 'JHN.1.1'")):
    book = verse_id.split(".")[0] if "." in verse_id else ""
    language = "hebrew" if book in OT_BOOKS else "greek"

    db = get_supabase()
    result = (
        db.table("interlinear_words")
        .select("original_word, transliteration, strongs_number, english_gloss, morphology, word_position")
        .eq("verse_id", verse_id)
        .eq("language", language)
        .order("word_position")
        .execute()
    )
    return result.data or []


@router.get("/verse")
async def get_verse(ref: str = Query(..., description="Verse reference, e.g. 'John 3:16'")):
    parsed = parse_ref(ref)
    if not parsed:
        raise HTTPException(status_code=400, detail="Could not parse verse reference. Use format like 'John 3:16'.")

    abbrev, chapter, verse = parsed
    verse_id = f"{abbrev}.{chapter}.{verse}"

    db = get_supabase()
    result = db.table("verses").select("*").eq("verse_id", verse_id).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Verse not found")

    row = result.data[0]
    return {
        "verse_id": verse_id,
        "book": ABBREV_TO_NAME.get(abbrev, abbrev),
        "chapter": chapter,
        "verse": verse,
        "text": row.get("text", ""),
        "translation": row.get("translation", "WEB"),
    }


@router.get("/corpus")
async def get_corpus(
    verse: Optional[str] = Query(None, description="Verse reference, e.g. 'John 1:1'"),
    transliteration: Optional[str] = Query(None, description="Transliteration, e.g. 'logos'"),
    strongs: Optional[str] = Query(None, description="Strong's number, e.g. 'G3056'"),
    source_kind: Optional[str] = Query(None, description="Filter to a single source_kind, e.g. 'word_study'"),
    user_id: str = Depends(require_user),
):
    if not verse and not transliteration:
        raise HTTPException(status_code=400, detail="At least one of verse or transliteration is required")

    db = get_supabase()

    # Word study lookup: direct DB query by title match instead of vector search.
    # Lexicon entries dominate vector similarity, pushing word studies out of top-N.
    if source_kind == "word_study" and (strongs or transliteration):
        filters = get_disabled_filters()
        if "word_study" in filters["source_kinds"]:
            return {"results": []}
        # Find the document by Strong's number first, fall back to transliteration
        doc_query = db.table("documents").select("id, title, author, source_kind, url").eq("source_kind", "word_study")
        if strongs:
            doc_query = doc_query.ilike("title", f"%{strongs}%")
        elif transliteration:
            doc_query = doc_query.ilike("title", f"%{transliteration}%")
        doc_result = doc_query.limit(5).execute()

        results = []
        for doc in (doc_result.data or []):
            # Try excerpts table first
            excerpt_found = False
            try:
                excerpt_result = (
                    db.table("excerpts")
                    .select("content")
                    .eq("document_id", doc["id"])
                    .eq("excerpt_type", "word_study_article")
                    .limit(1)
                    .execute()
                )
                if excerpt_result.data:
                    results.append({
                        "content": excerpt_result.data[0]["content"],
                        "title": doc.get("title", ""),
                        "author": doc.get("author", ""),
                        "source_kind": doc.get("source_kind", ""),
                        "url": doc.get("url"),
                        "is_excerpt": True,
                    })
                    excerpt_found = True
            except Exception as e:
                logger.warning("Excerpts lookup failed for doc %s: %s", doc["id"], str(e)[:200])

            if not excerpt_found:
                # Fall back to raw chunks
                chunk_result = db.table("chunks").select("content").eq("document_id", doc["id"]).order("chunk_index").limit(5).execute()
                for chunk in (chunk_result.data or []):
                    results.append({
                        "content": chunk.get("content", ""),
                        "title": doc.get("title", ""),
                        "author": doc.get("author", ""),
                        "source_kind": doc.get("source_kind", ""),
                        "url": doc.get("url"),
                        "is_excerpt": False,
                    })
        return {"results": results[:5]}

    # General corpus lookup: semantic search via vector similarity
    filters = get_disabled_filters()

    parts = []
    if verse:
        parts.append(verse)
    if transliteration:
        parts.append(transliteration)
        parts.append("word")
    query = " ".join(parts)

    try:
        embedding = embed_text(query)
    except Exception:
        logger.exception("Embedding failed for corpus query: %s", query[:100])
        raise HTTPException(status_code=500, detail="Embedding service error")

    try:
        result = db.rpc("match_chunks", {
            "query_embedding": embedding,
            "match_count": 20,
            "include_copyrighted": filters["include_copyrighted"],
        }).execute()
    except Exception:
        logger.exception("match_chunks RPC failed for corpus query")
        raise HTTPException(status_code=500, detail="Search service error")

    # Filter to citable chunks, dedupe by document, take top 5
    seen_docs = set()
    results = []
    for chunk in (result.data or []):
        if chunk.get("citation_mode") != "citable":
            continue
        if chunk.get("source_kind") not in CORPUS_SOURCE_KINDS:
            continue
        if is_chunk_disabled(chunk, filters):
            continue
        doc_id = chunk.get("document_id")
        if doc_id in seen_docs:
            continue
        seen_docs.add(doc_id)
        results.append({
            "content": chunk.get("content", ""),
            "title": chunk.get("title", ""),
            "author": chunk.get("author", ""),
            "source_kind": chunk.get("source_kind", ""),
            "url": chunk.get("url"),
        })
        if len(results) >= 5:
            break

    return {"results": results}


def _parse_word_study_title(title):
    # type: (str) -> tuple
    """Extract word, transliteration, strongs from 'Word Study: Word (transliteration, G3056)'."""
    m = re.search(r'\(([^,]+),\s*(G\d+|H\d+)\)', title)
    if m:
        transliteration = m.group(1).strip()
        strongs = m.group(2).strip()
        word_part = title.split("(")[0]
        if ":" in word_part:
            word = word_part.split(":", 1)[1].strip()
        else:
            word = word_part.strip()
        return word, transliteration, strongs
    return "", "", ""


@router.get("/wordsearch")
async def word_search(
    q: str = Query(..., min_length=1, description="Search term, e.g. 'faith' or 'logos'"),
):
    db = get_supabase()
    result = (
        db.table("documents")
        .select("id, title, author")
        .eq("source_kind", "word_study")
        .ilike("title", f"%{q}%")
        .limit(10)
        .execute()
    )

    results = []
    for doc in (result.data or []):
        word, transliteration, strongs = _parse_word_study_title(doc["title"])
        results.append({
            "id": doc["id"],
            "title": doc["title"],
            "author": doc.get("author", ""),
            "word": word,
            "transliteration": transliteration,
            "strongs_number": strongs,
        })
    return {"results": results}


@router.get("/wordstudy/{document_id}")
async def get_word_study(document_id: str):
    db = get_supabase()

    # Try excerpts table first
    try:
        excerpt_result = (
            db.table("excerpts")
            .select("content")
            .eq("document_id", document_id)
            .eq("excerpt_type", "word_study_article")
            .limit(1)
            .execute()
        )
        if excerpt_result.data:
            return {"content": excerpt_result.data[0]["content"], "source": "excerpt"}
    except Exception:
        pass  # excerpts table may not exist yet

    # Fall back to concatenated chunks
    chunk_result = (
        db.table("chunks")
        .select("content")
        .eq("document_id", document_id)
        .order("chunk_index")
        .execute()
    )
    chunks = chunk_result.data or []
    if not chunks:
        raise HTTPException(status_code=404, detail="No content found")

    content = "\n\n".join(c["content"] for c in chunks)
    return {"content": content, "source": "chunks"}


@router.get("/excerpt")
async def get_excerpt(
    strongs: str = Query(..., description="Strong's number, e.g. 'G3056'"),
    user_id: str = Depends(require_user),
):
    """Return the Precept Austin word study excerpt for a Strong's number."""
    db = get_supabase()

    # Find word_study document matching this Strong's number
    doc_result = (
        db.table("documents")
        .select("id")
        .eq("source_kind", "word_study")
        .ilike("title", f"%{strongs}%")
        .limit(1)
        .execute()
    )
    if not doc_result.data:
        return {"content": None}

    doc_id = doc_result.data[0]["id"]

    # Try excerpts table first
    try:
        excerpt_result = (
            db.table("excerpts")
            .select("content")
            .eq("document_id", doc_id)
            .eq("excerpt_type", "word_study_article")
            .limit(1)
            .execute()
        )
        if excerpt_result.data:
            return {"content": excerpt_result.data[0]["content"]}
    except Exception:
        pass

    # Fall back to concatenated chunks
    chunk_result = (
        db.table("chunks")
        .select("content")
        .eq("document_id", doc_id)
        .order("chunk_index")
        .execute()
    )
    chunks = chunk_result.data or []
    if not chunks:
        return {"content": None}

    return {"content": "\n\n".join(c["content"] for c in chunks)}


@router.get("/verses")
async def get_verses_for_strongs(
    strongs: str = Query(..., description="Strong's number, e.g. 'G3056' or 'H1234'"),
):
    """Return up to 10 scripture verses associated with a Strong's number.

    Strategy: find the word_study document for this Strong's number,
    extract Bible references from its excerpt or chunk content,
    then look up verse texts from the verses table.
    """
    db = get_supabase()

    # Find word_study document matching this Strong's number
    doc_result = (
        db.table("documents")
        .select("id")
        .eq("source_kind", "word_study")
        .ilike("title", f"%{strongs}%")
        .limit(1)
        .execute()
    )
    if not doc_result.data:
        return {"verses": []}

    doc_id = doc_result.data[0]["id"]

    # Get content: try excerpt first, fall back to chunks
    content = ""
    try:
        excerpt_result = (
            db.table("excerpts")
            .select("content")
            .eq("document_id", doc_id)
            .eq("excerpt_type", "word_study_article")
            .limit(1)
            .execute()
        )
        if excerpt_result.data:
            content = excerpt_result.data[0]["content"]
    except Exception:
        pass

    if not content:
        chunk_result = (
            db.table("chunks")
            .select("content")
            .eq("document_id", doc_id)
            .order("chunk_index")
            .limit(10)
            .execute()
        )
        content = "\n\n".join(c["content"] for c in (chunk_result.data or []))

    if not content:
        return {"verses": []}

    # Extract Bible references from content using regex
    ref_pattern = re.compile(
        r'(?:Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth'
        r'|1 Samuel|2 Samuel|1 Kings|2 Kings|1 Chronicles|2 Chronicles'
        r'|Ezra|Nehemiah|Esther|Job|Psalms?|Proverbs|Ecclesiastes'
        r'|Song of Solomon|Isaiah|Jeremiah|Lamentations|Ezekiel|Daniel'
        r'|Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk'
        r'|Zephaniah|Haggai|Zechariah|Malachi'
        r'|Matthew|Mark|Luke|John|Acts|Romans'
        r'|1 Corinthians|2 Corinthians|Galatians|Ephesians|Philippians'
        r'|Colossians|1 Thessalonians|2 Thessalonians'
        r'|1 Timothy|2 Timothy|Titus|Philemon|Hebrews|James'
        r'|1 Peter|2 Peter|1 John|2 John|3 John|Jude|Revelation)'
        r'\s+\d+:\d+'
    )
    raw_refs = ref_pattern.findall(content)

    # Deduplicate while preserving order
    seen = set()  # type: set
    unique_refs = []  # type: List[str]
    for ref in raw_refs:
        if ref not in seen:
            seen.add(ref)
            unique_refs.append(ref)
        if len(unique_refs) >= 15:
            break

    # Look up verse texts
    verses = []  # type: List[dict]
    for ref in unique_refs:
        parsed = parse_ref(ref)
        if not parsed:
            continue
        abbrev, chapter, verse_num = parsed
        verse_id = f"{abbrev}.{chapter}.{verse_num}"
        result = (
            db.table("verses")
            .select("text")
            .eq("verse_id", verse_id)
            .limit(1)
            .execute()
        )
        if result.data:
            verses.append({
                "reference": ref,
                "text": result.data[0]["text"],
            })
        if len(verses) >= 10:
            break

    return {"verses": verses}


COMMENTARY_AUTHOR_BOOST = {
    "matthew henry": 0.15,
    "jamieson, fausset & brown": 0.08,
    "adam clarke": 0.03,
}
COMMENTARY_DEFAULT_PENALTY = -0.10


def _verse_id_to_ref(verse_id):
    # type: (str) -> Optional[str]
    """Convert verse_id like 'JHN.3.16' to canonical ref like 'John 3:16'."""
    parts = verse_id.split(".")
    if len(parts) != 3:
        return None
    book_code, chapter, verse = parts
    book_name = ABBREV_TO_NAME.get(book_code)
    if not book_name:
        return None
    return "{} {}:{}".format(book_name, chapter, verse)


def _fetch_neighbor_content_batch(db, requests):
    # type: (object, List[Dict]) -> Dict[Tuple[str, int], str]
    """Batch equivalent of _fetch_neighbor_content for multiple (document_id,
    chunk_index) pairs -- one .or_() query (batched at 30 conditions per the
    Supabase URL-length limit, same batch size chat.py's
    fetch_neighbor_chunks_batch uses) instead of one round trip per document.
    """
    needed_pairs = set()  # type: set
    for r in requests:
        base_idx = r["chunk_index"]
        for idx in (base_idx - 1, base_idx, base_idx + 1):
            needed_pairs.add((r["document_id"], idx))

    if not needed_pairs:
        return {}

    or_parts = [
        "and(document_id.eq.%s,chunk_index.eq.%s)" % (doc_id, idx)
        for doc_id, idx in needed_pairs
    ]

    BATCH = 30
    all_rows = []  # type: List[dict]
    for i in range(0, len(or_parts), BATCH):
        batch_filter = ",".join(or_parts[i:i + BATCH])
        result = db.table("chunks").select("document_id, chunk_index, content").or_(batch_filter).execute()
        all_rows.extend(result.data or [])

    by_doc = {}  # type: Dict[str, Dict[int, str]]
    for row in all_rows:
        by_doc.setdefault(row["document_id"], {})[row["chunk_index"]] = row["content"]

    content_map = {}  # type: Dict[Tuple[str, int], str]
    for r in requests:
        doc_id = r["document_id"]
        base_idx = r["chunk_index"]
        doc_chunks = by_doc.get(doc_id, {})
        parts = [doc_chunks[i] for i in (base_idx - 1, base_idx, base_idx + 1) if i in doc_chunks]
        content_map[(doc_id, base_idx)] = "\n\n".join(parts)
    return content_map


@router.get("/commentary")
async def get_commentary(
    verse_text: str = Query(..., description="Full English verse text"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    verse_id: Optional[str] = Query(None, description="Verse ID like JHN.3.16 — enables sermon results"),
    source_kind_filter: Optional[str] = Query(
        None, description="'commentary' or 'sermon_transcript' — restricts to one source; omit for both (current behavior, unchanged)"
    ),
    user_id: str = Depends(require_user),
):
    filters = get_disabled_filters()

    try:
        embedding = embed_text(verse_text)
    except Exception:
        logger.exception("Embedding failed for commentary query: %s", verse_text[:100])
        raise HTTPException(status_code=500, detail="Embedding service error")

    db = get_supabase()

    # Study mode commentary: only apply source_kind filters, not source_name filters.
    # source_name toggles are for chat retrieval — commentaries should always show in study.
    study_filters = {
        "source_kinds": filters["source_kinds"],
        "source_names": [],
        "include_copyrighted": filters["include_copyrighted"],
    }

    seen_docs = set()  # type: set
    results = []

    if source_kind_filter in (None, "commentary"):
        # --- Step 1+2: Book-level pre-filter via bible_references ---
        book_doc_ids = set()  # type: set
        if verse_id:
            book_code = verse_id.split(".")[0] if "." in verse_id else ""
            book_name = ABBREV_TO_NAME.get(book_code)
            if book_name:
                try:
                    ref_result = db.rpc("match_commentary_by_book", {"book_name": book_name}).execute()
                    book_doc_ids = {str(row["id"]) for row in (ref_result.data or [])}
                except Exception as e:
                    logger.error("bible_references book lookup failed for %s: %s", book_name, e)

        # --- Step 3: Vector search, filtered to book docs when available ---
        try:
            if book_doc_ids:
                result = db.rpc("match_commentary_chunks", {
                    "query_embedding": embedding,
                    "match_count": 30,
                    "document_ids": list(book_doc_ids),
                }).execute()
                logger.info("[commentary] book_doc_ids: %d, chunks returned: %d", len(book_doc_ids), len(result.data or []))
            else:
                result = db.rpc("match_chunks", {
                    "query_embedding": embedding,
                    "match_count": 30,
                    "include_copyrighted": filters["include_copyrighted"],
                }).execute()
        except Exception:
            logger.exception("match_chunks RPC failed for commentary query")
            raise HTTPException(status_code=500, detail="Search service error")

        # Commentary docs use citation_mode='silent_context' for chat (to prevent
        # inline citations) but are always shown in Study Mode.
        # Do not add a citation_mode filter here.
        # Neighbor content is deferred until after sort+pagination below (only the
        # page actually returned to the client needs it — was previously fetched
        # sequentially, one round trip per document, for all ~30 candidates here).
        for chunk in (result.data or []):
            if chunk.get("source_kind") != "commentary":
                continue
            if is_chunk_disabled(chunk, study_filters):
                continue
            doc_id = chunk.get("document_id")
            if doc_id in seen_docs:
                continue
            seen_docs.add(doc_id)
            similarity = chunk.get("similarity", 0.0)
            author = chunk.get("author", "")
            boost = COMMENTARY_AUTHOR_BOOST.get(author.lower(), COMMENTARY_DEFAULT_PENALTY)
            results.append({
                "document_id": doc_id,
                "title": chunk.get("title", ""),
                "author": author,
                "source_kind": chunk.get("source_kind", ""),
                "_chunk_index": chunk.get("chunk_index", 0),
                "_score": similarity + boost,
            })

    # --- Sermon results (new path, requires verse_id) ---
    if verse_id and source_kind_filter in (None, "sermon_transcript"):
        verse_ref = _verse_id_to_ref(verse_id)
        if verse_ref:
            try:
                sermon_result = db.rpc("match_sermon_chunks_by_ref", {
                    "query_embedding": embedding,
                    "verse_ref": verse_ref,
                    "match_count": 10,
                }).execute()

                sermon_chunks = sermon_result.data or []

                # Dedupe by document — keep best chunk per doc
                seen_sermon_docs = set()
                top_sermons = []
                for sc in sermon_chunks:
                    sdoc = sc.get("document_id")
                    if sdoc in seen_sermon_docs or sdoc in seen_docs:
                        continue
                    seen_sermon_docs.add(sdoc)
                    top_sermons.append(sc)
                    if len(top_sermons) >= 2:
                        break

                # Build results — neighbor content deferred (see comment above).
                for sc in top_sermons:
                    results.append({
                        "document_id": sc["document_id"],
                        "title": sc.get("title", ""),
                        "author": sc.get("author", ""),
                        "source_kind": "sermon_transcript",
                        "_chunk_index": sc["chunk_index"],
                        "_score": 0.75,
                    })
            except Exception:
                logger.exception("Sermon chunk query failed for verse_id=%s", verse_id)

    results.sort(key=lambda r: r["_score"], reverse=True)
    for r in results:
        del r["_score"]

    page = results[offset:offset + 3]
    has_more = len(results) > offset + 3

    # Batch-fetch neighbor content for only the page being returned (at most 3
    # documents) instead of every candidate — one .or_() query instead of up
    # to ~32 sequential round trips.
    content_map = _fetch_neighbor_content_batch(
        db, [{"document_id": r["document_id"], "chunk_index": r["_chunk_index"]} for r in page]
    )
    for r in page:
        content = content_map.get((r["document_id"], r["_chunk_index"]), "")
        r["excerpt"] = content[:200].rsplit(" ", 1)[0] + "..." if len(content) > 200 else content
        r["content"] = content
        del r["_chunk_index"]

    return {"results": page, "has_more": has_more, "total": len(results)}


# ── SP2 Phase 5: global, account-level verse pins ────────────────────────────

class PinCreate(BaseModel):
    verse_id: str


@router.get("/pins")
async def list_pins(user_id: str = Depends(require_user)):
    db = get_supabase()
    result = (
        db.table("study_pins")
        .select("id, verse_id, created_at")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    return {"pins": result.data or []}


@router.post("/pins")
async def create_pin(body: PinCreate, user_id: str = Depends(require_user)):
    db = get_supabase()
    existing = db.table("study_pins").select("id").eq("user_id", user_id).execute()
    if len(existing.data or []) >= 8:
        raise HTTPException(status_code=409, detail="pin_cap_reached")
    result = (
        db.table("study_pins")
        .insert({"user_id": user_id, "verse_id": body.verse_id})
        .execute()
    )
    return result.data[0] if result.data else {}


@router.delete("/pins/{pin_id}")
async def delete_pin(pin_id: str, user_id: str = Depends(require_user)):
    db = get_supabase()
    db.table("study_pins").delete().eq("id", pin_id).eq("user_id", user_id).execute()
    return {"ok": True}


# ── SP4: teacher cards ───────────────────────────────────────────────────────

@router.get("/teachers")
async def list_curated_teachers():
    db = get_supabase()
    result = (
        db.table("teacher_profiles")
        .select("source_id, sources(name)")
        .execute()
    )
    teachers = [
        {"name": row["sources"]["name"], "source_id": row["source_id"]}
        for row in (result.data or [])
        if row.get("sources")
    ]
    return {"teachers": teachers}


_BIO_REDACTION_PLACEHOLDER = "another minister"


def _redact_name_word_bounded(text: str, name: str, replacement: str) -> str:
    """Replace every word-bounded occurrence of `name` in `text` with
    `replacement`. A match is rejected (left untouched, scan continues past
    just one character) if the character immediately before or after it is
    itself alphabetic, so this never mangles a name embedded inside a larger
    word. Pure string transform, no DB, no guard logic -- used only to build
    a redacted COPY of prompt-bound text, never touches the value actually
    returned to the caller."""
    if not name:
        return text
    out = []
    idx = 0
    while True:
        found = text.find(name, idx)
        if found == -1:
            out.append(text[idx:])
            break
        before = text[found - 1] if found > 0 else ""
        after_pos = found + len(name)
        after = text[after_pos] if after_pos < len(text) else ""
        if before.isalpha() or after.isalpha():
            out.append(text[idx:found + 1])
            idx = found + 1
            continue
        out.append(text[idx:found])
        out.append(replacement)
        idx = after_pos
    return "".join(out)


def _redact_bio_for_prompt(
    bio: Optional[str],
    name_universe: frozenset,
    exclude_name: Optional[str] = None,
    replacement: str = _BIO_REDACTION_PLACEHOLDER,
) -> Optional[str]:
    """Issue 1 fix (2026-08-15 teacher-card session, REDONE after an
    independent reviewer reproduced a real hole in the first version). This
    is now the ONLY thing Issue 1 does: return a redacted COPY of the bio
    text, with every OTHER full corpus teacher name replaced by a generic
    placeholder, for use ONLY in the model's prompt context. The `bio` value
    returned in the API response is never touched by this function and stays
    the original, full, unredacted text -- real user-facing bibliography
    content, not evidence context.

    `exclude_name` is this card's own subject teacher (`sources.name`) and is
    deliberately never redacted: his own material is always what gets
    retrieved for his own card, so his name was never at risk of being
    flagged as ungrounded by Guard 1 in the first place -- redacting him too
    would only degrade the bio's clarity (his own background sentence
    turning into "another minister trained under...") with no safety
    benefit. This exclusion narrows what gets redacted, never widens it --
    strictly safer, not a weaker version of the fix.

    Why redaction, not pre-grounding the guard (the first version of this
    fix, removed this session): that version put a bio-mentioned name
    directly into the citation guard's RetrievalGrounding.author_keys for
    the WHOLE answer, which blanket-permitted the model to credit that name
    for ANYTHING, not just the specific fact the bio actually stated. An
    independent reviewer reproduced this live: a bio mentioning "Reinhard
    Bonnke" let a wholly FABRICATED claim ("Bonnke taught physical healing
    is guaranteed in the atonement for every believer without exception")
    sail through `ungrounded_prose_teachers` uncaught, because Bonnke's name
    was blanket-grounded just for appearing in the bio, not for the specific
    thing the model said about him -- a real hole in CLAUDE.md's #2-ranked
    failure mode (misrepresenting a real, living teacher). This version
    instead leaves `reference_verifier.py`'s guard (`build_retrieval_
    grounding`, `build_name_universe`, `ungrounded_prose_teachers`)
    completely untouched, and prevents the false positive at its actual
    source: the model is never shown the bio-mentioned OTHER-teacher name in
    the first place. If the model still produces that name in its answer, it
    came from the model's own parametric/training knowledge, not from
    anything it was shown in this request -- and the guard, unchanged,
    correctly catches that as ungrounded.
    """
    if not bio:
        return bio
    redacted = bio
    for corpus_name in name_universe:
        if exclude_name is not None and corpus_name == exclude_name:
            continue
        redacted = _redact_name_word_bounded(redacted, corpus_name, replacement)
    return redacted


@router.get("/teacher/{source_id}")
async def get_teacher_card(
    source_id: str,
    question: str = Query(..., description="The user's current turn question"),
    user_id: str = Depends(require_user),
):
    db = get_supabase()

    profile_result = (
        db.table("teacher_profiles")
        .select("bio, sources(name)")
        .eq("source_id", source_id)
        .limit(1)
        .execute()
    )
    if not profile_result.data:
        raise HTTPException(status_code=404, detail="Not a curated teacher")
    bio = profile_result.data[0]["bio"]
    name = profile_result.data[0]["sources"]["name"]

    # Zero-point gate (uniform, every teacher — not a per-source patch): a
    # curated teacher whose source has no associated points (propositions) is
    # hidden and returns not-found rather than a live empty page (the "verified
    # link to an empty author page" surface). Single existence probe through the
    # propositions -> documents FK, so it scales to large teachers without a
    # giant IN clause.
    points_probe = (
        db.table("propositions")
        .select("id, documents!inner(source_id)")
        .eq("documents.source_id", source_id)
        .limit(1)
        .execute()
    )
    if not points_probe.data:
        raise HTTPException(status_code=404, detail="No content for this teacher")

    if not is_source_servable(db, source_id):
        return {"bio": bio, "works": [], "position": None}

    docs_result = (
        db.table("documents")
        .select("id, title, source_kind, source_type")
        .eq("source_id", source_id)
        .order("created_at", desc=True)
        .limit(TEACHER_CARD_CANDIDATE_DOC_LIMIT)
        .execute()
    )
    all_docs = docs_result.data or []
    # `works` (the bibliography) is the top-N-by-recency slice of this same
    # WHERE/ORDER BY -- byte-identical to what a standalone `.limit(
    # TEACHER_CARD_WORKS_LIMIT)` query would have returned, since it's the
    # same query with a wider LIMIT superset sliced down in Python. Stays
    # built from the FULL unfiltered doc set, same as before this fix.
    works = [{"id": d["id"], "title": d["title"]} for d in all_docs[:TEACHER_CARD_WORKS_LIMIT]]

    if not works:
        return {"bio": bio, "works": [], "position": None}

    # Guard 2 (commentary/word_study exclusion): match_teacher_chunks returns
    # no source_kind/source_type on its rows, so is_commentary_chunk can't be
    # applied to its output directly -- filter at the document level instead,
    # before the RPC call. `works` (the bibliography) stays built from the
    # FULL unfiltered top-N doc set above; this filtered list only narrows
    # what feeds generation. Drawn from the WIDER TEACHER_CARD_CANDIDATE_DOC_LIMIT
    # pool (`all_docs`), not just the narrower `works` window, so a
    # commentary/word_study-heavy teacher's real candidates no longer
    # compete with filtered-out documents for the same small budget.
    non_commentary_docs = [d for d in all_docs if not is_commentary_chunk(d)]
    if not non_commentary_docs:
        return {"bio": bio, "works": works, "position": None}

    try:
        embedding = embed_text(question)
    except Exception:
        logger.exception("Embedding failed for teacher-position query: %s", question[:100])
        raise HTTPException(status_code=500, detail="Embedding service error")

    document_ids = [d["id"] for d in non_commentary_docs]
    try:
        chunk_result = db.rpc("match_teacher_chunks", {
            "query_embedding": embedding,
            "match_count": 15,
            "document_ids": document_ids,
        }).execute()
    except Exception:
        logger.exception("match_teacher_chunks RPC failed for source_id=%s", source_id)
        raise HTTPException(status_code=500, detail="Search service error")

    relevant = [
        c for c in (chunk_result.data or [])
        if c.get("similarity", 0.0) >= TEACHER_POSITION_SIMILARITY_FLOOR
    ]
    relevant.sort(key=lambda c: c["similarity"], reverse=True)
    top_chunks = relevant[:5]

    if not top_chunks:
        return {"bio": bio, "works": works, "position": None}

    excerpts_text = "\n\n".join(
        f'From "{c["title"]}":\n{c["content"]}' for c in top_chunks
    )

    base_system = [
        {"type": "text", "text": _select_teacher_position_prompt(question)},
        {"type": "text", "text": get_guardrails_text()},
    ]

    # Issue 1 fix (2026-08-15, redone). Build a redacted COPY of the bio for
    # the prompt only -- every full corpus teacher name the bio mentions
    # (e.g. "trained under Reinhard Bonnke") is replaced with a generic
    # placeholder BEFORE the model ever sees it, so it cannot echo a
    # specific other-teacher name into `position` in the first place. The
    # `bio` variable itself is untouched and is what the final response
    # dict returns -- real, full, unredacted bibliography content. On a DB
    # failure building the name universe here, fail SOFT (use the original,
    # unredacted bio in the prompt) rather than failing the whole card --
    # the actual safety boundary is Guard 1 below, which is completely
    # unmodified and still runs unconditionally regardless of whether
    # redaction happened.
    try:
        bio_name_universe_for_redaction = build_name_universe(db)
    except Exception:
        logger.exception(
            "build_name_universe failed for bio redaction -- using original bio in prompt, source_id=%s",
            source_id,
        )
        bio_name_universe_for_redaction = frozenset()
    redacted_bio = _redact_bio_for_prompt(bio, bio_name_universe_for_redaction, exclude_name=name)

    user_message = {
        "role": "user",
        "content": (
            f"Teacher: {name}\n\nBio: {redacted_bio}\n\n"
            f"Excerpts:\n{excerpts_text}\n\nQuestion: {question}"
        ),
    }

    def _call_teacher_position_model(client, system_blocks):
        response = client.messages.create(
            model=get_generation_model(),
            max_tokens=400,
            thinking={"type": "disabled"},
            system=system_blocks,
            messages=[user_message],
        )
        return response.content[0].text

    try:
        client = get_anthropic_client()
        position = _call_teacher_position_model(client, base_system)
    except Exception:
        logger.exception("Anthropic call failed for teacher-position synthesis, source_id=%s", source_id)
        raise HTTPException(status_code=500, detail="Answer generation error")

    # Guard 1 (citation grounding): the same regenerate-once-then-refuse check
    # producer.py runs on the main answer path (reference_verifier's
    # ungrounded_prose_teachers), applied here to the teacher-card synthesis.
    # top_chunks already carries author/document_id, which build_retrieval_
    # grounding needs. Any failure in this block (including the retry call
    # itself) fails closed to the standard refusal, mirroring producer.py's
    # own posture -- never a raw crash on the guard, never a silent pass.
    grounding = build_retrieval_grounding(top_chunks, db)
    try:
        name_universe = build_name_universe(db)
        if ungrounded_prose_teachers(position, name_universe, grounding, db):
            permitted_names = sorted({
                (c.get("author") or "").strip() for c in top_chunks
                if (c.get("author") or "").strip()
            })
            names_text = (
                ", ".join(permitted_names) if permitted_names
                else "(no teacher's material was retrieved for this question -- attribute to no one)"
            )
            constraint_block = {
                "type": "text",
                "text": (
                    "STRICT ATTRIBUTION CONSTRAINT (this answer only): you may attribute a claim BY "
                    "NAME ONLY to these teachers, whose material was actually retrieved for this "
                    "question: " + names_text + ". Do NOT name, cite, or attribute any point to any "
                    "other teacher, author, commentator, or ministry -- not even in passing. If a "
                    "point cannot be attributed to a permitted name, state it without attribution. "
                    "This overrides any inclination to add other voices for balance."
                ),
            }
            retry_system = base_system + [constraint_block]
            position2 = _call_teacher_position_model(client, retry_system)
            if ungrounded_prose_teachers(position2, name_universe, grounding, db):
                logger.warning(
                    "get_teacher_card regeneration still credits an ungrounded teacher -- "
                    "clean refusal, source_id=%s", source_id,
                )
                position = _ATTRIBUTION_REFUSAL
            else:
                position = position2
    except Exception:
        logger.exception(
            "get_teacher_card attribution-resolution failed -- refusing cleanly (fail closed), "
            "source_id=%s", source_id,
        )
        position = _ATTRIBUTION_REFUSAL

    return {"bio": bio, "works": works, "position": position}
