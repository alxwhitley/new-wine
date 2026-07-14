#!/usr/bin/env python3
"""
shared_ingest.py — shared document-writer chokepoint for Rhemata ingest scripts.

Owns the common resolve -> insert -> chunk -> embed -> propositions flow that
every document-writing ingest script needs. Converted so far: ingest.py
(and, transitively, youtube_ingest.py), ingest_magazine.py, and
ingest_preceptaustin.py. ingest_lexicon.py, ingest_helloao.py, and
ingest_commentaries.py call propositions.process_document() directly and do
not go through this module yet.

ingest_document() writes a document record, all of its chunks, and its
propositions as ONE atomic unit: everything (chunking, embedding, and the
paraphrase step) is computed first, then written on a single shared
database connection that either commits as a whole or rolls back as a
whole. A killed process or any failure along the way leaves zero trace --
no document record, no chunks, no propositions -- rather than the partial,
half-written documents this replaces (see the Sermonindex incident in
rhemata-status.md / CLAUDE.md's shared_ingest decision entry). Propositions
runs on that same connection; its own existing commit-on-success /
rollback-on-failure (propositions.py, unmodified) becomes the single
commit/rollback boundary for the whole document, not just the
propositions table.

No module-level client construction or env-var reads: callers pass their own
`db` (supabase client) and `db_params` (psycopg2 DSN dict), matching the
existing convention in source_resolver.py.
"""

import os
import sys
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import execute_values
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.services.chunker import chunk_text
from app.services.embeddings import embed_text, EMBED_BATCH_SIZE

from source_resolver import normalize_alias_key, resolve_source_id
import propositions


# ── Dedup ─────────────────────────────────────────────────────────────────────

def already_ingested(
    db_params: dict,
    source_url: Optional[str],
    source_name: Optional[str],
    filename: str,
) -> bool:
    """Return True if a document row already exists for this content.

    Keys on source_url + source_name when a URL is known (exact match on both,
    NULL-safe). Falls back to matching filename against documents.file_path
    (suffix match, so it's indifferent to relative-vs-absolute or which
    subfolder the file currently sits in) when there's no URL.
    """
    conn = psycopg2.connect(**db_params)
    try:
        with conn.cursor() as cur:
            if source_url:
                cur.execute(
                    "SELECT id FROM documents WHERE url = %s AND source_name IS NOT DISTINCT FROM %s LIMIT 1",
                    (source_url, source_name),
                )
            else:
                cur.execute(
                    "SELECT id FROM documents WHERE right(file_path, length(%s)) = %s LIMIT 1",
                    (filename, filename),
                )
            return cur.fetchone() is not None
    finally:
        conn.close()


# ── Document row ──────────────────────────────────────────────────────────────

def _build_document_row(
    doc_id: str,
    *,
    title: Optional[str],
    author: Optional[str],
    year,
    issue: Optional[str],
    source_name: Optional[str],
    source_type: str,
    source_kind: str,
    citation_mode: str,
    topic_tags: Optional[List[str]],
    bible_references: Optional[List[str]],
    file_path: Optional[str],
    is_copyrighted: bool,
    source_id: Optional[str],
    url: Optional[str],
    full_text: Optional[str] = None,
) -> dict:
    row = {
        "id":              doc_id,
        "title":           title,
        "original_title":  title,
        "author":          author,
        "year":            year if isinstance(year, int) else None,
        "issue":           issue,
        "source_name":     source_name,
        "source_type":     source_type,
        "source_kind":     source_kind,
        "citation_mode":   citation_mode,
        "source":          source_name,  # mirrors source_name
        "topic_tags":      topic_tags or [],
        "bible_references": bible_references or [],
        "file_path":       file_path,
        "is_copyrighted":  is_copyrighted,
        "full_text":       full_text,
    }
    if source_id is not None:
        row["source_id"] = source_id
    if url:
        row["url"] = url
    return row


def _insert_document(cur, row: dict) -> str:
    """Insert a document row via the shared psycopg2 cursor/transaction --
    no commit here; the caller (ingest_document()) owns the transaction
    boundary. Column list is built dynamically from the row dict so it
    naturally omits whatever _build_document_row() didn't set (e.g.
    source_id, url when absent), the same way the REST insert this
    replaces did.
    """
    columns = list(row.keys())
    column_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    cur.execute(
        f"INSERT INTO documents ({column_list}) VALUES ({placeholders})",
        [row[c] for c in columns],
    )
    return row["id"]


def _delete_document(db, doc_id: str) -> None:
    db.table("chunks").delete().eq("document_id", doc_id).execute()
    db.table("documents").delete().eq("id", doc_id).execute()


# ── Chunks ────────────────────────────────────────────────────────────────────

class EmbeddingAlignmentError(Exception):
    """Raised by _embed_batch_verified when the alignment invariant (chunk
    i's stored embedding must come from embedding chunk i's own text)
    cannot be proven -- a short/partial batch response, an out-of-range
    item.index, or a position the API never returned an item for. Always
    raised, never swallowed: nothing has been written to the database yet
    when this fires (embedding happens entirely in memory, before the
    transaction opens -- see ingest_document()), so the caller can simply
    propagate it and nothing is left behind.
    """


_openai_client: Optional[OpenAI] = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai_client


def _embed_batch_verified(texts: List[str]) -> List[List[float]]:
    """Batch-embed texts, sub-batched at EMBED_BATCH_SIZE (matching
    backend/app/services/embeddings.py's own sub-batch size), verifying the
    OpenAI response's own `item.index` against intended position within
    each sub-batch before trusting it -- order is checked, never assumed.
    backend/app/services/embeddings.py's embed_batch() discards item.index
    today (positional trust only); this is a deliberately separate
    implementation rather than a wrapper around that function, because by
    the time embed_batch() returns, the index information is already gone
    -- there is nothing left to verify post hoc.

    Raises EmbeddingAlignmentError (never silently truncates, reorders, or
    proceeds) on: a sub-batch returning a different item count than it was
    sent, an item.index outside the sub-batch's range, or any position no
    item was ever written to. Returns a list the same length as `texts`,
    in the same order.
    """
    if not texts:
        return []
    client = _get_openai_client()
    embeddings: List[Optional[List[float]]] = [None] * len(texts)
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        response = client.embeddings.create(
            input=batch,
            model="text-embedding-3-small",
            dimensions=1536,
        )
        data = response.data
        if len(data) != len(batch):
            raise EmbeddingAlignmentError(
                f"embed sub-batch at offset {start} returned {len(data)} items "
                f"for {len(batch)} inputs -- refusing to zip a short/partial response"
            )
        for item in data:
            if not (0 <= item.index < len(batch)):
                raise EmbeddingAlignmentError(
                    f"embed sub-batch at offset {start}: item.index={item.index} "
                    f"out of range for a {len(batch)}-item sub-batch"
                )
            embeddings[start + item.index] = item.embedding

    missing = [i for i, e in enumerate(embeddings) if e is None]
    if missing:
        raise EmbeddingAlignmentError(
            f"embed batch never returned an item for position(s) {missing} "
            f"out of {len(texts)} -- refusing to proceed with gaps"
        )
    return embeddings


def _embed_chunks(
    chunks: List[str],
    embed_text_fn: Optional[Callable[[int, str], str]],
) -> List[List[float]]:
    """Compute every chunk's embedding in memory -- no database interaction
    at all. Pure computation step, called before any connection is opened,
    so a failure here (including EmbeddingAlignmentError) leaves nothing
    to roll back.

    Alignment invariant: for chunk i, embeddings[i] must come from
    embedding chunk i's own text.
      - _embed_batch_verified() checks the API's own item.index against
        intended position (order verified, not assumed) and raises on any
        short/partial/out-of-range response.
      - The length assert below is a second, explicit, independently
        visible check before the caller zips chunks with embeddings --
        redundant with the guarantee _embed_batch_verified() already
        provides by construction, but kept visible rather than only
        relying on that guarantee.
    """
    texts_to_embed = [
        embed_text_fn(idx, text) if embed_text_fn else text
        for idx, text in enumerate(chunks)
    ]
    embeddings = _embed_batch_verified(texts_to_embed)
    assert len(embeddings) == len(chunks), (
        f"embedding count {len(embeddings)} != chunk count {len(chunks)} -- "
        f"refusing to zip a mismatched batch"
    )
    return embeddings


def _insert_chunks(
    cur,
    doc_id: str,
    chunks: List[str],
    embeddings: List[List[float]],
    content_fn: Optional[Callable[[int, str], str]],
) -> None:
    """Insert every chunk row via the shared psycopg2 cursor/transaction in
    one execute_values(...) call -- no commit here; the caller
    (ingest_document()) owns the transaction boundary. Client-side UUIDs
    are generated per chunk before insert, same as every other caller in
    this codebase -- there is no server-generated-id + RETURNING remapping
    step to get wrong.
    """
    rows = []
    for idx, (text, embedding) in enumerate(zip(chunks, embeddings)):
        content = content_fn(idx, text) if content_fn else text
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        rows.append((str(uuid.uuid4()), doc_id, content, embedding_str, idx))

    execute_values(
        cur,
        "INSERT INTO chunks (id, document_id, content, embedding, chunk_index) VALUES %s",
        rows,
        template="(%s, %s, %s, %s::vector, %s)",
    )


# ── Strict mode ──────────────────────────────────────────────────────────────

class SilentSentinelRefused(Exception):
    """Raised by ingest_document() when strict mode (the default,
    allow_sentinel=False) would otherwise let a document land silently on the
    sentinel source because author/source_name matched no alias. Callers
    should catch this per-document to skip and continue a batch rather than
    letting one unresolvable doc kill the whole run. Carries the doc's
    identifying fields so the caller can build a useful skip report without
    re-deriving them.
    """

    def __init__(self, *, title, file_path, source_name, author):
        self.title = title
        self.file_path = file_path
        self.source_name = source_name
        self.author = author
        identifier = title or file_path or "(untitled)"
        super().__init__(
            f"{identifier}: source_name={source_name!r} author={author!r} matched "
            "no alias -- refusing silent sentinel fallback (allow_sentinel=False)"
        )


# ── Main entry point ──────────────────────────────────────────────────────────

def ingest_document(
    *,
    db,
    db_params: dict,
    title: Optional[str],
    body_text: str,
    filename: str,
    author: Optional[str] = None,
    year=None,
    issue: Optional[str] = None,
    source_name: Optional[str] = None,
    source_type: str = "other",
    source_kind: str = "unknown",
    citation_mode: str = "silent_context",
    is_copyrighted: bool = False,
    topic_tags: Optional[List[str]] = None,
    bible_references: Optional[List[str]] = None,
    url: Optional[str] = None,
    file_path: Optional[str] = None,

    # Attribution — supply source_id (pre-resolved, e.g. a caller-side gate)
    # or resolve_from=(source_name, author) to resolve here. If neither is
    # given, defaults to resolving from (source_name, author) above.
    source_id: Optional[str] = None,
    resolve_from: Optional[Tuple[Optional[str], Optional[str]]] = None,

    # Strict mode (default ON): refuse to silently land a resolver MISS on
    # the sentinel source — raises SilentSentinelRefused instead. Only
    # guards the resolve_from path below; a caller-provided source_id above
    # is a deliberate attribution choice and is never second-guessed here.
    # Set True to restore the old silent-fallback behavior.
    allow_sentinel: bool = False,

    # Dedup — source_url+source_name, filename fallback. skip_dedup=True for
    # callers that already own dedup responsibility (e.g. a per-row sheet
    # status column). Unchanged this session -- the skip-check's own design
    # (whether it should test completeness, not just existence) is a
    # separate, deliberately deferred decision (see rhemata-status.md).
    skip_dedup: bool = False,

    # Reuse-by-identity hook. Unused by ingest.py/ingest_magazine.py (always
    # insert fresh); used by ingest_preceptaustin.py's cross-pipeline excerpt
    # check. Its two known holes (unconditional re-chunk/re-insert on reuse;
    # document-row/full_text skipped on reuse) are unchanged this session --
    # still PLAN #11's job, not touched here.
    find_existing_fn: Optional[Callable[[], Optional[str]]] = None,
    on_existing: str = "skip",  # "skip" | "reuse" | "delete_and_reingest"

    # Chunking — default is the shared token-based chunker. lexicon will
    # need to pass its own one-entry-one-chunk formatter here when converted.
    chunk_fn: Callable[[str], List[str]] = chunk_text,
    embed_text_fn: Optional[Callable[[int, str], str]] = None,
    content_fn: Optional[Callable[[int, str], str]] = None,
) -> dict:
    """Resolve -> compute (chunk + embed + paraphrase) -> write, in that
    order. The document record, all of its chunks, and its propositions
    land in ONE atomic transaction: everything is computed in memory first
    (chunking is pure text splitting; embedding and the paraphrase step are
    external API calls, not database writes), then a single shared
    connection is opened and the record + chunks + propositions are
    written together. A killed process or any failure along the way rolls
    back the whole thing -- there is no point where a document record can
    exist with a partial chunk set, or with a paraphrase step that never
    ran, the way the two Sermonindex incident documents did.

    "Finished" (Alex-confirmed definition): record + all chunks + the
    paraphrase step having RUN TO COMPLETION, where "ran and found nothing"
    counts as finished and "failed to run" does not. This only applies
    where propositions.process_document()'s own gate says paraphrase
    should run at all (licensed/unlicensed sources) -- for gated-off
    sources (public_domain, owned, Precept Austin) "finished" is simply
    record + all chunks, and this function does not second-guess that gate.

    Concretely, once record + chunks are staged (uncommitted) on the shared
    connection, propositions.process_document() (unmodified, from commit
    42022a8) runs on that SAME connection:
      - "error" (the paraphrase call itself failed) -- process_document()
        has already rolled back internally; this function rolls back again
        (harmless no-op if already rolled back) and returns status="failed"
        with nothing written. The source row is left un-ingested by the
        caller so a retry redoes it cleanly -- and because nothing landed,
        that retry will not be blocked by a stale, already-exists document
        the way "The Ultimate Heist" was.
      - "stored:{n}" -- process_document() has already committed
        internally (record + chunks + propositions all land together,
        since they share this connection). This function's own commit()
        after that is a harmless no-op.
      - "no_propositions" / "skipped_licensed" / "skipped_precept_austin"
        -- process_document() touched neither commit nor rollback (nothing
        for it to write). This function commits explicitly here: paraphrase
        ran to completion (or correctly doesn't apply), so record + chunks
        are finished and saved.

    Any exception raised while record/chunks are being written (e.g. a
    duplicate-chunk-index collision on a reused document_id) rolls back and
    re-raises unchanged -- callers that catch specific exception types
    (e.g. ingest_preceptaustin.py's UniqueViolation guard) still see them.

    Returns a dict: {status, reason, doc_id, source_id, chunks, propositions}
    status is one of "processed", "skipped", "failed".
    """
    # ── Dedup ──
    if not skip_dedup:
        if already_ingested(db_params, url, source_name, filename):
            print("  ⏭️  Already ingested — skipping")
            return {
                "status": "skipped", "reason": "already_ingested",
                "doc_id": None, "source_id": None, "chunks": [], "propositions": None,
            }

    # ── Reuse-by-identity (find_existing_fn) ──
    existing_doc_id = find_existing_fn() if find_existing_fn else None
    if existing_doc_id is not None and on_existing == "skip":
        print("  ⏭️  Existing document found — skipping")
        return {
            "status": "skipped", "reason": "already_exists",
            "doc_id": existing_doc_id, "source_id": None, "chunks": [], "propositions": None,
        }
    if existing_doc_id is not None and on_existing == "delete_and_reingest":
        print(f"  Deleting existing document {existing_doc_id[:12]}... for re-ingest")
        _delete_document(db, existing_doc_id)
        existing_doc_id = None  # fall through to fresh insert below

    # ── Resolve attribution ──
    if source_id is not None:
        _resolved_id = source_id
        _norm_key = normalize_alias_key(source_name or author or "")
        print(f"  Source (caller-provided): {_resolved_id} (norm_key={_norm_key!r})")
    else:
        _resolve_from = resolve_from if resolve_from is not None else (source_name, author)
        _resolved_id, _norm_key, _via = resolve_source_id(db, _resolve_from[0], _resolve_from[1])
        print(f"  Resolved source: {_norm_key!r} -> {_resolved_id} (via {_via})")
        # Strict mode guards only this resolver path -- a caller-provided
        # source_id (the `if` branch above) is a deliberate attribution
        # choice and is never second-guessed here. The documents.source_id
        # column DEFAULT (migration 049) is a separate, unrelated
        # defense-in-depth layer for inserts that omit source_id entirely --
        # out of scope for this guard, left unchanged.
        if _via == "MISS" and not allow_sentinel:
            raise SilentSentinelRefused(
                title=title, file_path=file_path,
                source_name=source_name, author=author,
            )

    is_reuse = existing_doc_id is not None and on_existing == "reuse"
    doc_id = existing_doc_id if is_reuse else str(uuid.uuid4())
    if is_reuse:
        print(f"  Reusing existing document {doc_id[:12]}...")

    row = None
    if not is_reuse:
        row = _build_document_row(
            doc_id,
            title=title, author=author, year=year, issue=issue,
            source_name=source_name, source_type=source_type, source_kind=source_kind,
            citation_mode=citation_mode, topic_tags=topic_tags, bible_references=bible_references,
            file_path=file_path, is_copyrighted=is_copyrighted, source_id=_resolved_id, url=url,
            full_text=body_text,
        )

    # ── Compute everything in memory first -- nothing written yet ──
    print("  Chunking...")
    chunks = chunk_fn(body_text)
    print(f"  {len(chunks)} chunks created")
    print(f"  Embedding {len(chunks)} chunks...")
    embeddings = _embed_chunks(chunks, embed_text_fn)

    # ── Write record + chunks + propositions as one atomic unit ──
    conn = psycopg2.connect(**db_params)
    try:
        with conn.cursor() as cur:
            if not is_reuse:
                print("  Inserting document record...")
                _insert_document(cur, row)
                print(f"  Document ID: {doc_id}")
            print(f"  Inserting {len(chunks)} chunks...")
            _insert_chunks(cur, doc_id, chunks, embeddings, content_fn)

        prop_result = propositions.process_document(conn, doc_id, _resolved_id, body_text, embed_text)
        print(f"  propositions: {prop_result}")

        if prop_result == "error":
            conn.rollback()  # harmless no-op if process_document() already rolled back
            conn.close()
            print("  ✗ Paraphrase step failed — rolled back, nothing written for this document")
            return {
                "status": "failed", "reason": "paraphrase_failed",
                "doc_id": None, "source_id": _resolved_id, "chunks": [], "propositions": prop_result,
            }

        conn.commit()  # harmless no-op if process_document() already committed (stored:N)
        conn.close()
        return {
            "status": "processed", "reason": None,
            "doc_id": doc_id, "source_id": _resolved_id, "chunks": chunks, "propositions": prop_result,
        }
    except Exception:
        conn.rollback()
        conn.close()
        raise
