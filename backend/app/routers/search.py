import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.supabase import get_supabase
from app.services.embeddings import embed_text

logger = logging.getLogger(__name__)

INCLUDE_COPYRIGHTED = os.environ.get("INCLUDE_COPYRIGHTED", "true").lower() == "true"

router = APIRouter()


def _gated_source_ids(db) -> list:
    """Resolve source_ids currently eligible under the license gate -- mirrors
    the safe_mode + EXISTS(sources) clause added to the retrieval RPCs
    (migrations 049, 056). browse_documents queries `documents` directly with
    no RPC in between, so the gate is applied here as an explicit source_id
    allowlist instead of a SQL EXISTS clause."""
    safe_mode_result = (
        db.table("app_settings").select("value").eq("key", "safe_mode").limit(1).execute()
    )
    safe_mode_on = bool(safe_mode_result.data) and safe_mode_result.data[0]["value"] == "on"

    sources_result = db.table("sources").select("id, license_status, visibility").execute()
    allowed_ids = []
    for s in (sources_result.data or []):
        if s.get("license_status") in ("public_domain", "owned"):
            allowed_ids.append(s["id"])
        elif not safe_mode_on and s.get("visibility") == "shown":
            allowed_ids.append(s["id"])
    return allowed_ids


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


def _fetch_descriptions(db, doc_ids: list) -> dict:
    """Fetch clean descriptions from first chunks for a list of document IDs."""
    if not doc_ids:
        return {}
    first_chunks = (
        db.table("chunks")
        .select("document_id, content, chunk_index")
        .in_("document_id", doc_ids)
        .eq("chunk_index", 0)
        .execute()
    )
    desc_map = {}
    for c in first_chunks.data:
        desc = _extract_description(c.get("content"))
        if desc:
            desc_map[c["document_id"]] = desc
    return desc_map


def _extract_description(chunk_content: Optional[str], max_len: int = 150) -> Optional[str]:
    """Extract a clean opening sentence from chunk content, stripping metadata headers."""
    if not chunk_content:
        return None
    lines = chunk_content.strip().split("\n")
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip metadata: lines starting with [, lines with | (metadata separators),
        # all-caps lines (titles), markdown headings, frontmatter-like patterns
        if stripped.startswith("[") or stripped.startswith("#"):
            continue
        if "|" in stripped and len(stripped.split("|")) >= 3:
            continue
        if stripped == stripped.upper() and len(stripped) > 3:
            continue
        if stripped.startswith("---"):
            continue
        if ":" in stripped and len(stripped) < 60 and stripped.index(":") < 20:
            continue
        clean_lines.append(stripped)
    text = " ".join(clean_lines)
    if not text:
        return None
    if len(text) > max_len:
        # Try to break at sentence boundary
        dot = text.rfind(". ", 0, max_len)
        if dot > 60:
            return text[:dot + 1]
        return text[:max_len] + "\u2026"
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
    era: Optional[str] = Query(None, description="Filter by era: 'classic' or 'contemporary'"),
):
    try:
        db = get_supabase()

        # For multi-author, pass first author to RPC and post-filter the rest
        authors = [a.strip() for a in author.split(",") if a.strip()] if author else []
        rpc_author = authors[0] if len(authors) == 1 else None

        # include_copyrighted is server-controlled, not client-controllable --
        # was previously Query(True), letting any caller override it. The
        # search_documents RPC also enforces the license/visibility gate as of
        # migration 056, independent of this flag.
        result = db.rpc("search_documents", {
            "query_text": q,
            "author_filter": rpc_author,
            "source_kind_filter": source_kind,
            "include_copyrighted": INCLUDE_COPYRIGHTED,
        }).execute()

        # Fetch topic_tags + era for returned documents
        doc_ids = [row["id"] for row in result.data]
        extra_map = {}
        if doc_ids:
            extra_result = db.table("documents").select("id, topic_tags, era, source_name, source_kind, content_summary").in_("id", doc_ids).execute()
            extra_map = {r["id"]: r for r in extra_result.data}

        # Identify New Wine docs for description fetching
        nw_ids = [
            did for did in doc_ids
            if "new wine" in (extra_map.get(did, {}).get("source_name") or "").lower()
        ]
        desc_map = _fetch_descriptions(db, nw_ids)

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
                "source_kind": doc_extra.get("source_kind"),
                "source_name": doc_extra.get("source_name"),
                "description": desc_map.get(row["id"]),
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
    era: Optional[str] = Query(None, description="Filter by era: 'classic' or 'contemporary'"),
    author: Optional[str] = Query(None, description="Author name filter"),
):
    """List all documents of a given source_kind, ordered by year/issue descending.

    Queries `documents` directly with no RPC, so unlike search_documents this
    endpoint doesn't inherit the license gate from migration 056 automatically
    -- _gated_source_ids() applies the same eligibility rule as an explicit
    source_id allowlist. include_copyrighted is server-controlled, not
    client-controllable (was previously Query(True)).
    """
    try:
        db = get_supabase()
        gated_ids = _gated_source_ids(db)
        query = (
            db.table("documents")
            .select("id, title, author, issue, year, topic_tags, source_kind, source_name, content_summary")
            .in_("source_id", gated_ids)
            .order("year", desc=True)
            .order("issue", desc=True)
        )
        if source_kind:
            query = query.eq("source_kind", source_kind)
        if not INCLUDE_COPYRIGHTED:
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

        # Fetch descriptions for New Wine docs
        nw_ids = [
            row["id"] for row in result.data
            if "new wine" in (row.get("source_name") or "").lower()
        ]
        desc_map = _fetch_descriptions(db, nw_ids)

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
                    "source_name": row.get("source_name"),
                    "description": desc_map.get(row["id"]),
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
