from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import require_admin
from app.db.supabase import get_supabase
from app.services.chunker import chunk_text
from app.services.embeddings import embed_text

logger = logging.getLogger(__name__)

router = APIRouter()


class EditDocumentBody(BaseModel):
    title: str
    author: str
    content: str


@router.get("/sources")
async def list_sources(request: Request, user_id: str = Depends(require_admin)):
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
async def get_document_for_edit(doc_id: str, request: Request, user_id: str = Depends(require_admin)):
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
async def update_document(doc_id: str, body: EditDocumentBody, request: Request, user_id: str = Depends(require_admin)):
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
async def delete_document(doc_id: str, request: Request, user_id: str = Depends(require_admin)):
    """Delete a document and all its chunks. Admin only."""
    db = get_supabase()

    # Verify document exists
    doc = db.table("documents").select("id").eq("id", doc_id).limit(1).execute()
    if not doc.data:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete chunks first (FK dependency)
    db.table("chunks").delete().eq("document_id", doc_id).execute()
    # Delete document
    db.table("documents").delete().eq("id", doc_id).execute()

    logger.info("[ADMIN] Document %s deleted by user %s", doc_id, user_id)
    return {"success": True}


@router.patch("/sources/{toggle_id}")
async def toggle_source(toggle_id: str, request: Request, user_id: str = Depends(require_admin)):
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
