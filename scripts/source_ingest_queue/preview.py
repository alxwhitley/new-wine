"""Full-compute, zero-database-write previews for staged web articles."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import propositions
import shared_ingest
from app.services import metadata as metadata_service
from app.services.chunker import chunk_text
from quote_candidates import generate_candidate_spans
from source_ingest_queue.processor import PreparedIngest, prepare_ingest


SCHEMA_VERSION = "source_ingest_preview.v2"
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
    details: Optional[Mapping[str, object]] = None


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
    """Atomically publish a mode-0600 report without following local links."""
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
    capture_id = report.get("capture_id")
    if (
        not isinstance(capture_id, str)
        or len(capture_id) != 64
        or any(ch not in "0123456789abcdef" for ch in capture_id)
    ):
        raise PreviewValidationError("capture_id is not a lowercase SHA-256 digest")
    expected_capture_id = _capture_identity_digest(
        schema_version=report.get("schema_version"),
        row_id=capture.get("row_id"),
        url=capture.get("url"),
        content_sha256=capture.get("content_sha256"),
        fetched_bytes=capture.get("fetched_bytes"),
        source_id=attribution.get("source_id"),
    )
    if capture_id != expected_capture_id:
        raise PreviewValidationError("capture_id does not match capture identity")
    if report_id != _content_report_digest(report):
        raise PreviewValidationError("report_id does not match report content")
    payload = canonical_preview_json(report).encode("utf-8")
    directory = Path(review_dir)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / (report_id + ".json")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_descriptor = os.open(directory, directory_flags)
    except OSError as exc:
        raise PreviewValidationError("review_dir must be a real directory") from exc
    temporary_name: Optional[str] = None

    def _validate_regular_artifact(info: os.stat_result) -> None:
        if not stat.S_ISREG(info.st_mode):
            raise PreviewCollisionError(
                "preview identity is occupied by a non-regular file"
            )
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise PreviewCollisionError("preview artifact mode is not 0600")
        if info.st_nlink != 1:
            raise PreviewCollisionError("preview artifact has an unsafe link count")

    def _accept_existing() -> Optional[Path]:
        final_name = report_id + ".json"
        try:
            path_info = os.stat(
                final_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return None
        _validate_regular_artifact(path_info)
        if path_info.st_size != len(payload):
            raise PreviewCollisionError("preview identity already has different bytes")
        read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(
                final_name,
                read_flags,
                dir_fd=directory_descriptor,
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise PreviewCollisionError(
                "preview identity could not be opened without following links"
            ) from exc
        try:
            opened_info = os.fstat(descriptor)
            _validate_regular_artifact(opened_info)
            if opened_info.st_size != len(payload):
                raise PreviewCollisionError(
                    "preview identity already has different bytes"
                )
            if (opened_info.st_dev, opened_info.st_ino) != (
                path_info.st_dev,
                path_info.st_ino,
            ):
                raise PreviewCollisionError("preview identity changed during validation")
            chunks = []
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            final_info = os.fstat(descriptor)
            _validate_regular_artifact(final_info)
            try:
                final_path_info = os.stat(
                    final_name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError as exc:
                raise PreviewCollisionError(
                    "preview identity disappeared during validation"
                ) from exc
            if (final_path_info.st_dev, final_path_info.st_ino) != (
                final_info.st_dev,
                final_info.st_ino,
            ):
                raise PreviewCollisionError("preview identity changed during validation")
        finally:
            os.close(descriptor)
        if b"".join(chunks) != payload:
            raise PreviewCollisionError("preview identity already has different bytes")
        return path

    try:
        directory_info = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(directory_info.st_mode):
            raise PreviewValidationError("review_dir must be a real directory")
        existing = _accept_existing()
        if existing is not None:
            return existing

        candidate_name = ".%s.%s.tmp" % (report_id, os.urandom(16).hex())
        temporary_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        temporary_flags |= getattr(os, "O_NOFOLLOW", 0)
        temporary_descriptor = os.open(
            candidate_name,
            temporary_flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        temporary_name = candidate_name
        try:
            os.fchmod(temporary_descriptor, 0o600)
            temporary_info = os.fstat(temporary_descriptor)
            _validate_regular_artifact(temporary_info)
            remaining = memoryview(payload)
            while remaining:
                written = os.write(temporary_descriptor, remaining)
                if written <= 0:
                    raise OSError("preview artifact write made no progress")
                remaining = remaining[written:]
            os.fsync(temporary_descriptor)
        finally:
            os.close(temporary_descriptor)

        final_name = report_id + ".json"
        try:
            os.link(
                temporary_name,
                final_name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            existing = _accept_existing()
            if existing is None:
                raise PreviewCollisionError(
                    "preview identity changed during atomic publication"
                )
            return existing

        os.unlink(temporary_name, dir_fd=directory_descriptor)
        temporary_name = None
        os.fsync(directory_descriptor)
        published = _accept_existing()
        if published is None:
            raise PreviewCollisionError("published preview identity disappeared")
        return published
    finally:
        try:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=directory_descriptor)
                except FileNotFoundError:
                    pass
                else:
                    os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _capture_identity_digest(
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


def _capture_id(prepared: PreparedIngest) -> str:
    return _capture_identity_digest(
        schema_version=SCHEMA_VERSION,
        row_id=prepared.row_id,
        url=prepared.source_url,
        content_sha256=prepared.content_sha256,
        fetched_bytes=prepared.fetched_bytes,
        source_id=prepared.source_id,
    )


def _content_report_digest(report: Mapping[str, object]) -> str:
    report_content = dict(report)
    report_content.pop("report_id", None)
    return _sha256_text(_canonical_json(report_content))


def _stable_item_id(capture_id: str, kind: str, index: int, digest: str) -> str:
    return _sha256_text("%s:%s:%d:%s" % (capture_id, kind, index, digest))


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
    details = result.details
    if details is not None:
        if not isinstance(details, Mapping):
            raise PreviewValidationError("%s details must be an object" % boundary)
        details = dict(details)
        _canonical_json(details)
    evidence: Dict[str, object] = {
        "model": result.model.strip(),
        "usage": (
            {"status": "available", **usage}
            if usage is not None
            else {"status": "unavailable"}
        ),
        "cost_usd": (
            {"status": "available", "value": cost}
            if cost is not None
            else {"status": "unavailable"}
        ),
    }
    if details is not None:
        evidence["details"] = details
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
) -> Tuple[List[List[float]], List[Dict[str, object]]]:
    if not isinstance(raw_embeddings, list) or len(raw_embeddings) != expected_count:
        raise PreviewValidationError("%s embedding count mismatch" % boundary)
    normalized_vectors: List[List[float]] = []
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
        normalized_vectors.append(normalized)
        evidence.append(
            {
                "dimensions": expected_dimensions,
                "sha256": _sha256_text(_canonical_json(normalized)),
            }
        )
    return normalized_vectors, evidence


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
        if len(content) > _MAX_PROPOSITION_CHARS:
            raise PreviewValidationError("proposition content is too large")
        seen_indexes.add(index)
        propositions_out.append({"proposition_index": index, "content": content})
    return propositions_out


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


def _default_metadata(text: str) -> metadata_service.MetadataComputation:
    return metadata_service.extract_metadata_with_evidence(text)


def _embedding_model_evidence(
    computations: Sequence[shared_ingest.EmbeddingBatchComputation],
) -> Tuple[str, Dict[str, object]]:
    response_models = [
        model
        for computation in computations
        for model in computation.response_models
    ]
    observed_models = {
        model for model in response_models if isinstance(model, str)
    }
    statuses = [computation.model_status for computation in computations]
    if statuses and all(status == "available" for status in statuses):
        status = "available" if len(observed_models) == 1 else "ambiguous"
    elif statuses and all(status == "unavailable" for status in statuses):
        status = "unavailable"
    else:
        status = "ambiguous"
    model = (
        next(iter(observed_models))
        if status == "available"
        else EMBEDDING_MODEL
    )
    return model, {
        "model_evidence": {
            "status": status,
            "response_models": response_models,
        }
    }


def _default_chunk_embeddings(texts: List[str]) -> ModelComputation:
    computation = shared_ingest._embed_batch_verified_with_evidence(texts)
    model, details = _embedding_model_evidence([computation])
    return ModelComputation(
        output=computation.output,
        model=model,
        usage=computation.usage,
        cost_usd=computation.cost_usd,
        details=details,
    )


def _default_propositions(
    text: str,
    *,
    document_id: str,
    speaker: str,
    prompt_version: str,
) -> ModelComputation:
    computation = propositions.extract_propositions_with_evidence(
        text,
        doc_id=document_id,
        speaker=speaker,
        prompt_version=prompt_version,
        grounding_review_sink=None,
    )
    grounding = computation.grounding
    return ModelComputation(
        output=computation.output,
        model=computation.model,
        usage=computation.usage,
        cost_usd=computation.cost_usd,
        details={
            "reference_grounding": {
                "references_found": grounding.n_found,
                "references_grounded": grounding.n_grounded,
                "references_stripped_fabricated": grounding.n_stripped_fabricated,
                "references_stripped_uncertain": grounding.n_stripped_uncertain,
                "references_kept_arbitration": grounding.n_kept_arbitration,
                "arbitration_items": len(grounding.review_records),
            }
        },
    )


def _default_proposition_embeddings(texts: List[str]) -> ModelComputation:
    if not texts:
        return ModelComputation(
            output=[],
            model=EMBEDDING_MODEL,
            details={
                "model_evidence": {
                    "status": "unavailable",
                    "response_models": [],
                }
            },
        )
    computations = [
        shared_ingest._embed_batch_verified_with_evidence([text])
        for text in texts
    ]
    model, details = _embedding_model_evidence(computations)
    usage = None
    if all(item.usage is not None for item in computations):
        common_fields = set.intersection(
            *(set(item.usage or {}) for item in computations)
        )
        usage = {
            field: sum((item.usage or {})[field] for item in computations)
            for field in _USAGE_FIELDS
            if field in common_fields
        } or None
    costs = [item.cost_usd for item in computations]
    cost_usd = (
        sum(float(value) for value in costs if value is not None)
        if all(value is not None for value in costs)
        else None
    )
    return ModelComputation(
        output=[vector for item in computations for vector in item.output],
        model=model,
        usage=usage,
        cost_usd=cost_usd,
        details=details,
    )


def _unavailable_computation(reason: str) -> Dict[str, object]:
    return {
        "model": None,
        "usage": {"status": "unavailable"},
        "cost_usd": {"status": "unavailable"},
        "reason": reason,
    }


def _known_usage(computations: Sequence[Mapping[str, object]]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for computation in computations:
        usage = computation.get("usage")
        if not isinstance(usage, Mapping):
            continue
        if usage.get("status") != "available":
            continue
        for field in _USAGE_FIELDS:
            value = usage.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[field] = totals.get(field, 0) + value
    return totals


def _known_cost(computations: Sequence[Mapping[str, object]]) -> Optional[float]:
    values = [item.get("cost_usd") for item in computations]
    known = [
        float(value["value"])
        for value in values
        if isinstance(value, Mapping)
        and value.get("status") == "available"
        and isinstance(value.get("value"), (int, float))
    ]
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

    capture_id = _capture_id(prepared)
    if isinstance(
        prepared.metadata_computation,
        metadata_service.MetadataComputation,
    ):
        metadata_boundary = prepared.metadata_computation
        metadata_computation = _normalize_computation(
            ModelComputation(
                output=metadata_boundary.output,
                model=metadata_boundary.model,
                usage=metadata_boundary.usage,
                cost_usd=metadata_boundary.cost_usd,
            ),
            boundary="metadata",
        )[1]
    else:
        metadata_computation = _unavailable_computation(
            "metadata provider evidence was not retained by preparation"
        )
    chunks = _validate_chunks(chunk_fn(prepared.body_text))
    if len(chunks) != prepared.chunk_count:
        raise PreviewValidationError("prepared and preview chunk counts differ")

    raw_chunk_embeddings, chunk_computation = _normalize_computation(
        chunk_embeddings_fn(chunks), boundary="chunk_embeddings"
    )
    _chunk_embedding_vectors, chunk_embedding_evidence = _validate_embeddings(
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
                "id": _stable_item_id(capture_id, "chunk", index, digest),
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
            document_id=capture_id,
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
    proposition_embedding_vectors, proposition_embedding_evidence = _validate_embeddings(
        raw_proposition_embeddings,
        expected_count=len(validated_propositions),
        expected_dimensions=expected_embedding_dimensions,
        boundary="proposition_embeddings",
    )

    chunk_ids = [str(chunk["id"]) for chunk in chunk_rows]
    # Provider response labels remain computation evidence. Proposed storage
    # rows use the same canonical model provenance as the production writer.
    proposition_payload = propositions.build_proposition_payload(
        validated_propositions,
        proposition_embedding_vectors,
        prompt_version=PROMPT_VERSION,
        model=propositions.EXTRACTION_MODEL,
        embedding_model=str(proposition_embedding_computation["model"]),
    )
    fingerprint = propositions.prompt_fingerprint(PROMPT_VERSION)
    proposition_rows: List[Dict[str, object]] = []
    for item, embedding in zip(proposition_payload, proposition_embedding_evidence):
        index = item.proposition_index
        content = item.content
        digest = _sha256_text(content)
        proposition_rows.append(
            {
                "id": _stable_item_id(capture_id, "proposition", index, digest),
                "proposition_index": index,
                "content": content,
                "content_sha256": digest,
                "prompt_version": item.prompt_version,
                "prompt_fingerprint": item.prompt_fingerprint,
                "model": item.model,
                "eligible": False,
                "chunk_ids": list(chunk_ids),
                "embedding": {
                    **embedding,
                    "model": item.embedding_model,
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
                    "id": _stable_item_id(
                        capture_id,
                        "quote_proposal",
                        len(quote_rows),
                        digest,
                    ),
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

    grounding_details = proposition_computation.get("details")
    grounding = (
        grounding_details.get("reference_grounding")
        if isinstance(grounding_details, Mapping)
        else None
    )
    arbitration_computation = _unavailable_computation(
        "reference-grounding arbitration boundary does not expose provider evidence"
    )
    arbitration_computation["items"] = (
        grounding.get("arbitration_items", 0)
        if isinstance(grounding, Mapping)
        else 0
    )
    computations = (
        metadata_computation,
        chunk_computation,
        proposition_computation,
        proposition_embedding_computation,
    )
    report: Dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "capture_id": capture_id,
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
            "metadata": metadata_computation,
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
            "reference_grounding_arbitration": arbitration_computation,
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
    report["report_id"] = _content_report_digest(report)
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
    prepare_kwargs.setdefault("metadata_fn", _default_metadata)
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
