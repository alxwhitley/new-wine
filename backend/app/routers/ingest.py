import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form

from app.auth import require_admin_role
from app.db.supabase import get_supabase
from app.services.extractor import extract_text_from_pdf
from app.services.metadata import extract_metadata
from app.services.chunker import chunk_text
from app.services.embeddings import embed_batch

logger = logging.getLogger(__name__)

router = APIRouter()

# Empirically measured against live data: chunks.embedding is HNSW-indexed, so
# insert cost is dominated by index maintenance, not row count alone.
# PostgREST's statement_timeout (~8s) is hit reliably at batch sizes >= 20.
# Batches of 6 with REAL embeddings run ~1.0-2.8s (avg ~1.8s) -- an earlier
# calibration using random noise vectors instead of real embeddings measured
# ~4.5s/batch, which turned out not to be representative (HNSW insert cost
# depends on vector distribution; real, semantically-clustered embeddings are
# cheaper to place than uniform random noise).
CHUNK_INSERT_BATCH_SIZE = 6

# Railway's edge proxy hard-caps public HTTP requests at 300s (confirmed via
# Railway's own docs: https://docs.railway.com/networking/edge-networking).
# Target: total request wall-clock <= 150s (50% of the hard limit, full 2x
# margin) -- 30s reserved for non-insert work (PDF extraction, chunking,
# batched embedding calls, response), 120s for the insert loop. Using the
# WORST observed per-batch time (2.8s, not the ~1.8s average) as the design
# basis: 120s / 2.8s = 42 batches x 6 = 252 chunks, rounded down to 250.
# The largest real document in the corpus (STEPBible Greek Lexicon, 11,034
# chunks) is ~44x this threshold -- oversized documents must be re-ingested
# offline (direct DB connection, no request timeout), not through this
# request/response endpoint.
MAX_INGEST_CHUNKS = 250
MAX_LOG_IDENTITY_CHARS = 240


def _bounded_log_identity(value):
    if value is None:
        return None
    text = str(value)
    if len(text) <= MAX_LOG_IDENTITY_CHARS:
        return text
    return text[:MAX_LOG_IDENTITY_CHARS] + "..."


def _log_ingest_failure(log, progress):
    """Emit identifiers and counts needed to reconcile a partial ingest.

    User-derived strings use repr formatting so embedded newlines cannot forge
    extra log lines. Document text and chunk contents are intentionally absent.
    """
    log.exception(
        "Unhandled error in /ingest endpoint: filename=%r source_type=%s "
        "stage=%s document_id=%s title=%r chunks_attempted=%s chunks_stored=%s",
        _bounded_log_identity(progress.get("filename")),
        progress.get("source_type"),
        progress.get("stage"),
        progress.get("document_id"),
        _bounded_log_identity(progress.get("title")),
        progress.get("chunks_attempted"),
        progress.get("chunks_stored"),
    )


@router.post("")
async def ingest(
    request: Request,
    file: UploadFile = File(...),
    source_type: str = Form("sermon"),
    user_id: str = Depends(require_admin_role),
):
    if source_type not in ("sermon", "background"):
        raise HTTPException(status_code=400, detail="source_type must be 'sermon' or 'background'")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    progress = {
        "filename": file.filename,
        "source_type": source_type,
        "stage": "read_upload",
        "document_id": None,
        "title": None,
        "chunks_attempted": 0,
        "chunks_stored": 0,
    }
    try:
        file_bytes = await file.read()

        progress["stage"] = "extract_text"
        text = extract_text_from_pdf(file_bytes)
        if not text:
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")

        progress["stage"] = "extract_metadata"
        metadata = extract_metadata(text)
        progress["title"] = metadata.get("title")

        progress["stage"] = "chunk_text"
        chunks = chunk_text(text)
        progress["chunks_attempted"] = len(chunks)

        # Size-check BEFORE any DB mutation or embedding spend -- see
        # MAX_INGEST_CHUNKS for why. A rejected request here has written
        # nothing.
        if len(chunks) > MAX_INGEST_CHUNKS:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"This PDF would chunk to {len(chunks)} chunks, exceeding the "
                    f"{MAX_INGEST_CHUNKS}-chunk limit for in-request ingestion. At ~6 "
                    f"chunks/insert-batch and Railway's 300s hard request timeout, larger "
                    f"documents cannot complete this endpoint's embed+insert loop reliably. "
                    f"Ingest this document offline instead via scripts/ingest.py (direct DB "
                    f"connection, no request timeout)."
                ),
            )

        author = metadata.get("author")
        year = metadata.get("year")

        # Embed everything BEFORE inserting the document row -- if embedding
        # fails, nothing is written at all (previously the document row was
        # inserted first, then chunks were embedded and inserted one at a
        # time; a mid-loop failure left an orphaned document with zero or
        # partial chunks). Insert in small batches (CHUNK_INSERT_BATCH_SIZE)
        # -- see its comment for why a single giant insert isn't safe. This
        # still replaces ~1 embed + 1 insert round trip per chunk (a
        # ~110-chunk document was ~220 sequential round trips, 40-90s,
        # guaranteed Railway timeout) with one batched embedding call plus
        # ~1 insert call per 6 chunks.
        progress["stage"] = "embed_chunks"
        prefix = f"Author: {author} | Year: {year} | "
        embeddings = embed_batch([prefix + chunk_content for chunk_content in chunks])

        db = get_supabase()
        doc_id = str(uuid.uuid4())
        progress["document_id"] = doc_id

        progress["stage"] = "insert_document"
        db.table("documents").insert({
            "id": doc_id,
            "title": metadata.get("title"),
            "author": author,
            "year": year,
            "topic_tags": metadata.get("topic_tags"),
            "source_type": source_type,
        }).execute()

        chunk_rows = [
            {
                "id": str(uuid.uuid4()),
                "document_id": doc_id,
                "chunk_index": i,
                "content": chunk_content,
                "embedding": embedding,
            }
            for i, (chunk_content, embedding) in enumerate(zip(chunks, embeddings))
        ]
        progress["stage"] = "insert_chunks"
        for i in range(0, len(chunk_rows), CHUNK_INSERT_BATCH_SIZE):
            batch = chunk_rows[i:i + CHUNK_INSERT_BATCH_SIZE]
            db.table("chunks").insert(batch).execute()
            progress["chunks_stored"] += len(batch)

        progress["stage"] = "complete"
        return {
            "document_id": doc_id,
            "title": metadata.get("title"),
            "author": metadata.get("author"),
            "chunks_created": len(chunks),
        }
    except HTTPException:
        raise
    except Exception:
        _log_ingest_failure(logger, progress)
        raise HTTPException(status_code=500, detail="An internal error occurred during ingestion")
