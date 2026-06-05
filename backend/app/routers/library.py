import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/books")
async def list_books(
    q: Optional[str] = Query(None, description="Search title, author, or description"),
):
    """Return all books, optionally filtered by a text query."""
    try:
        db = get_supabase()
        query = (
            db.table("books")
            .select("id, title, author, description, topic_tags, created_at")
            .order("author")
            .order("title")
        )

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
