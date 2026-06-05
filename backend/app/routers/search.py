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


# To include sermon transcripts in search results, change the default below to None
# source_kind: Optional[str] = Query(None, description="Filter by source_kind"),
@router.get("/documents")
async def search_documents(
    q: Optional[str] = Query(None, description="Keyword search query"),
    author: Optional[str] = Query(None, description="Author name filter"),
    source_kind: Optional[str] = Query("magazine_article", description="Filter by source_kind — excludes sermon_transcript by default"),
    include_copyrighted: bool = Query(True, description="Include copyrighted content"),
    era: Optional[str] = Query(None, description="Filter by era: 'classic' or 'contemporary'"),
):
    try:
        db = get_supabase()

        # For multi-author, pass first author to RPC and post-filter the rest
        authors = [a.strip() for a in author.split(",") if a.strip()] if author else []
        rpc_author = authors[0] if len(authors) == 1 else None

        result = db.rpc("search_documents", {
            "query_text": q,
            "author_filter": rpc_author,
            "source_kind_filter": source_kind,
            "include_copyrighted": include_copyrighted,
        }).execute()

        # Fetch topic_tags + era for returned documents
        doc_ids = [row["id"] for row in result.data]
        extra_map = {}
        if doc_ids:
            extra_result = db.table("documents").select("id, topic_tags, era").in_("id", doc_ids).execute()
            extra_map = {r["id"]: r for r in extra_result.data}

        results = []
        for row in result.data:
            doc_extra = extra_map.get(row["id"], {})
            # Apply era filter (RPC doesn't support it natively)
            if era and doc_extra.get("era") != era:
                continue
            # Apply multi-author filter (post-filter when >1 author)
            if len(authors) > 1:
                row_author = (row.get("author") or "").lower()
                if not any(a.lower() in row_author for a in authors):
                    continue
            snippet = row.get("highlighted_snippet")
            if snippet:
                snippet = _strip_metadata_header(snippet)
            results.append({
                "id": row["id"],
                "title": row.get("title"),
                "author": _clean_author(row.get("author")),
                "issue": row.get("issue"),
                "year": row.get("year"),
                "topic_tags": doc_extra.get("topic_tags") or [],
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


@router.get("/documents/browse")
async def browse_documents(
    source_kind: Optional[str] = Query("magazine_article", description="Filter by source_kind"),
    include_copyrighted: bool = Query(True, description="Include copyrighted content"),
    era: Optional[str] = Query(None, description="Filter by era: 'classic' or 'contemporary'"),
    author: Optional[str] = Query(None, description="Author name filter"),
):
    """List all documents of a given source_kind, ordered by year/issue descending."""
    try:
        db = get_supabase()
        query = (
            db.table("documents")
            .select("id, title, author, issue, year, topic_tags, source_kind")
            .order("year", desc=True)
            .order("issue", desc=True)
        )
        if source_kind:
            query = query.eq("source_kind", source_kind)
        if not include_copyrighted:
            query = query.eq("is_copyrighted", False)
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

        return {
            "results": [
                {
                    "id": row["id"],
                    "title": row.get("title"),
                    "author": _clean_author(row.get("author")),
                    "issue": row.get("issue"),
                    "year": row.get("year"),
                    "topic_tags": row.get("topic_tags") or [],
                    "source_kind": row.get("source_kind"),
                    "highlighted_snippet": None,
                    "rank": 0,
                }
                for row in result.data
            ],
            "count": len(result.data),
        }
    except Exception:
        logger.exception("Unhandled error in /search/documents/browse endpoint")
        raise HTTPException(status_code=500, detail="An internal error occurred")
