import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()


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
            .select("id, title, author, description, topic_tags, created_at, era")
            .order("author")
            .order("title")
        )
        if era:
            query = query.eq("era", era)
        if author:
            query = query.ilike("author", f"%{author}%")

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
