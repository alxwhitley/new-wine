import hashlib
import logging
import uuid

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.db.supabase import get_supabase
from app.services.extractor import extract_text_from_pdf
from app.services.metadata import extract_metadata
from app.services.chunker import chunk_text
from app.services.embeddings import embed_text

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("")
async def ingest(
    file: UploadFile = File(...),
    source_type: str = Form("sermon"),
):
    if source_type not in ("sermon", "background"):
        raise HTTPException(status_code=400, detail="source_type must be 'sermon' or 'background'")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        file_bytes = await file.read()
        source_hash = hashlib.md5(file_bytes).hexdigest()

        text = extract_text_from_pdf(file_bytes)
        if not text:
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")

        metadata = extract_metadata(text)
        chunks = chunk_text(text)

        db = get_supabase()
        doc_id = str(uuid.uuid4())

        db.table("documents").insert({
            "id": doc_id,
            "title": metadata.get("title"),
            "author": metadata.get("author"),
            "year": metadata.get("year"),
            "topic_tags": metadata.get("topic_tags"),
            "source_type": source_type,
        }).execute()

        author = metadata.get("author")
        year = metadata.get("year")

        for i, chunk_content in enumerate(chunks):
            prefix = f"Author: {author} | Year: {year} | "
            embedding = embed_text(prefix + chunk_content)
            db.table("chunks").insert({
                "id": str(uuid.uuid4()),
                "document_id": doc_id,
                "chunk_index": i,
                "content": chunk_content,
                "embedding": embedding,
                "page_number": 0,
                "source_hash": source_hash,
            }).execute()

        return {
            "document_id": doc_id,
            "title": metadata.get("title"),
            "author": metadata.get("author"),
            "chunks_created": len(chunks),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /ingest endpoint")
        raise HTTPException(status_code=500, detail="An internal error occurred during ingestion")
