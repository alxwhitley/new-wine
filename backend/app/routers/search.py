import logging
import os

from fastapi import APIRouter, HTTPException, Query

from app.db.supabase import get_supabase
from app.services.embeddings import embed_text

logger = logging.getLogger(__name__)

INCLUDE_COPYRIGHTED = os.environ.get("INCLUDE_COPYRIGHTED", "false").lower() == "true"

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
