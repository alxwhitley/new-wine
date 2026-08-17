"""Read-only preparation and sole-writer execution for queued sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import psycopg2
import shared_ingest
from app.services.chunker import chunk_text
from app.services.metadata import extract_metadata
from app.services.source_resolver import is_source_servable
from source_ingest_queue.fetcher import FetchRejected, FetchTransient, fetch_html, fetch_pdf
from source_ingest_queue.html_extract import HtmlRejected, extract_article_bounded
from source_ingest_queue.pdf import PdfRejected, extract_pdf_bounded
from source_resolver import SENTINEL_SOURCE_ID, resolve_source_id


_SOURCE_FORMATS = frozenset({"pdf", "web_page"})
_SOURCE_TYPES = frozenset(
    {"book", "article", "sermon", "commentary", "essay", "letter", "other"}
)
_SOURCE_KINDS = frozenset({"sermon_transcript", "background_note", "unknown"})
_CITATION_MODES = frozenset({"citable", "silent_context"})


def _bounded_detail(detail: str) -> str:
    return " ".join(str(detail).split())[:240]


class AttentionRequired(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = _bounded_detail(detail)
        super().__init__("%s: %s" % (code, self.detail))


class RetryableIngestError(RuntimeError):
    def __init__(self, code: str, detail: str, *, attempted: bool = False):
        self.code = code
        self.detail = _bounded_detail(detail)
        self.attempted = attempted
        super().__init__("%s: %s" % (code, self.detail))


@dataclass(frozen=True)
class PreparedIngest:
    row_id: str
    source_id: str
    title: str
    author: str
    source_name: str
    body_text: str
    filename: str
    source_url: str
    source_type: str
    source_kind: str
    citation_mode: str
    year: Optional[int]
    topic_tags: List[str]
    bible_references: List[str]
    page_count: int
    chunk_count: int
    content_sha256: str
    fetched_bytes: int
    duplicate: bool
    extraction_evidence: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProcessOutcome:
    status: str
    reason: Optional[str]
    document_id: Optional[str]
    attempted: int
    stored: int
    skipped: int
    errored: int


def classify_row(row: dict) -> Optional[str]:
    """Return the first unsupported-policy reason, or None when runnable."""
    if row.get("source_format") not in _SOURCE_FORMATS:
        return "unsupported_source_format"
    if row.get("source_scope") != "single":
        return "unsupported_source_scope"
    if row.get("attribution_mode") != "declared":
        return "unsupported_attribution_mode"
    if row.get("retain_original_text") is not True:
        return "retention_policy_missing"
    if not (row.get("attribute_to") or "").strip():
        return "declared_author_missing"
    return None


def _clean_text(value, fallback: str, max_length: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    return " ".join(value.split())[:max_length]


def _clean_string_list(value) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value[:50]:
        if not isinstance(item, str) or not item.strip():
            continue
        cleaned.append(" ".join(item.split())[:100])
    return cleaned


def _base_prepared(
    *,
    row: dict,
    source_id: str,
    declared_author: str,
    extracted,
    fetched,
    chunk_count: int,
    duplicate: bool,
    is_web_page: bool,
) -> PreparedIngest:
    if is_web_page:
        # extracted is an html_extract.ExtractedArticle: it already carries a
        # real title (from <title>/<h1>) and structural extraction evidence,
        # both stronger signals than anything derivable from the URL alone.
        fallback_title = (extracted.title or "").strip()
        page_count = 1  # one article page; not a paginated-document concept
        evidence: Dict[str, object] = dict(extracted.evidence)
    else:
        fallback_title = Path(fetched.filename).stem.replace("_", " ").strip()
        page_count = extracted.page_count
        evidence = {"page_count": extracted.page_count}
    return PreparedIngest(
        row_id=str(row.get("id") or ""),
        source_id=source_id,
        title=fallback_title or declared_author,
        author=declared_author,
        source_name=declared_author,
        body_text=extracted.text,
        filename=fetched.filename,
        source_url=fetched.final_url,
        source_type="other",
        source_kind="unknown",
        citation_mode="silent_context",
        year=None,
        topic_tags=[],
        bible_references=[],
        page_count=page_count,
        chunk_count=chunk_count,
        content_sha256=fetched.sha256,
        fetched_bytes=fetched.byte_count,
        duplicate=duplicate,
        extraction_evidence=evidence,
    )


def prepare_ingest(
    row: dict,
    *,
    db,
    db_params: dict,
    dry_run: bool,
    fetch_fn: Callable = fetch_pdf,
    extract_fn: Callable = extract_pdf_bounded,
    html_fetch_fn: Callable = fetch_html,
    html_extract_fn: Callable = extract_article_bounded,
    resolve_fn: Callable = resolve_source_id,
    servable_fn: Callable = is_source_servable,
    dedup_fn: Callable = shared_ingest.already_ingested,
    chunk_fn: Callable = chunk_text,
    metadata_fn: Callable = extract_metadata,
) -> PreparedIngest:
    """Validate and prepare one row without writing corpus or queue state.

    source_format selects which fetch/extract pair runs -- pdf uses
    fetch_fn/extract_fn (fetch_pdf/extract_pdf_bounded by default),
    web_page uses html_fetch_fn/html_extract_fn (fetch_html/
    extract_article_bounded by default). Every later boundary (source
    resolution, servability, dedup, metadata, chunking) is identical for
    both -- only how raw bytes become plain body text differs."""
    reason = classify_row(row)
    if reason is not None:
        raise AttentionRequired(reason, "queue row is unsupported")
    if not row.get("id") or not row.get("url"):
        raise AttentionRequired("invalid_queue_row", "queue row identity is missing")

    is_web_page = row.get("source_format") == "web_page"
    active_fetch_fn = html_fetch_fn if is_web_page else fetch_fn
    active_extract_fn = html_extract_fn if is_web_page else extract_fn

    declared_author = row["attribute_to"].strip()
    try:
        fetched = active_fetch_fn(row["url"])
    except FetchRejected as exc:
        raise AttentionRequired(exc.code, "source fetch was rejected") from exc
    except FetchTransient as exc:
        raise RetryableIngestError(exc.code, "source fetch failed") from exc

    try:
        extracted = active_extract_fn(fetched.content)
    except PdfRejected as exc:
        raise AttentionRequired(exc.code, "PDF extraction was rejected") from exc
    except HtmlRejected as exc:
        raise AttentionRequired(exc.code, "article extraction was rejected") from exc

    try:
        source_id, _normalized_key, via = resolve_fn(
            db, declared_author, None
        )
    except Exception as exc:
        raise RetryableIngestError(
            "database_transient", "source resolution failed"
        ) from exc
    if via == "MISS" or source_id == SENTINEL_SOURCE_ID:
        raise AttentionRequired("source_unresolved", "declared source is unresolved")

    try:
        source_is_servable = servable_fn(db, source_id)
    except Exception as exc:
        raise RetryableIngestError(
            "database_transient", "source visibility check failed"
        ) from exc
    if not source_is_servable:
        raise AttentionRequired("source_not_servable", "declared source is not servable")

    chunks = chunk_fn(extracted.text)
    if not chunks:
        raise AttentionRequired("pdf_empty", "PDF produced no chunks")
    try:
        duplicate = bool(
            dedup_fn(
                db_params,
                fetched.final_url,
                declared_author,
                fetched.filename,
            )
        )
    except Exception as exc:
        raise RetryableIngestError(
            "database_transient", "duplicate check failed"
        ) from exc

    prepared = _base_prepared(
        row=row,
        source_id=source_id,
        declared_author=declared_author,
        extracted=extracted,
        fetched=fetched,
        chunk_count=len(chunks),
        duplicate=duplicate,
        is_web_page=is_web_page,
    )
    if dry_run or duplicate:
        return prepared

    try:
        metadata = metadata_fn(extracted.text)
    except Exception as exc:
        raise RetryableIngestError(
            "metadata_provider_failure", "metadata extraction failed"
        ) from exc
    if not isinstance(metadata, dict):
        raise RetryableIngestError(
            "metadata_provider_failure", "metadata response was invalid"
        )

    source_type = metadata.get("source_type")
    if source_type not in _SOURCE_TYPES:
        source_type = "other"
    default_kind = "sermon_transcript" if source_type == "sermon" else "unknown"
    default_citation = "citable" if source_type == "sermon" else "silent_context"
    source_kind = metadata.get("source_kind")
    if source_kind not in _SOURCE_KINDS:
        source_kind = default_kind
    citation_mode = metadata.get("citation_mode")
    if citation_mode not in _CITATION_MODES:
        citation_mode = default_citation
    year = metadata.get("year")
    if isinstance(year, bool) or not isinstance(year, int):
        year = None

    return PreparedIngest(
        row_id=prepared.row_id,
        source_id=prepared.source_id,
        title=_clean_text(metadata.get("title"), prepared.title),
        author=declared_author,
        source_name=declared_author,
        body_text=prepared.body_text,
        filename=prepared.filename,
        source_url=prepared.source_url,
        source_type=source_type,
        source_kind=source_kind,
        citation_mode=citation_mode,
        year=year,
        topic_tags=_clean_string_list(metadata.get("topic_tags")),
        bible_references=_clean_string_list(metadata.get("bible_references")),
        page_count=prepared.page_count,
        chunk_count=prepared.chunk_count,
        content_sha256=prepared.content_sha256,
        fetched_bytes=prepared.fetched_bytes,
        extraction_evidence=prepared.extraction_evidence,
        duplicate=False,
    )


def execute_ingest(
    prepared: PreparedIngest,
    *,
    db,
    db_params: dict,
    writer_fn: Callable = shared_ingest.ingest_document,
) -> ProcessOutcome:
    """Call the shared corpus writer at most once and reconcile its outcome."""
    if prepared.duplicate:
        return ProcessOutcome(
            status="skipped",
            reason="already_ingested",
            document_id=None,
            attempted=1,
            stored=0,
            skipped=1,
            errored=0,
        )

    try:
        result = writer_fn(
            db=db,
            db_params=db_params,
            title=prepared.title,
            body_text=prepared.body_text,
            filename=prepared.filename,
            author=prepared.author,
            year=prepared.year,
            source_name=prepared.source_name,
            source_type=prepared.source_type,
            source_kind=prepared.source_kind,
            citation_mode=prepared.citation_mode,
            is_copyrighted=False,
            topic_tags=list(prepared.topic_tags),
            bible_references=list(prepared.bible_references),
            url=prepared.source_url,
            file_path=prepared.filename,
            source_id=prepared.source_id,
            allow_sentinel=False,
        )
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
        raise RetryableIngestError(
            "database_transient", "shared ingest database call failed", attempted=True
        ) from exc
    except Exception as exc:
        raise RetryableIngestError(
            "embedding_provider_failure",
            "shared ingest computation failed",
            attempted=True,
        ) from exc

    if not isinstance(result, dict):
        raise RetryableIngestError(
            "internal_error", "shared ingest returned invalid data", attempted=True
        )
    status = result.get("status")
    reason = result.get("reason")
    if status == "processed" and result.get("doc_id"):
        return ProcessOutcome(
            status="processed",
            reason=None,
            document_id=str(result["doc_id"]),
            attempted=1,
            stored=1,
            skipped=0,
            errored=0,
        )
    if status == "skipped":
        return ProcessOutcome(
            status="skipped",
            reason=_bounded_detail(reason or "already_ingested"),
            document_id=str(result["doc_id"]) if result.get("doc_id") else None,
            attempted=1,
            stored=0,
            skipped=1,
            errored=0,
        )
    if status == "failed":
        raise RetryableIngestError(
            "proposition_provider_failure",
            "shared ingest rolled back",
            attempted=True,
        )
    raise RetryableIngestError(
        "internal_error", "shared ingest returned invalid data", attempted=True
    )
