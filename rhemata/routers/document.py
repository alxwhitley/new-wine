import logging

from fastapi import APIRouter, HTTPException

from rhemata.db.supabase import get_supabase

logger = logging.getLogger(__name__)

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
