"""Full-compute, zero-database-write previews for staged web articles."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import propositions
import shared_ingest
from app.services.chunker import chunk_text
from quote_candidates import generate_candidate_spans
from source_ingest_queue.processor import PreparedIngest, prepare_ingest


SCHEMA_VERSION = "source_ingest_preview.v1"
PROMPT_VERSION = "v3.1"
EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_REVIEW_DIR = Path(__file__).resolve().parents[2] / "source_ingest_preview_review"
_MAX_PROPOSITIONS = 1_000
_MAX_PROPOSITION_CHARS = 20_000
_SURROUNDING_PASSAGE_CHARS = 240
_USAGE_FIELDS = ("input_tokens", "output_tokens", "total_tokens")


@dataclass(frozen=True)
class ModelComputation:
    """Validated boundary envelope for one external model computation."""

    output: object
    model: str
    usage: Optional[Mapping[str, object]] = None
    cost_usd: Optional[float] = None


class PreviewValidationError(ValueError):
    """Raised when captured or external-model data violates the preview contract."""


class PreviewCollisionError(RuntimeError):
    """Raised rather than replacing an immutable preview artifact."""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise PreviewValidationError("preview data is not canonical JSON") from exc


def canonical_preview_json(report: Mapping[str, object]) -> str:
    """Return the one canonical byte representation used for review artifacts."""
    return _canonical_json(report) + "\n"


def write_preview_report(
    report: Mapping[str, object],
    *,
    review_dir: Path = DEFAULT_REVIEW_DIR,
) -> Path:
    """Create a mode-0600 canonical report, never replacing existing bytes."""
    report_id = report.get("report_id")
    if (
        not isinstance(report_id, str)
        or len(report_id) != 64
        or any(ch not in "0123456789abcdef" for ch in report_id)
    ):
        raise PreviewValidationError("report_id is not a lowercase SHA-256 digest")
    capture = report.get("capture")
    attribution = report.get("attribution")
    if not isinstance(capture, Mapping) or not isinstance(attribution, Mapping):
        raise PreviewValidationError("report identity evidence is missing")
    expected_report_id = _identity_digest(
        schema_version=report.get("schema_version"),
        row_id=capture.get("row_id"),
        url=capture.get("url"),
        content_sha256=capture.get("content_sha256"),
        fetched_bytes=capture.get("fetched_bytes"),
        source_id=attribution.get("source_id"),
    )
    if report_id != expected_report_id:
        raise PreviewValidationError("report_id does not match capture identity")
    payload = canonical_preview_json(report).encode("utf-8")
    directory = Path(review_dir)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise PreviewValidationError("review_dir must be a real directory")
    path = directory / (report_id + ".json")

    def _accept_existing() -> Path:
        if path.is_symlink() or not path.is_file():
            raise PreviewCollisionError("preview identity is occupied by a non-file")
        if path.read_bytes() != payload:
            raise PreviewCollisionError("preview identity already has different bytes")
        return path

    if path.exists() or path.is_symlink():
        return _accept_existing()
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _accept_existing()
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        os.fchmod(handle.fileno(), 0o600)
    return path


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identity_digest(
    *,
    schema_version: object,
    row_id: object,
    url: object,
    content_sha256: object,
    fetched_bytes: object,
    source_id: object,
) -> str:
    if schema_version != SCHEMA_VERSION:
        raise PreviewValidationError("preview schema version is invalid")
    identity = {
        "schema_version": schema_version,
        "row_id": row_id,
        "url": url,
        "content_sha256": content_sha256,
        "fetched_bytes": fetched_bytes,
        "source_id": source_id,
    }
    return _sha256_text(_canonical_json(identity))


def _report_id(prepared: PreparedIngest) -> str:
    return _identity_digest(
        schema_version=SCHEMA_VERSION,
        row_id=prepared.row_id,
        url=prepared.source_url,
        content_sha256=prepared.content_sha256,
        fetched_bytes=prepared.fetched_bytes,
        source_id=prepared.source_id,
    )


def _stable_item_id(report_id: str, kind: str, index: int, digest: str) -> str:
    return _sha256_text("%s:%s:%d:%s" % (report_id, kind, index, digest))


def _validate_prepared(prepared: PreparedIngest) -> None:
    required_text = {
        "row_id": prepared.row_id,
        "source_id": prepared.source_id,
        "source_url": prepared.source_url,
        "content_sha256": prepared.content_sha256,
        "author": prepared.author,
        "source_name": prepared.source_name,
        "body_text": prepared.body_text,
    }
    for name, value in required_text.items():
        if not isinstance(value, str) or not value.strip():
            raise PreviewValidationError("prepared %s is missing" % name)
    if (
        len(prepared.content_sha256) != 64
        or prepared.content_sha256 != prepared.content_sha256.lower()
        or any(ch not in "0123456789abcdef" for ch in prepared.content_sha256)
    ):
        raise PreviewValidationError("prepared content_sha256 is invalid")
    if (
        isinstance(prepared.fetched_bytes, bool)
        or not isinstance(prepared.fetched_bytes, int)
        or prepared.fetched_bytes < 0
    ):
        raise PreviewValidationError("prepared fetched_bytes is invalid")
    if prepared.duplicate:
        raise PreviewValidationError("duplicate captures cannot produce a full preview")
    if prepared.source_kind != "web_article":
        raise PreviewValidationError("preview requires source_kind=web_article")
    if prepared.citation_mode != "citable":
        raise PreviewValidationError("preview requires citation_mode=citable")
    if prepared.license_status not in ("licensed", "unlicensed"):
        raise PreviewValidationError("preview source license is not stageable")
    if prepared.source_visibility != "hidden":
        raise PreviewValidationError("preview source must remain hidden")
    if prepared.metadata_computed is not True:
        raise PreviewValidationError("preview requires completed metadata computation")
    _canonical_json(prepared.extraction_evidence)


def _normalize_usage(value: Optional[Mapping[str, object]]) -> Optional[Dict[str, int]]:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise PreviewValidationError("model usage must be an object")
    usage: Dict[str, int] = {}
    for field in _USAGE_FIELDS:
        if field not in value:
            continue
        token_count = value[field]
        if isinstance(token_count, bool) or not isinstance(token_count, int):
            raise PreviewValidationError("model usage %s must be an integer" % field)
        if token_count < 0:
            raise PreviewValidationError("model usage %s cannot be negative" % field)
        usage[field] = token_count
    return usage or None


def _normalize_computation(
    result: object,
    *,
    boundary: str,
) -> Tuple[object, Dict[str, object]]:
    if not isinstance(result, ModelComputation):
        raise PreviewValidationError("%s must return ModelComputation" % boundary)
    if not isinstance(result.model, str) or not result.model.strip() or len(result.model) > 200:
        raise PreviewValidationError("%s model identity is invalid" % boundary)
    usage = _normalize_usage(result.usage)
    cost = result.cost_usd
    if cost is not None:
        if isinstance(cost, bool) or not isinstance(cost, (int, float)):
            raise PreviewValidationError("%s cost_usd must be numeric" % boundary)
        cost = float(cost)
        if not math.isfinite(cost) or cost < 0:
            raise PreviewValidationError("%s cost_usd is invalid" % boundary)
    evidence = {
        "model": result.model.strip(),
        "usage": usage,
        "cost_usd": cost,
    }
    return result.output, evidence


def _validate_chunks(raw_chunks: object) -> List[str]:
    if not isinstance(raw_chunks, list) or not raw_chunks:
        raise PreviewValidationError("chunker must return a non-empty list")
    chunks: List[str] = []
    for chunk in raw_chunks:
        if not isinstance(chunk, str) or not chunk.strip():
            raise PreviewValidationError("chunk content must be non-empty text")
        chunks.append(chunk)
    return chunks


def _validate_embeddings(
    raw_embeddings: object,
    *,
    expected_count: int,
    expected_dimensions: int,
    boundary: str,
) -> List[Dict[str, object]]:
    if not isinstance(raw_embeddings, list) or len(raw_embeddings) != expected_count:
        raise PreviewValidationError("%s embedding count mismatch" % boundary)
    evidence: List[Dict[str, object]] = []
    for vector in raw_embeddings:
        if not isinstance(vector, (list, tuple)) or len(vector) != expected_dimensions:
            raise PreviewValidationError("%s embedding dimensions mismatch" % boundary)
        normalized: List[float] = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PreviewValidationError("%s embedding value is not numeric" % boundary)
            number = float(value)
            if not math.isfinite(number):
                raise PreviewValidationError("%s embedding value is not finite" % boundary)
            normalized.append(0.0 if number == 0 else number)
        evidence.append(
            {
                "dimensions": expected_dimensions,
                "sha256": _sha256_text(_canonical_json(normalized)),
            }
        )
    return evidence


def _validate_propositions(raw: object) -> List[Dict[str, object]]:
    if not isinstance(raw, list):
        raise PreviewValidationError("proposition model output must be a list")
    if len(raw) > _MAX_PROPOSITIONS:
        raise PreviewValidationError("proposition model output is too large")
    propositions_out: List[Dict[str, object]] = []
    seen_indexes = set()
    for item in raw:
        if not isinstance(item, dict):
            raise PreviewValidationError("each proposition must be an object")
        index = item.get("proposition_index")
        content = item.get("content")
        if isinstance(index, bool) or not isinstance(index, int) or index < 1:
            raise PreviewValidationError("proposition_index must be a positive integer")
        if index in seen_indexes:
            raise PreviewValidationError("proposition_index values must be unique")
        if not isinstance(content, str) or not content.strip():
            raise PreviewValidationError("proposition content must be non-empty text")
        content = content.strip()
        if len(content) > _MAX_PROPOSITION_CHARS:
            raise PreviewValidationError("proposition content is too large")
        seen_indexes.add(index)
        propositions_out.append({"proposition_index": index, "content": content})
    return sorted(propositions_out, key=lambda item: int(item["proposition_index"]))


def _validate_quote_spans(
    raw_spans: object,
    *,
    chunk_content: str,
) -> List[Tuple[int, int, str]]:
    if not isinstance(raw_spans, list):
        raise PreviewValidationError("quote proposer output must be a list")
    spans: List[Tuple[int, int, str]] = []
    for item in raw_spans:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise PreviewValidationError("quote proposal must be a start/end/text span")
        start, end, text = item
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or end > len(chunk_content)
            or not isinstance(text, str)
            or chunk_content[start:end] != text
        ):
            raise PreviewValidationError("quote proposal is not an exact source span")
        spans.append((start, end, text))
    return spans


def _default_chunk_embeddings(texts: List[str]) -> ModelComputation:
    return ModelComputation(
        output=shared_ingest._embed_batch_verified(texts),
        model=EMBEDDING_MODEL,
    )


def _default_propositions(
    text: str,
    *,
    document_id: str,
    speaker: str,
    prompt_version: str,
) -> ModelComputation:
    return ModelComputation(
        output=propositions.extract_propositions(
            text,
            doc_id=document_id,
            speaker=speaker,
            prompt_version=prompt_version,
        ),
        model=propositions.EXTRACTION_MODEL,
    )


def _default_proposition_embeddings(texts: List[str]) -> ModelComputation:
    return ModelComputation(
        output=shared_ingest._embed_batch_verified(texts),
        model=EMBEDDING_MODEL,
    )


def _known_usage(computations: Sequence[Mapping[str, object]]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for computation in computations:
        usage = computation.get("usage")
        if not isinstance(usage, Mapping):
            continue
        for field in _USAGE_FIELDS:
            value = usage.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[field] = totals.get(field, 0) + value
    return totals


def _known_cost(computations: Sequence[Mapping[str, object]]) -> Optional[float]:
    values = [item.get("cost_usd") for item in computations]
    known = [float(value) for value in values if isinstance(value, (int, float))]
    return round(sum(known), 12) if known else None


def build_preview(
    prepared: PreparedIngest,
    *,
    chunk_fn: Callable[[str], List[str]] = chunk_text,
    chunk_embeddings_fn: Callable[[List[str]], ModelComputation] = _default_chunk_embeddings,
    proposition_model_fn: Callable[..., ModelComputation] = _default_propositions,
    proposition_embeddings_fn: Callable[
        [List[str]], ModelComputation
    ] = _default_proposition_embeddings,
    quote_spans_fn: Callable[..., List[Tuple[int, int, str]]] = generate_candidate_spans,
    expected_embedding_dimensions: int = 1536,
) -> Dict[str, object]:
    """Compute a complete review report without accepting a persistence boundary."""
    _validate_prepared(prepared)
    if (
        isinstance(expected_embedding_dimensions, bool)
        or not isinstance(expected_embedding_dimensions, int)
        or expected_embedding_dimensions < 1
    ):
        raise PreviewValidationError("expected embedding dimensions must be positive")

    report_id = _report_id(prepared)
    chunks = _validate_chunks(chunk_fn(prepared.body_text))
    if len(chunks) != prepared.chunk_count:
        raise PreviewValidationError("prepared and preview chunk counts differ")

    raw_chunk_embeddings, chunk_computation = _normalize_computation(
        chunk_embeddings_fn(chunks), boundary="chunk_embeddings"
    )
    chunk_embedding_evidence = _validate_embeddings(
        raw_chunk_embeddings,
        expected_count=len(chunks),
        expected_dimensions=expected_embedding_dimensions,
        boundary="chunk_embeddings",
    )

    chunk_rows: List[Dict[str, object]] = []
    for index, (content, embedding) in enumerate(zip(chunks, chunk_embedding_evidence)):
        digest = _sha256_text(content)
        chunk_rows.append(
            {
                "id": _stable_item_id(report_id, "chunk", index, digest),
                "index": index,
                "content": content,
                "content_sha256": digest,
                "byte_count": len(content.encode("utf-8")),
                "embedding": {**embedding, "model": chunk_computation["model"]},
            }
        )

    raw_propositions, proposition_computation = _normalize_computation(
        proposition_model_fn(
            prepared.body_text,
            document_id=report_id,
            speaker=prepared.author,
            prompt_version=PROMPT_VERSION,
        ),
        boundary="proposition_extraction",
    )
    validated_propositions = _validate_propositions(raw_propositions)
    proposition_contents = [str(item["content"]) for item in validated_propositions]
    raw_proposition_embeddings, proposition_embedding_computation = _normalize_computation(
        proposition_embeddings_fn(proposition_contents),
        boundary="proposition_embeddings",
    )
    proposition_embedding_evidence = _validate_embeddings(
        raw_proposition_embeddings,
        expected_count=len(validated_propositions),
        expected_dimensions=expected_embedding_dimensions,
        boundary="proposition_embeddings",
    )

    chunk_ids = [str(chunk["id"]) for chunk in chunk_rows]
    fingerprint = propositions.prompt_fingerprint(PROMPT_VERSION)
    proposition_rows: List[Dict[str, object]] = []
    for item, embedding in zip(validated_propositions, proposition_embedding_evidence):
        index = int(item["proposition_index"])
        content = str(item["content"])
        digest = _sha256_text(content)
        proposition_rows.append(
            {
                "id": _stable_item_id(report_id, "proposition", index, digest),
                "proposition_index": index,
                "content": content,
                "content_sha256": digest,
                "prompt_version": PROMPT_VERSION,
                "prompt_fingerprint": fingerprint,
                "model": proposition_computation["model"],
                "eligible": False,
                "chunk_ids": list(chunk_ids),
                "embedding": {
                    **embedding,
                    "model": proposition_embedding_computation["model"],
                },
            }
        )

    quote_rows: List[Dict[str, object]] = []
    for chunk in chunk_rows:
        content = str(chunk["content"])
        spans = _validate_quote_spans(
            quote_spans_fn(content),
            chunk_content=content,
        )
        for start, end, text in spans:
            passage_start = max(0, start - _SURROUNDING_PASSAGE_CHARS)
            passage_end = min(len(content), end + _SURROUNDING_PASSAGE_CHARS)
            digest = _sha256_text(text)
            quote_rows.append(
                {
                    "id": _stable_item_id(report_id, "quote_proposal", len(quote_rows), digest),
                    "status": "proposal",
                    "chunk_id": chunk["id"],
                    "chunk_index": chunk["index"],
                    "start": start,
                    "end": end,
                    "text": text,
                    "text_sha256": digest,
                    "surrounding_passage": {
                        "start": passage_start,
                        "end": passage_end,
                        "text": content[passage_start:passage_end],
                    },
                }
            )

    computations = (
        chunk_computation,
        proposition_computation,
        proposition_embedding_computation,
    )
    report: Dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id,
        "mode": "full_compute_zero_database_write",
        "capture": {
            "row_id": prepared.row_id,
            "url": prepared.source_url,
            "content_sha256": prepared.content_sha256,
            "fetched_bytes": prepared.fetched_bytes,
            "filename": prepared.filename,
            "page_count": prepared.page_count,
            "extraction_evidence": dict(prepared.extraction_evidence),
        },
        "attribution": {
            "source_id": prepared.source_id,
            "teacher": prepared.author,
            "source_name": prepared.source_name,
            "license_status": prepared.license_status,
            "visibility": prepared.source_visibility,
        },
        "metadata": {
            "computed": prepared.metadata_computed,
            "title": prepared.title,
            "author": prepared.author,
            "source_name": prepared.source_name,
            "source_type": prepared.source_type,
            "source_kind": prepared.source_kind,
            "citation_mode": prepared.citation_mode,
            "year": prepared.year,
            "topic_tags": list(prepared.topic_tags),
            "bible_references": list(prepared.bible_references),
        },
        "chunks": chunk_rows,
        "propositions": proposition_rows,
        "quote_spans": quote_rows,
        "computation": {
            "chunk_embeddings": {
                **chunk_computation,
                "items": len(chunk_rows),
            },
            "proposition_extraction": {
                **proposition_computation,
                "items": len(proposition_rows),
                "prompt_version": PROMPT_VERSION,
                "prompt_fingerprint": fingerprint,
            },
            "proposition_embeddings": {
                **proposition_embedding_computation,
                "items": len(proposition_rows),
            },
            "known_tokens": _known_usage(computations),
            "known_cost_usd": _known_cost(computations),
        },
        "reconciliation": {
            "chunks_computed": len(chunk_rows),
            "chunk_embeddings_computed": len(chunk_embedding_evidence),
            "propositions_computed": len(proposition_rows),
            "proposition_embeddings_computed": len(proposition_embedding_evidence),
            "quote_spans_proposed": len(quote_rows),
            "database_rows_written": 0,
            "quote_rows_written": 0,
            "quotes_approved": 0,
        },
    }
    canonical_preview_json(report)
    return report


def preview_row(
    row: dict,
    *,
    db,
    db_params: dict,
    prepare_fn: Callable[..., PreparedIngest] = prepare_ingest,
    prepare_options: Optional[Mapping[str, object]] = None,
    preview_options: Optional[Mapping[str, object]] = None,
) -> Dict[str, object]:
    """Prepare and fully compute one row without exposing a corpus writer.

    ``prepare_ingest(..., dry_run=False)`` means "include metadata" in the
    existing processor contract; preparation itself is read-only. This
    orchestration deliberately accepts model boundaries but no corpus, queue,
    proposition-storage, or quote-approval persistence callable.
    """
    prepare_kwargs = dict(prepare_options or {})
    reserved = {"db", "db_params", "dry_run"}.intersection(prepare_kwargs)
    if reserved:
        raise PreviewValidationError("prepare_options contains reserved arguments")
    build_kwargs = dict(preview_options or {})
    prepared = prepare_fn(
        row,
        db=db,
        db_params=db_params,
        dry_run=False,
        **prepare_kwargs,
    )
    if not isinstance(prepared, PreparedIngest):
        raise PreviewValidationError("prepare boundary did not return PreparedIngest")
    return build_preview(prepared, **build_kwargs)
