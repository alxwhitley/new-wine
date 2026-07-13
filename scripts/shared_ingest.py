#!/usr/bin/env python3
"""
shared_ingest.py — shared document-writer chokepoint for Rhemata ingest scripts.

Owns the common resolve -> insert -> chunk -> embed -> propositions flow that
every document-writing ingest script (ingest.py, ingest_magazine.py,
ingest_preceptaustin.py, ingest_lexicon.py, ingest_commentaries.py) needs.
Script-specific concerns (file discovery, metadata extraction, frontmatter
parsing, Bible-reference extraction, topic tagging) stay in each script —
only the part every script duplicates today lives here.

Converted so far: ingest.py only (see CLAUDE.md "Ingest chokepoint consolidation").
The other four scripts are unconverted; the hooks below (chunk_fn,
find_existing_fn/on_existing, insert_mode) exist for them but are only
exercised by ingest.py's default values today. Do not assume they're battle
tested for lexicon's one-entry-one-chunk override or commentaries' batched
insert until those scripts are actually converted.

No module-level client construction or env-var reads: callers pass their own
`db` (supabase client) and `db_params` (psycopg2 DSN dict), matching the
existing convention in source_resolver.py.
"""

import sys
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.services.chunker import chunk_text
from app.services.embeddings import embed_text

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


def _insert_document_rest(db, row: dict) -> str:
    try:
        db.table("documents").insert(row).execute()
    except Exception:
        # url/bible_references columns may not exist yet — retry without them
        row.pop("url", None)
        row.pop("bible_references", None)
        db.table("documents").insert(row).execute()
    return row["id"]


def _delete_document(db, doc_id: str) -> None:
    db.table("chunks").delete().eq("document_id", doc_id).execute()
    db.table("documents").delete().eq("id", doc_id).execute()


# ── Chunks ────────────────────────────────────────────────────────────────────

def _insert_chunks_rest(
    db,
    db_params: dict,
    doc_id: str,
    chunks: List[str],
    embed_text_fn: Optional[Callable[[int, str], str]],
    content_fn: Optional[Callable[[int, str], str]],
) -> None:
    # db_params is unused here -- REST mode never opens a direct connection.
    # Accepted anyway so every _INSERT_MODES entry shares one call signature
    # (see ingest_document()'s single generic call site below).
    for idx, text in enumerate(chunks):
        print(f"  Embedding chunk {idx + 1}/{len(chunks)}...")
        text_to_embed = embed_text_fn(idx, text) if embed_text_fn else text
        embedding = embed_text(text_to_embed)
        content = content_fn(idx, text) if content_fn else text

        # page_number is excluded: the column is absent from the live DB schema.
        db.table("chunks").insert({
            "id":          str(uuid.uuid4()),
            "document_id": doc_id,
            "content":     content,
            "embedding":   embedding,
            "chunk_index": idx,
        }).execute()


_INSERT_MODES = {
    "rest_per_chunk": _insert_chunks_rest,
    # "psycopg2_batch" is the shape needed by ingest_preceptaustin.py /
    # ingest_lexicon.py / ingest_commentaries.py — not implemented yet.
    # Add it when converting the first of those scripts; don't build it
    # speculatively against three different batching/pacing needs.
}


# ── Propositions ──────────────────────────────────────────────────────────────

def _run_propositions(db_params: dict, propositions_conn, doc_id: str, source_id: str, body_text: str) -> str:
    if propositions_conn is not None:
        return propositions.process_document(propositions_conn, doc_id, source_id, body_text, embed_text)
    conn = psycopg2.connect(**db_params)
    try:
        return propositions.process_document(conn, doc_id, source_id, body_text, embed_text)
    finally:
        conn.close()


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
    # status column).
    skip_dedup: bool = False,

    # Reuse-by-identity hook. Unused by ingest.py (always inserts fresh);
    # exists for precept_austin's cross-pipeline excerpt check, lexicon's
    # resume-by-chunk-count, and commentaries' crash-recovery delete pattern.
    find_existing_fn: Optional[Callable[[], Optional[str]]] = None,
    on_existing: str = "skip",  # "skip" | "reuse" | "delete_and_reingest"

    # Chunking — default is the shared token-based chunker. lexicon will
    # need to pass its own one-entry-one-chunk formatter here when converted.
    chunk_fn: Callable[[str], List[str]] = chunk_text,
    embed_text_fn: Optional[Callable[[int, str], str]] = None,
    content_fn: Optional[Callable[[int, str], str]] = None,

    insert_mode: str = "rest_per_chunk",

    # Propositions connection: reuse the caller's (commentaries' pattern) or
    # leave None to open+close a dedicated one (everyone else's pattern).
    propositions_conn=None,
) -> dict:
    """Resolve -> insert -> chunk -> embed -> propositions, in that order.

    Returns a dict: {status, reason, doc_id, source_id, chunks, propositions}
    status is one of "processed", "skipped", "failed".
    """
    if insert_mode not in _INSERT_MODES:
        raise NotImplementedError(
            f"insert_mode={insert_mode!r} is not implemented yet. "
            f"Available: {list(_INSERT_MODES)}"
        )
    insert_chunks_fn = _INSERT_MODES[insert_mode]

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

    # ── Insert document (or reuse) ──
    if existing_doc_id is not None and on_existing == "reuse":
        doc_id = existing_doc_id
        print(f"  Reusing existing document {doc_id[:12]}...")
    else:
        doc_id = str(uuid.uuid4())
        row = _build_document_row(
            doc_id,
            title=title, author=author, year=year, issue=issue,
            source_name=source_name, source_type=source_type, source_kind=source_kind,
            citation_mode=citation_mode, topic_tags=topic_tags, bible_references=bible_references,
            file_path=file_path, is_copyrighted=is_copyrighted, source_id=_resolved_id, url=url,
            full_text=body_text,
        )
        print("  Inserting document record...")
        doc_id = _insert_document_rest(db, row)
        print(f"  Document ID: {doc_id}")

    # ── Chunk ──
    print("  Chunking...")
    chunks = chunk_fn(body_text)
    print(f"  {len(chunks)} chunks created")

    # ── Embed + insert chunks ──
    print(f"  Embedding and inserting {len(chunks)} chunks...")
    insert_chunks_fn(db, db_params, doc_id, chunks, embed_text_fn, content_fn)

    # ── Propositions (non-fatal; gate lives in propositions.py) ──
    prop_result = _run_propositions(db_params, propositions_conn, doc_id, _resolved_id, body_text)
    print(f"  propositions: {prop_result}")

    return {
        "status": "processed", "reason": None,
        "doc_id": doc_id, "source_id": _resolved_id, "chunks": chunks, "propositions": prop_result,
    }
