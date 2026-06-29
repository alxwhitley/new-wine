from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth import require_admin_role
from app.db.supabase import get_supabase
from app.services.chunker import chunk_text
from app.services.embeddings import embed_text

logger = logging.getLogger(__name__)

router = APIRouter()

_SENTINEL_SOURCE_ID = "267a09ac-76f3-43fb-901f-3015aef88e22"
_VALID_LICENSE_STATUS = frozenset({"public_domain", "owned", "licensed", "unlicensed"})
_VALID_VISIBILITY = frozenset({"shown", "hidden"})


class EditDocumentBody(BaseModel):
    title: str
    author: str
    content: str


class SetVisibilityBody(BaseModel):
    visibility: str


class SetLicenseStatusBody(BaseModel):
    license_status: str


class SetSafeModeBody(BaseModel):
    value: str


@router.get("/sources")
async def list_sources(request: Request, user_id: str = Depends(require_admin_role)):
    db = get_supabase()

    rows = db.table("source_toggles").select("*").order("created_at").execute()
    toggles = rows.data or []

    results = []
    for toggle in toggles:
        identifier = toggle["source_identifier"]
        id_type = toggle["identifier_type"]

        doc_count = None
        try:
            if id_type == "source_kind":
                count_result = (
                    db.table("documents")
                    .select("id", count="exact")
                    .eq("source_kind", identifier)
                    .execute()
                )
                doc_count = count_result.count
            elif id_type == "source_name":
                count_result = (
                    db.table("documents")
                    .select("id", count="exact")
                    .ilike("author", "%" + identifier + "%")
                    .execute()
                )
                doc_count = count_result.count
        except Exception:
            logger.warning("Failed to count docs for %s/%s", id_type, identifier)

        results.append({
            "id": toggle["id"],
            "source_identifier": identifier,
            "identifier_type": id_type,
            "label": toggle["label"],
            "enabled": toggle["enabled"],
            "doc_count": doc_count,
        })

    return {"sources": results}


@router.get("/document/{doc_id}/edit")
async def get_document_for_edit(doc_id: str, request: Request, user_id: str = Depends(require_admin_role)):
    """Return document fields and reassembled content for editing."""
    db = get_supabase()

    doc = db.table("documents").select("title, author, source_kind, url").eq("id", doc_id).limit(1).execute()
    if not doc.data:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = (
        db.table("chunks")
        .select("content, rewritten_content, chunk_index")
        .eq("document_id", doc_id)
        .order("chunk_index")
        .execute()
    )

    # Reassemble: prefer rewritten_content, fall back to content
    parts = []
    for c in chunks.data:
        text = c.get("rewritten_content") or c.get("content") or ""
        if text.strip():
            parts.append(text.strip())
    content = "\n\n".join(parts)

    row = doc.data[0]
    return {
        "title": row.get("title"),
        "author": row.get("author"),
        "source_kind": row.get("source_kind"),
        "url": row.get("url"),
        "content": content,
    }


@router.put("/document/{doc_id}/edit")
async def update_document(doc_id: str, body: EditDocumentBody, request: Request, user_id: str = Depends(require_admin_role)):
    """Update document metadata and re-chunk + re-embed content."""
    db = get_supabase()

    # Verify document exists
    doc = db.table("documents").select("id, author").eq("id", doc_id).limit(1).execute()
    if not doc.data:
        raise HTTPException(status_code=404, detail="Document not found")

    # Update document metadata
    db.table("documents").update({
        "title": body.title,
        "author": body.author,
    }).eq("id", doc_id).execute()

    # Re-chunk content
    chunks = chunk_text(body.content, chunk_target=550, overlap=80)
    if not chunks:
        chunks = [body.content.strip()] if body.content.strip() else []

    # Delete existing chunks
    db.table("chunks").delete().eq("document_id", doc_id).execute()

    # Embed and insert new chunks
    author = body.author or ""
    for idx, text in enumerate(chunks):
        logger.info("[ADMIN] Embedding chunk %d/%d for doc %s", idx + 1, len(chunks), doc_id)
        embedding = embed_text(f"Author: {author} | {text}")
        db.table("chunks").insert({
            "id": str(uuid.uuid4()),
            "document_id": doc_id,
            "content": text,
            "rewritten_content": text,
            "embedding": embedding,
            "chunk_index": idx,
        }).execute()

    logger.info("[ADMIN] Document %s updated by user %s — %d chunks", doc_id, user_id, len(chunks))
    return {"success": True, "chunk_count": len(chunks)}


@router.delete("/document/{doc_id}")
async def delete_document(doc_id: str, request: Request, user_id: str = Depends(require_admin_role)):
    """Delete a document and its cascade (chunks, propositions). Admin only.

    Writes to removed_urls before deleting when the document has a URL so the
    URL is blocked from being re-ingested on the next pipeline run.
    """
    db = get_supabase()

    # Fetch document — need url/title/original_title for the blocklist write
    doc_q = db.table("documents").select("id, url, title, original_title").eq("id", doc_id).limit(1).execute()
    if not doc_q.data:
        raise HTTPException(status_code=404, detail="Document not found")

    doc_row = doc_q.data[0]
    doc_url = doc_row.get("url")

    # Write to removed_urls BEFORE deleting so a concurrent re-ingest attempt
    # sees the block record even if the delete is still in flight
    if doc_url:
        db.table("removed_urls").upsert({
            "url": doc_url,
            "document_id": doc_id,
            "title": doc_row.get("title"),
            "original_title": doc_row.get("original_title"),
        }).execute()
        logger.info("[ADMIN] blocked url %s for removed doc %s", doc_url, doc_id)

    # Delete document; chunks + propositions cascade automatically via FK ON DELETE CASCADE
    db.table("documents").delete().eq("id", doc_id).execute()

    logger.info("[ADMIN] Document %s deleted by %s (url_blocked=%s)", doc_id, user_id, bool(doc_url))
    return {"success": True, "deleted": True, "blocked_url": doc_url}


# ── Corpus documents list ───────────────────────────────────────────────────────

@router.get("/corpus/documents")
async def list_corpus_documents(
    request: Request,
    user_id: str = Depends(require_admin_role),
    source_kind: Optional[str] = Query(None),
    source_id: Optional[str] = Query(None),
    license_status: Optional[str] = Query(None),
    visibility: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Paginated, server-side-filtered corpus document list with source join.

    Per-kind stats use a separate bulk fetch aggregated in Python (no N+1).
    License/visibility filters pre-resolve matching source_ids, then filter
    documents by those ids via IN — avoids ambiguous embedded-table filter syntax.
    """
    from collections import Counter
    db = get_supabase()

    # ── 1. Per-kind stats (unfiltered — for the stats header row) ─────────────
    all_kinds = db.table("documents").select("source_kind").execute()
    kind_counts: Counter = Counter(
        r["source_kind"] for r in (all_kinds.data or []) if r.get("source_kind")
    )
    total_all = len(all_kinds.data or [])

    # ── 2. Pre-resolve source_ids if license/visibility filters are active ─────
    source_id_whitelist = None
    if license_status or visibility:
        src_q = db.table("sources").select("id")
        if license_status:
            src_q = src_q.eq("license_status", license_status)
        if visibility:
            src_q = src_q.eq("visibility", visibility)
        src_result = src_q.execute()
        source_id_whitelist = [r["id"] for r in (src_result.data or [])]
        if not source_id_whitelist:
            return {"total": 0, "total_all": total_all, "kind_counts": dict(kind_counts), "rows": []}

    # ── 3. Build paginated docs query with embedded source join ───────────────
    q = db.table("documents").select(
        "id, title, original_title, author, source_kind, url, created_at, "
        "sources!source_id(name, license_status, visibility)",
        count="exact",
    )

    if source_kind:
        q = q.eq("source_kind", source_kind)
    if source_id:
        q = q.eq("source_id", source_id)
    elif source_id_whitelist is not None:
        q = q.in_("source_id", source_id_whitelist)
    if search:
        s = search.replace("%", "\\%")
        q = q.or_(f"title.ilike.%{s}%,original_title.ilike.%{s}%,author.ilike.%{s}%")

    q = q.order("created_at", desc=True).range(offset, offset + limit - 1)
    result = q.execute()

    docs = result.data or []
    total = result.count or 0

    rows = []
    for d in docs:
        src = d.get("sources") or {}
        rows.append({
            "id": d["id"],
            "title": d.get("title"),
            "original_title": d.get("original_title"),
            "author": d.get("author"),
            "source_kind": d.get("source_kind"),
            "source_name": src.get("name"),
            "license_status": src.get("license_status"),
            "visibility": src.get("visibility"),
            "url": d.get("url"),
            "created_at": d.get("created_at"),
        })

    return {
        "total": total,
        "total_all": total_all,
        "kind_counts": dict(kind_counts),
        "rows": rows,
    }


@router.patch("/sources/{toggle_id}")
async def toggle_source(toggle_id: str, request: Request, user_id: str = Depends(require_admin_role)):
    db = get_supabase()

    # Get current state
    current = db.table("source_toggles").select("*").eq("id", toggle_id).limit(1).execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Toggle not found")

    new_enabled = not current.data[0]["enabled"]
    result = (
        db.table("source_toggles")
        .update({"enabled": new_enabled})
        .eq("id", toggle_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update toggle")

    # Invalidate cache
    import app.services.source_filter as sf
    sf._cache = None
    sf._cache_ts = 0.0

    return result.data[0]


# ── License controls ───────────────────────────────────────────────────────────

@router.get("/license-sources")
async def list_license_sources(request: Request, user_id: str = Depends(require_admin_role)):
    """List all sources with license_status, visibility, and doc count.

    Uses two queries (sources + all doc source_ids) instead of N+1 per-source
    count queries — the N+1 pattern caused ~4s response times that timed out in
    production.
    """
    db = get_supabase()

    sources_result = db.table("sources").select("id, name, license_status, visibility").order("name").execute()
    if not sources_result.data:
        logger.warning("[ADMIN] list_license_sources: sources query returned no data")
        return {"sources": []}

    # Single bulk fetch of all document source_ids; aggregate in Python.
    docs_result = db.table("documents").select("source_id").execute()
    from collections import Counter
    doc_counts: Counter = Counter(
        row["source_id"] for row in (docs_result.data or []) if row.get("source_id")
    )

    results = [
        {
            "id": src["id"],
            "name": src["name"],
            "license_status": src["license_status"],
            "visibility": src["visibility"],
            "doc_count": doc_counts.get(src["id"], 0),
        }
        for src in sources_result.data
    ]

    return {"sources": results}


@router.patch("/license-sources/{source_id}/visibility")
async def set_source_visibility(
    source_id: str, body: SetVisibilityBody, request: Request, user_id: str = Depends(require_admin_role)
):
    """Set visibility for a source. Sentinel source is hard-rejected."""
    if source_id == _SENTINEL_SOURCE_ID:
        raise HTTPException(status_code=403, detail="Sentinel source is protected and cannot be modified")
    if body.visibility not in _VALID_VISIBILITY:
        raise HTTPException(status_code=422, detail=f"visibility must be one of: {', '.join(sorted(_VALID_VISIBILITY))}")

    db = get_supabase()
    if not db.table("sources").select("id").eq("id", source_id).limit(1).execute().data:
        raise HTTPException(status_code=404, detail="Source not found")

    result = db.table("sources").update({"visibility": body.visibility}).eq("id", source_id).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update visibility")

    logger.info("[ADMIN] source %s visibility → %s by %s", source_id, body.visibility, user_id)
    return {"id": source_id, "visibility": body.visibility}


@router.patch("/license-sources/{source_id}/license-status")
async def set_source_license_status(
    source_id: str, body: SetLicenseStatusBody, request: Request, user_id: str = Depends(require_admin_role)
):
    """Set license_status for a source. Sentinel source is hard-rejected."""
    if source_id == _SENTINEL_SOURCE_ID:
        raise HTTPException(status_code=403, detail="Sentinel source is protected and cannot be modified")
    if body.license_status not in _VALID_LICENSE_STATUS:
        raise HTTPException(
            status_code=422,
            detail=f"license_status must be one of: {', '.join(sorted(_VALID_LICENSE_STATUS))}",
        )

    db = get_supabase()
    if not db.table("sources").select("id").eq("id", source_id).limit(1).execute().data:
        raise HTTPException(status_code=404, detail="Source not found")

    result = db.table("sources").update({"license_status": body.license_status}).eq("id", source_id).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update license_status")

    logger.info("[ADMIN] source %s license_status → %s by %s", source_id, body.license_status, user_id)
    return {"id": source_id, "license_status": body.license_status}


@router.get("/safe-mode")
async def get_safe_mode(request: Request, user_id: str = Depends(require_admin_role)):
    """Return the current safe_mode value from app_settings."""
    db = get_supabase()
    result = db.table("app_settings").select("value").eq("key", "safe_mode").limit(1).execute()
    value = result.data[0]["value"] if result.data else "off"
    return {"value": value}


@router.patch("/safe-mode")
async def set_safe_mode(body: SetSafeModeBody, request: Request, user_id: str = Depends(require_admin_role)):
    """Toggle safe_mode on or off in app_settings."""
    if body.value not in {"on", "off"}:
        raise HTTPException(status_code=422, detail="value must be 'on' or 'off'")

    db = get_supabase()
    result = db.table("app_settings").update({"value": body.value}).eq("key", "safe_mode").execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update safe_mode")

    logger.info("[ADMIN] safe_mode → %s by %s", body.value, user_id)
    return {"value": body.value}


@router.get("/stats")
async def get_corpus_stats(request: Request, user_id: str = Depends(require_admin_role)):
    """Return total row counts for documents, chunks, verses, interlinear_words.
    Uses the service key so RLS is bypassed — the anon client returns 0 for
    several of these tables because they have no public-read policy."""
    db = get_supabase()
    counts = {}
    for table in ("documents", "chunks", "verses", "interlinear_words"):
        try:
            result = db.table(table).select("id", count="exact").execute()
            counts[table] = result.count or 0
        except Exception:
            logger.warning("Failed to count %s", table)
            counts[table] = 0
    return counts
