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
from app.services.llm_client import get_anthropic_client, get_guardrails_text

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

TEACHER_POSITION_PROMPT = (
    "You are summarizing what a specific teacher has said on a topic, based "
    "only on the excerpts provided below. Paraphrase in your own words — "
    "never quote more than a few words verbatim. Cite specific works by "
    "title when relevant. If the excerpts don't address the question, say "
    "so plainly rather than guessing or generalizing. Do not editorialize "
    "or add your own theological commentary — represent only what appears "
    "in the source material."
)


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

    if not is_source_servable(db, source_id):
        return {"bio": bio, "works": [], "position": None}

    docs_result = (
        db.table("documents")
        .select("id, title")
        .eq("source_id", source_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    works = [{"id": d["id"], "title": d["title"]} for d in (docs_result.data or [])]

    if not works:
        return {"bio": bio, "works": [], "position": None}

    try:
        embedding = embed_text(question)
    except Exception:
        logger.exception("Embedding failed for teacher-position query: %s", question[:100])
        raise HTTPException(status_code=500, detail="Embedding service error")

    document_ids = [w["id"] for w in works]
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

    try:
        client = get_anthropic_client()
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            system=[
                {"type": "text", "text": TEACHER_POSITION_PROMPT},
                {"type": "text", "text": get_guardrails_text()},
            ],
            messages=[{
                "role": "user",
                "content": (
                    f"Teacher: {name}\n\nBio: {bio}\n\n"
                    f"Excerpts:\n{excerpts_text}\n\nQuestion: {question}"
                ),
            }],
        )
        position = response.content[0].text
    except Exception:
        logger.exception("Anthropic call failed for teacher-position synthesis, source_id=%s", source_id)
        raise HTTPException(status_code=500, detail="Answer generation error")

    return {"bio": bio, "works": works, "position": position}
