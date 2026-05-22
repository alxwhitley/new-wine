from __future__ import annotations

import re
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from app.db.supabase import get_supabase
from app.services.embeddings import embed_text

logger = logging.getLogger(__name__)

router = APIRouter()

CORPUS_SOURCE_KINDS = {"sermon_transcript", "magazine_article", "word_study"}

# Full 66-book mapping: common names/abbreviations -> verse_id prefix
BOOK_MAP = {
    # Old Testament
    "genesis": "GEN", "gen": "GEN",
    "exodus": "EXO", "exo": "EXO", "exod": "EXO",
    "leviticus": "LEV", "lev": "LEV",
    "numbers": "NUM", "num": "NUM",
    "deuteronomy": "DEU", "deut": "DEU", "deu": "DEU",
    "joshua": "JOS", "josh": "JOS", "jos": "JOS",
    "judges": "JDG", "judg": "JDG", "jdg": "JDG",
    "ruth": "RUT", "rut": "RUT",
    "1 samuel": "1SA", "1samuel": "1SA", "1 sam": "1SA", "1sam": "1SA", "1sa": "1SA",
    "2 samuel": "2SA", "2samuel": "2SA", "2 sam": "2SA", "2sam": "2SA", "2sa": "2SA",
    "1 kings": "1KI", "1kings": "1KI", "1 kgs": "1KI", "1kgs": "1KI", "1ki": "1KI",
    "2 kings": "2KI", "2kings": "2KI", "2 kgs": "2KI", "2kgs": "2KI", "2ki": "2KI",
    "1 chronicles": "1CH", "1chronicles": "1CH", "1 chr": "1CH", "1chr": "1CH", "1ch": "1CH",
    "2 chronicles": "2CH", "2chronicles": "2CH", "2 chr": "2CH", "2chr": "2CH", "2ch": "2CH",
    "ezra": "EZR", "ezr": "EZR",
    "nehemiah": "NEH", "neh": "NEH",
    "esther": "EST", "esth": "EST", "est": "EST",
    "job": "JOB",
    "psalms": "PSA", "psalm": "PSA", "psa": "PSA", "ps": "PSA",
    "proverbs": "PRO", "prov": "PRO", "pro": "PRO",
    "ecclesiastes": "ECC", "eccl": "ECC", "ecc": "ECC",
    "song of solomon": "SNG", "song of songs": "SNG", "song": "SNG", "sng": "SNG", "sos": "SNG",
    "isaiah": "ISA", "isa": "ISA",
    "jeremiah": "JER", "jer": "JER",
    "lamentations": "LAM", "lam": "LAM",
    "ezekiel": "EZK", "ezek": "EZK", "ezk": "EZK",
    "daniel": "DAN", "dan": "DAN",
    "hosea": "HOS", "hos": "HOS",
    "joel": "JOL", "jol": "JOL",
    "amos": "AMO", "amo": "AMO",
    "obadiah": "OBA", "obad": "OBA", "oba": "OBA",
    "jonah": "JON", "jon": "JON",
    "micah": "MIC", "mic": "MIC",
    "nahum": "NAM", "nah": "NAM", "nam": "NAM",
    "habakkuk": "HAB", "hab": "HAB",
    "zephaniah": "ZEP", "zeph": "ZEP", "zep": "ZEP",
    "haggai": "HAG", "hag": "HAG",
    "zechariah": "ZEC", "zech": "ZEC", "zec": "ZEC",
    "malachi": "MAL", "mal": "MAL",
    # New Testament
    "matthew": "MAT", "matt": "MAT", "mat": "MAT",
    "mark": "MRK", "mrk": "MRK",
    "luke": "LUK", "luk": "LUK",
    "john": "JHN", "jhn": "JHN",
    "acts": "ACT", "act": "ACT",
    "romans": "ROM", "rom": "ROM",
    "1 corinthians": "1CO", "1corinthians": "1CO", "1 cor": "1CO", "1cor": "1CO", "1co": "1CO",
    "2 corinthians": "2CO", "2corinthians": "2CO", "2 cor": "2CO", "2cor": "2CO", "2co": "2CO",
    "galatians": "GAL", "gal": "GAL",
    "ephesians": "EPH", "eph": "EPH",
    "philippians": "PHP", "phil": "PHP", "php": "PHP",
    "colossians": "COL", "col": "COL",
    "1 thessalonians": "1TH", "1thessalonians": "1TH", "1 thess": "1TH", "1thess": "1TH", "1th": "1TH",
    "2 thessalonians": "2TH", "2thessalonians": "2TH", "2 thess": "2TH", "2thess": "2TH", "2th": "2TH",
    "1 timothy": "1TI", "1timothy": "1TI", "1 tim": "1TI", "1tim": "1TI", "1ti": "1TI",
    "2 timothy": "2TI", "2timothy": "2TI", "2 tim": "2TI", "2tim": "2TI", "2ti": "2TI",
    "titus": "TIT", "tit": "TIT",
    "philemon": "PHM", "phlm": "PHM", "phm": "PHM",
    "hebrews": "HEB", "heb": "HEB",
    "james": "JAS", "jas": "JAS",
    "1 peter": "1PE", "1peter": "1PE", "1 pet": "1PE", "1pet": "1PE", "1pe": "1PE",
    "2 peter": "2PE", "2peter": "2PE", "2 pet": "2PE", "2pet": "2PE", "2pe": "2PE",
    "1 john": "1JN", "1john": "1JN", "1 jn": "1JN", "1jn": "1JN",
    "2 john": "2JN", "2john": "2JN", "2 jn": "2JN", "2jn": "2JN",
    "3 john": "3JN", "3john": "3JN", "3 jn": "3JN", "3jn": "3JN",
    "jude": "JUD", "jud": "JUD",
    "revelation": "REV", "rev": "REV",
}

# Reverse mapping: abbreviation -> canonical book name
ABBREV_TO_NAME = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers",
    "DEU": "Deuteronomy", "JOS": "Joshua", "JDG": "Judges", "RUT": "Ruth",
    "1SA": "1 Samuel", "2SA": "2 Samuel", "1KI": "1 Kings", "2KI": "2 Kings",
    "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra", "NEH": "Nehemiah",
    "EST": "Esther", "JOB": "Job", "PSA": "Psalms", "PRO": "Proverbs",
    "ECC": "Ecclesiastes", "SNG": "Song of Solomon", "ISA": "Isaiah", "JER": "Jeremiah",
    "LAM": "Lamentations", "EZK": "Ezekiel", "DAN": "Daniel", "HOS": "Hosea",
    "JOL": "Joel", "AMO": "Amos", "OBA": "Obadiah", "JON": "Jonah",
    "MIC": "Micah", "NAM": "Nahum", "HAB": "Habakkuk", "ZEP": "Zephaniah",
    "HAG": "Haggai", "ZEC": "Zechariah", "MAL": "Malachi",
    "MAT": "Matthew", "MRK": "Mark", "LUK": "Luke", "JHN": "John",
    "ACT": "Acts", "ROM": "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians",
    "GAL": "Galatians", "EPH": "Ephesians", "PHP": "Philippians", "COL": "Colossians",
    "1TH": "1 Thessalonians", "2TH": "2 Thessalonians", "1TI": "1 Timothy",
    "2TI": "2 Timothy", "TIT": "Titus", "PHM": "Philemon", "HEB": "Hebrews",
    "JAS": "James", "1PE": "1 Peter", "2PE": "2 Peter", "1JN": "1 John",
    "2JN": "2 John", "3JN": "3 John", "JUD": "Jude", "REV": "Revelation",
}


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
            "include_copyrighted": True,
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


@router.get("/commentary")
async def get_commentary(
    verse_text: str = Query(..., description="Full English verse text"),
):
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
            "include_copyrighted": True,
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
        })
        if len(results) >= 5:
            break

    return {"results": results}
