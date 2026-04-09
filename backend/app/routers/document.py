import logging
import re

from fastapi import APIRouter, HTTPException

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

CHUNK_OVERLAP = 200

router = APIRouter()


@router.get("/{document_id}")
async def get_document(document_id: str):
    try:
        db = get_supabase()

        doc_result = db.table("documents").select("*").eq("id", document_id).execute()
        if not doc_result.data:
            raise HTTPException(status_code=404, detail="Document not found")

        chunks_result = (
            db.table("chunks")
            .select("id, chunk_index, content")
            .eq("document_id", document_id)
            .order("chunk_index")
            .execute()
        )

        return {
            "document": doc_result.data[0],
            "chunks": chunks_result.data,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /document endpoint")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/{document_id}/article")
async def get_article(document_id: str):
    try:
        db = get_supabase()

        doc_result = (
            db.table("documents")
            .select("id, title, author, issue, year, source_name, url")
            .eq("id", document_id)
            .execute()
        )
        if not doc_result.data:
            raise HTTPException(status_code=404, detail="Document not found")

        doc = doc_result.data[0]

        chunks_result = (
            db.table("chunks")
            .select("chunk_index, content")
            .eq("document_id", document_id)
            .order("chunk_index")
            .execute()
        )

        # Reassemble full text, trimming overlap from all chunks except the first
        parts = []
        for chunk in chunks_result.data:
            content = chunk.get("content", "")
            if chunk["chunk_index"] == 0:
                parts.append(content)
            else:
                parts.append(content[CHUNK_OVERLAP:] if len(content) > CHUNK_OVERLAP else content)

        full_text = "\n".join(parts)

        # Strip metadata header: [New Wine | Jan 1973 | Title by Author]
        if full_text.startswith("["):
            bracket_end = full_text.find("]")
            if bracket_end != -1:
                full_text = full_text[bracket_end + 1:].lstrip("\n")

        # Strip markdown bold/italic markers
        full_text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", full_text)

        # Clean author: truncate at opening parenthesis
        author = doc.get("author") or ""
        if "(" in author:
            author = author[:author.index("(")].rstrip()

        return {
            "id": doc["id"],
            "title": doc.get("title"),
            "author": author or None,
            "issue": doc.get("issue"),
            "year": doc.get("year"),
            "source_name": doc.get("source_name"),
            "url": doc.get("url"),
            "content": full_text,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /document/%s/article endpoint", document_id)
        raise HTTPException(status_code=500, detail="An internal error occurred")
