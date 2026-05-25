from __future__ import annotations

import re
import logging
from typing import Optional, List

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


@router.get("/interlinear")
async def get_interlinear(verse_id: str = Query(..., description="SBL verse ID, e.g. 'JHN.1.1'")):
    db = get_supabase()
    result = (
        db.table("interlinear_words")
        .select("greek_word, transliteration, strongs_number, english_gloss, morphology, word_position")
        .eq("verse_id", verse_id)
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


@router.get("/commentary")
async def get_commentary(
    verse_text: str = Query(..., description="Full English verse text"),
):
    filters = get_disabled_filters()

    try:
        embedding = embed_text(verse_text)
    except Exception:
        logger.exception("Embedding failed for commentary query: %s", verse_text[:100])
        raise HTTPException(status_code=500, detail="Embedding service error")

    db = get_supabase()

    try:
        result = db.rpc("match_chunks", {
            "query_embedding": embedding,
            "match_count": 20,
            "include_copyrighted": filters["include_copyrighted"],
        }).execute()
    except Exception:
        logger.exception("match_chunks RPC failed for commentary query")
        raise HTTPException(status_code=500, detail="Search service error")

    seen_docs = set()
    results = []
    for chunk in (result.data or []):
        if chunk.get("citation_mode") != "citable":
            continue
        if chunk.get("source_kind") != "commentary":
            continue
        if is_chunk_disabled(chunk, filters):
            continue
        doc_id = chunk.get("document_id")
        if doc_id in seen_docs:
            continue
        seen_docs.add(doc_id)
        content = chunk.get("content", "")
        excerpt = content[:200].rsplit(" ", 1)[0] + "..." if len(content) > 200 else content
        results.append({
            "document_id": doc_id,
            "title": chunk.get("title", ""),
            "author": chunk.get("author", ""),
            "source_kind": chunk.get("source_kind", ""),
            "excerpt": excerpt,
            "content": content,
        })
        if len(results) >= 5:
            break

    return {"results": results}
