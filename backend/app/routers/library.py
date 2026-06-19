import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/doc-meta")
async def get_doc_meta(ids: str = Query(..., description="Comma-separated document IDs, max 20")):
    """Return lightweight document metadata for specific IDs (no chunks). Used by Featured section."""
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    if not id_list:
        return {"results": []}
    if len(id_list) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 IDs per request")
    try:
        db = get_supabase()
        result = (
            db.table("documents")
            .select("id, title, author, source_kind, topic_tags, year, era, content_summary, image_url")
            .in_("id", id_list)
            .execute()
        )
        order_map = {doc_id: i for i, doc_id in enumerate(id_list)}
        rows = sorted(result.data or [], key=lambda r: order_map.get(r["id"], 999))
        return {"results": rows}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /library/doc-meta endpoint")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/recent")
async def list_recent_documents(limit: int = Query(6, description="Maximum results to return")):
    """Return recently added non-magazine documents ordered by created_at DESC."""
    try:
        db = get_supabase()
        result = (
            db.table("documents")
            .select("id, title, author, source_kind, topic_tags, year, era, content_summary")
            .neq("source_kind", "magazine_article")
            .neq("source_kind", "commentary")
            .neq("source_kind", "lexicon")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {"results": result.data or []}
    except Exception:
        logger.exception("Unhandled error in /library/recent endpoint")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/counts")
async def get_source_counts():
    """Return document counts per source type for the Discover browse tiles."""
    try:
        db = get_supabase()
        mag = (
            db.table("documents")
            .select("id", count="exact")
            .eq("source_kind", "magazine_article")
            .limit(0)
            .execute()
        )
        sermons = (
            db.table("documents")
            .select("id", count="exact")
            .eq("source_kind", "sermon_transcript")
            .limit(0)
            .execute()
        )
        books = (
            db.table("books")
            .select("id", count="exact")
            .limit(0)
            .execute()
        )
        return {
            "magazine_article": mag.count or 0,
            "sermon_transcript": sermons.count or 0,
            "books": books.count or 0,
        }
    except Exception:
        logger.exception("Unhandled error in /library/counts endpoint")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/book/{doc_id}")
async def get_book_excerpts(doc_id: str):
    """Return book document metadata and quotes (or chunks as fallback) for the excerpt reader."""
    try:
        db = get_supabase()

        doc = db.table("documents").select("id, title, author, era").eq("id", doc_id).limit(1).execute()
        if not doc.data:
            raise HTTPException(status_code=404, detail="Document not found")

        # Prefer pre-extracted quotes; fall back to raw chunks
        quotes = (
            db.table("book_quotes")
            .select("id, quote_text, quote_index")
            .eq("document_id", doc_id)
            .order("quote_index")
            .execute()
        )

        if quotes.data:
            return {
                "document": doc.data[0],
                "quotes": quotes.data,
            }

        # Fallback: return chunks
        chunks = (
            db.table("chunks")
            .select("id, chunk_index, content")
            .eq("document_id", doc_id)
            .order("chunk_index")
            .execute()
        )

        return {
            "document": doc.data[0],
            "chunks": chunks.data,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /library/book/{id} endpoint")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/books")
async def list_books(
    q: Optional[str] = Query(None, description="Search title, author, or description"),
    era: Optional[str] = Query(None, description="Filter by era: 'classic' or 'contemporary'"),
    author: Optional[str] = Query(None, description="Filter by author name"),
):
    """Return all books, optionally filtered by a text query, era, or author."""
    try:
        db = get_supabase()
        query = (
            db.table("books")
            .select("id, title, author, description, topic_tags, created_at, era, document_id")
            .order("author")
            .order("title")
        )
        if era:
            query = query.eq("era", era)
        if author:
            authors = [a.strip() for a in author.split(",") if a.strip()]
            if len(authors) == 1:
                query = query.ilike("author", f"%{authors[0]}%")
            elif authors:
                or_clauses = ",".join(f"author.ilike.%{a}%" for a in authors)
                query = query.or_(or_clauses)

        result = query.execute()

        rows = result.data
        if q:
            q_lower = q.lower()
            rows = [
                r for r in rows
                if q_lower in (r.get("title") or "").lower()
                or q_lower in (r.get("author") or "").lower()
                or q_lower in (r.get("description") or "").lower()
            ]

        return {
            "results": rows,
            "count": len(rows),
        }
    except Exception:
        logger.exception("Unhandled error in /library/books endpoint")
        raise HTTPException(status_code=500, detail="An internal error occurred")
