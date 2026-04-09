import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.supabase import get_supabase
from app.services.embeddings import embed_text

logger = logging.getLogger(__name__)

INCLUDE_COPYRIGHTED = os.environ.get("INCLUDE_COPYRIGHTED", "true").lower() == "true"

router = APIRouter()


@router.get("")
async def search(q: str = Query(..., description="Search query")):
    try:
        embedding = embed_text(q)
        db = get_supabase()

        chunks_result = db.rpc("match_chunks", {
            "query_embedding": embedding,
            "match_count": 10,
            "include_copyrighted": INCLUDE_COPYRIGHTED,
        }).execute()

        chunks = chunks_result.data
        doc_ids = list({c["document_id"] for c in chunks})
        documents_result = db.table("documents").select("*").in_("id", doc_ids).execute()

        return {
            "documents": documents_result.data,
            "chunks": chunks,
        }
    except Exception:
        logger.exception("Unhandled error in /search endpoint")
        raise HTTPException(status_code=500, detail="An internal error occurred")


def _strip_metadata_header(text: Optional[str]) -> Optional[str]:
    """Remove everything up to and including the first ']' character."""
    if not text:
        return text
    idx = text.find("]")
    if idx != -1:
        return text[idx + 1:].lstrip()
    return text


def _clean_author(author: Optional[str]) -> Optional[str]:
    """Truncate author at opening parenthesis."""
    if not author:
        return author
    if "(" in author:
        return author[:author.index("(")].rstrip() or None
    return author


@router.get("/documents")
async def search_documents(
    q: Optional[str] = Query(None, description="Keyword search query"),
    author: Optional[str] = Query(None, description="Author name filter"),
    source_kind: Optional[str] = Query("magazine_article", description="Filter by source_kind"),
    include_copyrighted: bool = Query(True, description="Include copyrighted content"),
):
    try:
        db = get_supabase()

        result = db.rpc("search_documents", {
            "query_text": q,
            "author_filter": author,
            "source_kind_filter": source_kind,
            "include_copyrighted": include_copyrighted,
        }).execute()

        results = []
        for row in result.data:
            snippet = row.get("highlighted_snippet")
            if snippet:
                snippet = _strip_metadata_header(snippet)
            results.append({
                "id": row["id"],
                "title": row.get("title"),
                "author": _clean_author(row.get("author")),
                "issue": row.get("issue"),
                "year": row.get("year"),
                "highlighted_snippet": snippet,
                "rank": row.get("rank"),
            })

        return {
            "results": results,
            "count": len(results),
        }
    except Exception:
        logger.exception("Unhandled error in /search/documents endpoint")
        raise HTTPException(status_code=500, detail="An internal error occurred")
