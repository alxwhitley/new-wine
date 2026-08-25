#!/usr/bin/env python3
"""
shared_ingest.py — shared document-writer chokepoint for Rhemata ingest scripts.

Owns the common resolve -> insert -> chunk -> embed -> propositions flow that
every document-writing ingest script needs. Converted so far: ingest.py
(and, transitively, youtube_ingest.py), ingest_magazine.py, and
ingest_preceptaustin.py. ingest_lexicon.py and ingest_helloao.py call
propositions.process_document() directly and do not go through this module
yet.

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
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

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


def _get_chunk_count(db_params: dict, doc_id: str) -> int:
    """Return the next free chunk_index for doc_id -- MAX(chunk_index)+1, or
    0 if the document has no chunks yet. Deliberately MAX+1, not a raw row
    COUNT: safe even if a document somehow already has a gap (none do,
    confirmed corpus-wide in an earlier session, but this is the correct
    invariant to hold regardless), and it's what reuse/append resumes from.
    """
    conn = psycopg2.connect(**db_params)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(chunk_index), -1) + 1 FROM chunks WHERE document_id = %s",
                (doc_id,),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


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
EMBEDDING_MODEL = "text-embedding-3-small"


class EmbeddingBatchComputation(NamedTuple):
    output: List[List[float]]
    model: str
    usage: Optional[Dict[str, int]]
    cost_usd: Optional[float]
    response_models: Tuple[Optional[str], ...] = ()
    model_status: str = "unavailable"


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai_client


def _embedding_response_usage(response) -> Optional[Dict[str, int]]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    normalized = {}
    for destination, candidates in (
        ("input_tokens", ("input_tokens", "prompt_tokens")),
        ("output_tokens", ("output_tokens", "completion_tokens")),
        ("total_tokens", ("total_tokens",)),
    ):
        for candidate in candidates:
            value = getattr(usage, candidate, None)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                normalized[destination] = value
                break
    return normalized or None


def _embed_batch_verified_with_evidence(
    texts: List[str],
    *,
    _collect_provider_evidence: bool = True,
) -> EmbeddingBatchComputation:
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
    item was ever written to. The computation output is a list the same
    length as `texts`, in the same order, alongside provider evidence.
    """
    if not texts:
        return EmbeddingBatchComputation([], EMBEDDING_MODEL, None, None)
    client = _get_openai_client()
    embeddings: List[Optional[List[float]]] = [None] * len(texts)
    usage_rows: List[Dict[str, int]] = []
    response_models: List[Optional[str]] = []
    costs: List[float] = []
    every_cost_available = True
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        response = client.embeddings.create(
            input=batch,
            model=EMBEDDING_MODEL,
            dimensions=1536,
        )
        if _collect_provider_evidence:
            raw_model = getattr(response, "model", None)
            response_models.append(
                raw_model.strip()
                if isinstance(raw_model, str) and raw_model.strip()
                else None
            )
            response_usage = _embedding_response_usage(response)
            if response_usage is not None:
                usage_rows.append(response_usage)
            raw_cost = getattr(response, "cost_usd", None)
            if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool):
                costs.append(float(raw_cost))
            else:
                every_cost_available = False
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
    usage = None
    batch_count = (len(texts) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE
    if _collect_provider_evidence and len(usage_rows) == batch_count:
        common_fields = set.intersection(*(set(row) for row in usage_rows))
        usage = {
            field: sum(row[field] for row in usage_rows)
            for field in ("input_tokens", "output_tokens", "total_tokens")
            if field in common_fields
        } or None
    observed_models = {model for model in response_models if model is not None}
    if not _collect_provider_evidence or not observed_models:
        model = EMBEDDING_MODEL
        model_status = "unavailable"
    elif len(observed_models) == 1 and all(
        model is not None for model in response_models
    ):
        model = next(iter(observed_models))
        model_status = "available"
    else:
        model = EMBEDDING_MODEL
        model_status = "ambiguous"
    output = [embedding for embedding in embeddings if embedding is not None]
    return EmbeddingBatchComputation(
        output=output,
        model=model,
        usage=usage,
        cost_usd=(
            sum(costs)
            if _collect_provider_evidence and every_cost_available
            else None
        ),
        response_models=tuple(response_models),
        model_status=model_status,
    )


def _embed_batch_verified(texts: List[str]) -> List[List[float]]:
    """Legacy aligned-embedding API; evidence callers use its companion."""
    return _embed_batch_verified_with_evidence(
        texts,
        _collect_provider_evidence=False,
    ).output


def _embed_chunks(
    chunks: List[str],
    embed_text_fn: Optional[Callable[[int, str], str]],
    start_index: int = 0,
) -> List[List[float]]:
    """Compute every chunk's embedding in memory -- no database interaction
    at all. Pure computation step, called before any connection is opened,
    so a failure here (including EmbeddingAlignmentError) leaves nothing
    to roll back.

    `chunks` may be a SLICE of a document's full chunk list (the reuse/
    append path only embeds the new tail, never re-embeds what's already
    stored) -- `start_index` is that slice's offset into the whole
    document, so embed_text_fn(idx, text) still sees the chunk's real,
    global position (e.g. magazine's idx==0 header special-case must mean
    "the document's true first chunk," not "the first chunk of this
    particular append").

    Alignment invariant: for chunk i (global index), embeddings[i -
    start_index] must come from embedding chunk i's own text.
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
        embed_text_fn(start_index + offset, text) if embed_text_fn else text
        for offset, text in enumerate(chunks)
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
    start_index: int = 0,
) -> None:
    """Insert every chunk row via the shared psycopg2 cursor/transaction in
    one execute_values(...) call -- no commit here; the caller
    (ingest_document()) owns the transaction boundary. Client-side UUIDs
    are generated per chunk before insert, same as every other caller in
    this codebase -- there is no server-generated-id + RETURNING remapping
    step to get wrong.

    `start_index` offsets chunk_index so a reuse/append call lands its new
    rows immediately after whatever already exists (continued numbering,
    never re-touching chunk_index values already present) -- 0 for a fresh
    document or a redo's full rewrite, existing_count for an append.
    """
    rows = []
    for offset, (text, embedding) in enumerate(zip(chunks, embeddings)):
        idx = start_index + offset
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
    # check (on_existing="reuse"). See the on_existing behaviors documented
    # in this function's docstring (PLAN #11, resolved 2026-07-13): "reuse"
    # now does continued-numbering append (the re-chunk-from-0 bug is
    # fixed); "delete_and_reingest" is now a true atomic swap. The
    # document-row/full_text-skipped-on-reuse gap is unchanged by design --
    # reuse never re-inserts the document row, only appends chunks.
    find_existing_fn: Optional[Callable[[], Optional[str]]] = None,
    on_existing: str = "skip",  # "skip" | "reuse" | "delete_and_reingest"

    # Chunking — default is the shared token-based chunker. lexicon will
    # need to pass its own one-entry-one-chunk formatter here when converted.
    chunk_fn: Callable[[str], List[str]] = chunk_text,
    embed_text_fn: Optional[Callable[[int, str], str]] = None,
    content_fn: Optional[Callable[[int, str], str]] = None,
    _reviewed_propositions: Optional[
        propositions._ValidatedReviewedPropositions
    ] = None,
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
    A document that lands finished is stamped (documents.ingest_completed_at,
    migration 062) inside this same transaction -- legacy pre-stamp rows
    stay NULL and are never treated as suspect; only an explicit caller
    choice (redo/reuse below) ever re-examines an existing document.

    When find_existing_fn() reports an existing document, on_existing picks
    one of three behaviors (PLAN #11, resolved 2026-07-13):
      - "skip" (default) -- leave the existing document alone untouched.
        Applies identically whether it's stamped or not; this function
        never uses the stamp to second-guess a caller's "skip" choice.
      - "delete_and_reingest" (REDO) -- for a document the caller has
        already determined is broken. The old document (and, via ON DELETE
        CASCADE, its chunks/propositions/excerpts) is deleted and the new
        one written under a fresh id in the SAME transaction as everything
        else here -- a true atomic swap. At every instant, another
        connection sees either the complete old document or the complete
        new one, never neither and never a partial write of the new one.
        A paraphrase failure (or any exception) rolls the whole thing back,
        including the delete -- the old document is left exactly as it was.
      - "reuse" (REUSE/APPEND) -- for a document that is deliberately built
        incrementally across multiple calls (lexicon-style: a huge file
        embedded/inserted in pieces across separate runs). Re-chunks the
        CURRENT full body_text, finds how many chunks already exist
        (MAX(chunk_index)+1, not a raw count), and appends only the new
        tail with continued numbering -- chunk_index values already
        present are never re-touched, so migration 061's uniqueness
        constraint is never hit by this path. If the existing chunk count
        already covers the full re-chunk, there is nothing to append;
        returns status="skipped", reason="already_complete" without
        touching the database. Document row is never re-inserted on this
        path (the existing one stays as-is; the known "full_text on reuse"
        gap this leaves is unchanged -- not this session's scope).

    Concretely, once record/delete + chunks are staged (uncommitted) on the
    shared connection, propositions.process_document() (unmodified, from
    commit 42022a8) runs on that SAME connection:
      - "error" (the paraphrase call itself failed) -- process_document()
        has already rolled back internally; this function rolls back again
        (harmless no-op if already rolled back) and returns status="failed"
        with nothing written (and, for a redo, the old document intact).
        The source row is left un-ingested by the caller so a retry redoes
        it cleanly -- and because nothing landed, that retry will not be
        blocked by a stale, already-exists document the way "The Ultimate
        Heist" was.
      - "stored:{n}" -- process_document() has already committed
        internally (record/delete + chunks + propositions all land
        together, since they share this connection). This function's own
        commit() after that is a harmless no-op.
      - "no_propositions" / "skipped_licensed" / "skipped_precept_austin"
        -- process_document() touched neither commit nor rollback (nothing
        for it to write). This function stamps and commits explicitly
        here: paraphrase ran to completion (or correctly doesn't apply),
        so record + chunks are finished and saved.

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

    is_redo = existing_doc_id is not None and on_existing == "delete_and_reingest"
    is_reuse = existing_doc_id is not None and on_existing == "reuse"

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

    old_doc_id = existing_doc_id if is_redo else None
    doc_id = existing_doc_id if is_reuse else str(uuid.uuid4())
    if is_redo:
        print(f"  Redo: will delete existing document {old_doc_id[:12]}... and write fresh as one atomic swap")
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

    start_index = 0
    if is_reuse:
        start_index = _get_chunk_count(db_params, doc_id)
        if start_index >= len(chunks):
            print(f"  Already complete: {start_index} chunks stored, {len(chunks)} expected — nothing to append")
            return {
                "status": "skipped", "reason": "already_complete",
                "doc_id": doc_id, "source_id": _resolved_id, "chunks": [], "propositions": None,
            }
        print(f"  Appending from chunk {start_index} ({len(chunks) - start_index} new of {len(chunks)} total)")

    new_chunks = chunks[start_index:]
    print(f"  Embedding {len(new_chunks)} chunk(s)...")
    embeddings = _embed_chunks(new_chunks, embed_text_fn, start_index=start_index)

    # ── Write record/delete + chunks + propositions as one atomic unit ──
    conn = psycopg2.connect(**db_params)
    try:
        with conn.cursor() as cur:
            if is_redo:
                print(f"  Deleting old document {old_doc_id[:12]}... (cascades chunks/propositions/excerpts)")
                cur.execute("DELETE FROM documents WHERE id = %s", (old_doc_id,))
            if not is_reuse:
                print("  Inserting document record...")
                _insert_document(cur, row)
                print(f"  Document ID: {doc_id}")
            print(f"  Inserting {len(new_chunks)} chunk(s)...")
            _insert_chunks(cur, doc_id, new_chunks, embeddings, content_fn, start_index=start_index)

            # Bypass-proofing Phase 2b (PLAN.md #45, 2026-07-29): fetch the
            # document's FULL current chunk-id set, on this same open
            # connection/cursor, before any commit -- so
            # propositions.process_document() can pass it down to
            # store_propositions() for the proposition_chunks back-link
            # (migration 074). One query is correct for all three paths
            # this function supports:
            #   - fresh insert: only this call's just-inserted chunks exist
            #     under this doc_id, so the query returns exactly that set.
            #   - redo (delete_and_reingest): the old document was deleted
            #     under its OWN id above, and a full fresh chunk set was
            #     just inserted under this NEW doc_id -- the query only
            #     ever sees the new set.
            #   - reuse/append: pre-existing chunks committed under this
            #     same doc_id on a PRIOR call, plus this call's newly
            #     appended tail, share this doc_id and are BOTH visible to
            #     a query on this same connection even before this call's
            #     own commit -- a transaction always sees its own
            #     uncommitted writes, and the prior call's chunks are
            #     already durably committed. Either way this query returns
            #     the full, current, honest chunk set for the document.
            print("  Fetching chunk ids for propositions back-link...")
            cur.execute(
                "SELECT id FROM chunks WHERE document_id = %s ORDER BY chunk_index",
                (doc_id,),
            )
            chunk_ids = [str(row[0]) for row in cur.fetchall()]

            # Named-teacher fix (2026-07-30, PLAN.md #46 follow-up):
            # resolve the best available real name for prompt attribution.
            # Prefer the caller-supplied author/source_name params (cheap,
            # no extra query) -- but those are only populated on the
            # resolve_from path; a caller using the pre-resolved source_id
            # override above can leave both None even though _resolved_id
            # names a real, populated sources row. Same connection/cursor,
            # before commit, so this adds one cheap lookup only in that
            # gap case.
            speaker = author or source_name
            if not speaker:
                cur.execute("SELECT name FROM sources WHERE id = %s", (_resolved_id,))
                row = cur.fetchone()
                speaker = row[0] if row else None

        # Opt this real call site into prompt_version="v3.1" (isolated
        # naming fix only -- see propositions.EXTRACTION_PROMPT_V3_1's own
        # comment). If `speaker` is still empty here (no author, no
        # source_name, no sources.name -- not expected for any real
        # licensed/unlicensed source, but not specially guarded against),
        # process_document()'s own extract call raises ValueError
        # internally, caught by its outer except and returned as "error",
        # same as any other extraction failure.
        prop_result = propositions.process_document(
            conn, doc_id, _resolved_id, body_text, embed_text, chunk_ids=chunk_ids,
            speaker=speaker, prompt_version="v3.1",
            _reviewed_propositions=_reviewed_propositions,
        )
        print(f"  propositions: {prop_result}")

        if prop_result == "error":
            conn.rollback()  # harmless no-op if process_document() already rolled back
            conn.close()
            print("  ✗ Paraphrase step failed — rolled back, nothing written for this document")
            return {
                "status": "failed", "reason": "paraphrase_failed",
                "doc_id": None, "source_id": _resolved_id, "chunks": [], "propositions": prop_result,
            }

        with conn.cursor() as cur:
            cur.execute("UPDATE documents SET ingest_completed_at = now() WHERE id = %s", (doc_id,))
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
