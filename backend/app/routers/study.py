from __future__ import annotations

import os
import re
import logging
from typing import Optional, List
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query

from app.constants import ABBREV_TO_NAME, BOOK_MAP
from app.db.supabase import get_supabase
from app.services.embeddings import embed_text
from app.services.source_filter import get_disabled_filters, is_chunk_disabled

logger = logging.getLogger(__name__)

router = APIRouter()

CORPUS_SOURCE_KINDS = {"sermon_transcript", "magazine_article", "word_study", "commentary"}


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
async def get_lexicon_entry(strongs: str = Query(..., description="Strong's number, e.g. 'G3056'")):
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


def _fetch_neighbor_content(db, document_id, chunk_index):
    # type: (object, str, int) -> str
    """Fetch chunk_index-1, chunk_index, chunk_index+1 content, concatenated."""
    indices = [chunk_index - 1, chunk_index, chunk_index + 1]
    result = (
        db.table("chunks")
        .select("chunk_index, content")
        .eq("document_id", document_id)
        .in_("chunk_index", indices)
        .order("chunk_index")
        .execute()
    )
    parts = [row["content"] for row in (result.data or [])]
    return "\n\n".join(parts)


@router.get("/commentary")
async def get_commentary(
    verse_text: str = Query(..., description="Full English verse text"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    verse_id: Optional[str] = Query(None, description="Verse ID like JHN.3.16 — enables sermon results"),
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

    # --- Step 1+2: Book-level pre-filter via bible_references ---
    book_doc_ids = set()  # type: set
    if verse_id:
        book_code = verse_id.split(".")[0] if "." in verse_id else ""
        book_name = ABBREV_TO_NAME.get(book_code)
        if book_name:
            try:
                import psycopg2
                parsed_db = urlparse(os.environ["SUPABASE_DB_URL"])
                conn = psycopg2.connect(
                    host=parsed_db.hostname,
                    port=parsed_db.port,
                    user=parsed_db.username,
                    password=parsed_db.password,
                    dbname=parsed_db.path.lstrip("/"),
                )
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM documents WHERE source_kind = 'commentary' AND citation_mode = 'citable' AND bible_references && %s",
                    ([book_name],),
                )
                rows = cur.fetchall()
                cur.close()
                conn.close()
                book_doc_ids = {str(r[0]) for r in rows}
            except Exception:
                logger.exception("bible_references book lookup failed for %s", book_name)

    # --- Step 3: Vector search, filtered to book docs when available ---
    try:
        result = db.rpc("match_chunks", {
            "query_embedding": embedding,
            "match_count": 30,
            "include_copyrighted": filters["include_copyrighted"],
        }).execute()
    except Exception:
        logger.exception("match_chunks RPC failed for commentary query")
        raise HTTPException(status_code=500, detail="Search service error")

    for chunk in (result.data or []):
        if chunk.get("citation_mode") != "citable":
            continue
        if chunk.get("source_kind") != "commentary":
            continue
        if book_doc_ids and chunk.get("document_id") not in book_doc_ids:
            continue
        if is_chunk_disabled(chunk, study_filters):
            continue
        doc_id = chunk.get("document_id")
        if doc_id in seen_docs:
            continue
        seen_docs.add(doc_id)
        content = chunk.get("content", "")
        excerpt = content[:200].rsplit(" ", 1)[0] + "..." if len(content) > 200 else content
        similarity = chunk.get("similarity", 0.0)
        author = chunk.get("author", "")
        boost = COMMENTARY_AUTHOR_BOOST.get(author.lower(), COMMENTARY_DEFAULT_PENALTY)
        results.append({
            "document_id": doc_id,
            "title": chunk.get("title", ""),
            "author": author,
            "source_kind": chunk.get("source_kind", ""),
            "excerpt": excerpt,
            "content": content,
            "_score": similarity + boost,
        })

    # --- Sermon results (new path, requires verse_id) ---
    if verse_id:
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

                # Neighbor chunk expansion + build results
                for sc in top_sermons:
                    display_content = _fetch_neighbor_content(
                        db, sc["document_id"], sc["chunk_index"]
                    )
                    excerpt = display_content[:200].rsplit(" ", 1)[0] + "..." if len(display_content) > 200 else display_content
                    results.append({
                        "document_id": sc["document_id"],
                        "title": sc.get("title", ""),
                        "author": sc.get("author", ""),
                        "source_kind": "sermon_transcript",
                        "excerpt": excerpt,
                        "content": display_content,
                        "_score": 0.75,
                    })
            except Exception:
                logger.exception("Sermon chunk query failed for verse_id=%s", verse_id)

    results.sort(key=lambda r: r["_score"], reverse=True)
    for r in results:
        del r["_score"]

    page = results[offset:offset + 3]
    has_more = len(results) > offset + 3

    return {"results": page, "has_more": has_more, "total": len(results)}
