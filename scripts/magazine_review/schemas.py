"""Immutable, fail-closed records for the New Wine review pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, Tuple


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STAGE_STATUSES = frozenset({"passed", "quarantined"})


class ArtifactValidationError(ValueError):
    """Raised when review evidence cannot safely be resumed or approved."""


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError("artifact_not_canonical_json") from exc


def _require_nonempty(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactValidationError(reason)
    return value


def _require_sha256(value: object, reason: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ArtifactValidationError(reason)
    return value


def _require_nonnegative_int(value: object, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ArtifactValidationError(reason)
    return value


def _require_positive_int(value: object, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ArtifactValidationError(reason)
    return value


def _string_tuple(value: Sequence[object], reason: str) -> Tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise ArtifactValidationError(reason)
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise ArtifactValidationError(reason)
    return result


def _require_exact_keys(raw: object, keys: set[str], reason: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != keys:
        raise ArtifactValidationError(reason)
    return raw


def _require_usage(value: object, reason: str) -> Mapping[str, float | int]:
    if not isinstance(value, Mapping):
        raise ArtifactValidationError(reason)
    for name, amount in value.items():
        _require_nonempty(name, reason)
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
            raise ArtifactValidationError(reason)
    return value


def _require_cost(value: object, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ArtifactValidationError(reason)
    return float(value)


def _require_timestamp(value: object, reason: str) -> str:
    return _require_nonempty(value, reason)


@dataclass(frozen=True)
class StageIdentity:
    """Immutable inputs that make a cached stage result eligible for resume."""

    schema_version: int
    input_hashes: Mapping[str, str]
    model: str
    prompt_fingerprint: str
    renderer_settings: Mapping[str, Any]

    def validate(self) -> None:
        _require_positive_int(self.schema_version, "schema_version_invalid")
        if not isinstance(self.input_hashes, Mapping) or not self.input_hashes:
            raise ArtifactValidationError("input_hashes_required")
        for name, digest in self.input_hashes.items():
            _require_nonempty(name, "input_hash_name_invalid")
            _require_sha256(digest, "input_hash_invalid")
        _require_nonempty(self.model, "stage_model_required")
        _require_sha256(self.prompt_fingerprint, "prompt_fingerprint_invalid")
        if not isinstance(self.renderer_settings, Mapping):
            raise ArtifactValidationError("renderer_settings_invalid")
        _canonical_json(self.to_dict())

    @property
    def digest(self) -> str:
        self.validate()
        return hashlib.sha256(_canonical_json(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "input_hashes": dict(self.input_hashes),
            "model": self.model,
            "prompt_fingerprint": self.prompt_fingerprint,
            "renderer_settings": dict(self.renderer_settings),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "StageIdentity":
        raw = _require_exact_keys(
            raw,
            {"schema_version", "input_hashes", "model", "prompt_fingerprint", "renderer_settings"},
            "stage_identity_invalid",
        )
        try:
            value = cls(
                schema_version=raw["schema_version"],
                input_hashes=raw["input_hashes"],
                model=raw["model"],
                prompt_fingerprint=raw["prompt_fingerprint"],
                renderer_settings=raw["renderer_settings"],
            )
        except KeyError as exc:
            raise ArtifactValidationError("stage_identity_field_missing") from exc
        value.validate()
        return value


@dataclass(frozen=True)
class OCRPage:
    page_number: int
    image_hash: str
    initial_text: str
    initial_text_hash: str
    initial_provider: str
    initial_model: str
    initial_prompt_fingerprint: str
    initial_usage: Mapping[str, float | int]
    initial_cost_usd: float
    initial_timestamp: str
    reviewer_model: str
    reviewer_prompt_fingerprint: str
    reviewer_complete: bool
    reviewer_reasons: Tuple[str, ...]
    reviewer_usage: Mapping[str, float | int]
    reviewer_cost_usd: float
    reviewer_timestamp: str
    repaired_text: str | None
    repaired_text_hash: str | None
    repair_provider: str | None
    repair_model: str | None
    repair_prompt_fingerprint: str | None
    repair_usage: Mapping[str, float | int] | None
    repair_cost_usd: float | None
    repair_timestamp: str | None
    text: str
    final_text_hash: str
    transcript_start: int
    transcript_end: int
    repair_attempts: int = 0
    complete: bool = True
    reasons: Tuple[str, ...] = ()

    def validate(self) -> None:
        _require_positive_int(self.page_number, "page_number_invalid")
        _require_sha256(self.image_hash, "page_image_hash_invalid")
        _require_nonempty(self.initial_text, "initial_text_required")
        if hashlib.sha256(self.initial_text.encode("utf-8")).hexdigest() != self.initial_text_hash:
            raise ArtifactValidationError("initial_text_hash_mismatch")
        _require_nonempty(self.initial_provider, "initial_provider_required")
        _require_nonempty(self.initial_model, "initial_model_required")
        _require_sha256(self.initial_prompt_fingerprint, "initial_prompt_fingerprint_invalid")
        _require_usage(self.initial_usage, "initial_usage_invalid")
        _require_cost(self.initial_cost_usd, "initial_cost_invalid")
        _require_timestamp(self.initial_timestamp, "initial_timestamp_required")
        _require_nonempty(self.reviewer_model, "reviewer_model_required")
        _require_sha256(self.reviewer_prompt_fingerprint, "reviewer_prompt_fingerprint_invalid")
        if not isinstance(self.reviewer_complete, bool):
            raise ArtifactValidationError("reviewer_complete_invalid")
        _string_tuple(self.reviewer_reasons, "reviewer_reasons_invalid")
        _require_usage(self.reviewer_usage, "reviewer_usage_invalid")
        _require_cost(self.reviewer_cost_usd, "reviewer_cost_invalid")
        _require_timestamp(self.reviewer_timestamp, "reviewer_timestamp_required")
        if not isinstance(self.text, str):
            raise ArtifactValidationError("page_text_invalid")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.final_text_hash:
            raise ArtifactValidationError("final_text_hash_mismatch")
        start = _require_nonnegative_int(self.transcript_start, "page_transcript_start_invalid")
        end = _require_nonnegative_int(self.transcript_end, "page_transcript_end_invalid")
        if end - start != len(self.text):
            raise ArtifactValidationError("page_transcript_span_mismatch")
        if isinstance(self.repair_attempts, bool) or self.repair_attempts not in (0, 1):
            raise ArtifactValidationError("page_repair_attempts_invalid")
        repair_values = (
            self.repaired_text,
            self.repaired_text_hash,
            self.repair_provider,
            self.repair_model,
            self.repair_prompt_fingerprint,
            self.repair_usage,
            self.repair_cost_usd,
            self.repair_timestamp,
        )
        if self.repair_attempts == 0 and any(value is not None for value in repair_values):
            raise ArtifactValidationError("unexpected_repair_evidence")
        if self.repair_attempts == 1:
            if not all(value is not None for value in repair_values):
                raise ArtifactValidationError("repair_evidence_required")
            _require_nonempty(self.repaired_text, "repaired_text_required")
            if hashlib.sha256(self.repaired_text.encode("utf-8")).hexdigest() != self.repaired_text_hash:
                raise ArtifactValidationError("repaired_text_hash_mismatch")
            _require_nonempty(self.repair_provider, "repair_provider_required")
            _require_nonempty(self.repair_model, "repair_model_required")
            _require_sha256(self.repair_prompt_fingerprint, "repair_prompt_fingerprint_invalid")
            _require_usage(self.repair_usage, "repair_usage_invalid")
            _require_cost(self.repair_cost_usd, "repair_cost_invalid")
            _require_timestamp(self.repair_timestamp, "repair_timestamp_required")
        if not isinstance(self.complete, bool):
            raise ArtifactValidationError("page_complete_invalid")
        _string_tuple(self.reasons, "page_reasons_invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "image_hash": self.image_hash,
            "initial_text": self.initial_text,
            "initial_text_hash": self.initial_text_hash,
            "initial_provider": self.initial_provider,
            "initial_model": self.initial_model,
            "initial_prompt_fingerprint": self.initial_prompt_fingerprint,
            "initial_usage": dict(self.initial_usage),
            "initial_cost_usd": self.initial_cost_usd,
            "initial_timestamp": self.initial_timestamp,
            "reviewer_model": self.reviewer_model,
            "reviewer_prompt_fingerprint": self.reviewer_prompt_fingerprint,
            "reviewer_complete": self.reviewer_complete,
            "reviewer_reasons": list(self.reviewer_reasons),
            "reviewer_usage": dict(self.reviewer_usage),
            "reviewer_cost_usd": self.reviewer_cost_usd,
            "reviewer_timestamp": self.reviewer_timestamp,
            "repaired_text": self.repaired_text,
            "repaired_text_hash": self.repaired_text_hash,
            "repair_provider": self.repair_provider,
            "repair_model": self.repair_model,
            "repair_prompt_fingerprint": self.repair_prompt_fingerprint,
            "repair_usage": dict(self.repair_usage) if self.repair_usage is not None else None,
            "repair_cost_usd": self.repair_cost_usd,
            "repair_timestamp": self.repair_timestamp,
            "text": self.text,
            "final_text_hash": self.final_text_hash,
            "transcript_start": self.transcript_start,
            "transcript_end": self.transcript_end,
            "repair_attempts": self.repair_attempts,
            "complete": self.complete,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OCRPage":
        raw = _require_exact_keys(
            raw,
            {
                "page_number", "image_hash", "initial_text", "initial_text_hash", "initial_provider",
                "initial_model", "initial_prompt_fingerprint", "initial_usage", "initial_cost_usd",
                "initial_timestamp", "reviewer_model", "reviewer_prompt_fingerprint", "reviewer_complete",
                "reviewer_reasons", "reviewer_usage", "reviewer_cost_usd", "reviewer_timestamp",
                "repaired_text", "repaired_text_hash", "repair_provider", "repair_model",
                "repair_prompt_fingerprint", "repair_usage", "repair_cost_usd", "repair_timestamp",
                "text", "final_text_hash", "transcript_start", "transcript_end", "repair_attempts",
                "complete", "reasons",
            },
            "ocr_page_invalid",
        )
        try:
            return cls(
                page_number=raw["page_number"],
                image_hash=raw["image_hash"],
                initial_text=raw["initial_text"],
                initial_text_hash=raw["initial_text_hash"],
                initial_provider=raw["initial_provider"],
                initial_model=raw["initial_model"],
                initial_prompt_fingerprint=raw["initial_prompt_fingerprint"],
                initial_usage=raw["initial_usage"],
                initial_cost_usd=raw["initial_cost_usd"],
                initial_timestamp=raw["initial_timestamp"],
                reviewer_model=raw["reviewer_model"],
                reviewer_prompt_fingerprint=raw["reviewer_prompt_fingerprint"],
                reviewer_complete=raw["reviewer_complete"],
                reviewer_reasons=tuple(raw["reviewer_reasons"]),
                reviewer_usage=raw["reviewer_usage"],
                reviewer_cost_usd=raw["reviewer_cost_usd"],
                reviewer_timestamp=raw["reviewer_timestamp"],
                repaired_text=raw["repaired_text"],
                repaired_text_hash=raw["repaired_text_hash"],
                repair_provider=raw["repair_provider"],
                repair_model=raw["repair_model"],
                repair_prompt_fingerprint=raw["repair_prompt_fingerprint"],
                repair_usage=raw["repair_usage"],
                repair_cost_usd=raw["repair_cost_usd"],
                repair_timestamp=raw["repair_timestamp"],
                text=raw["text"],
                final_text_hash=raw["final_text_hash"],
                transcript_start=raw["transcript_start"],
                transcript_end=raw["transcript_end"],
                repair_attempts=raw["repair_attempts"],
                complete=raw["complete"],
                reasons=tuple(raw["reasons"]),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("ocr_page_invalid") from exc


@dataclass(frozen=True)
class OCRManifest:
    identity: StageIdentity
    pdf_hash: str
    page_count: int
    pages: Tuple[OCRPage, ...]
    usage: Mapping[str, float | int]
    cost_usd: float
    status: str = "passed"
    quarantine_reasons: Tuple[str, ...] = ()

    def validate(self) -> None:
        self.identity.validate()
        _require_sha256(self.pdf_hash, "pdf_hash_invalid")
        _require_usage(self.usage, "ocr_usage_invalid")
        _require_cost(self.cost_usd, "ocr_cost_invalid")
        page_count = _require_positive_int(self.page_count, "page_count_invalid")
        if self.status not in _STAGE_STATUSES:
            raise ArtifactValidationError("ocr_status_invalid")
        _string_tuple(self.quarantine_reasons, "ocr_quarantine_reasons_invalid")
        if not isinstance(self.pages, tuple) or len(self.pages) != page_count:
            raise ArtifactValidationError("ocr_page_count_mismatch")
        if tuple(page.page_number for page in self.pages) != tuple(range(1, page_count + 1)):
            raise ArtifactValidationError("ocr_pages_not_contiguous")
        expected_start = 0
        for page in self.pages:
            page.validate()
            if page.transcript_start != expected_start:
                raise ArtifactValidationError("ocr_transcript_offsets_not_contiguous")
            expected_start = page.transcript_end
        if self.status == "passed" and not all(page.complete for page in self.pages):
            raise ArtifactValidationError("ocr_incomplete_page")

    @property
    def transcript(self) -> str:
        self.validate()
        return "".join(page.text for page in self.pages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "pdf_hash": self.pdf_hash,
            "page_count": self.page_count,
            "pages": [page.to_dict() for page in self.pages],
            "usage": dict(self.usage),
            "cost_usd": self.cost_usd,
            "status": self.status,
            "quarantine_reasons": list(self.quarantine_reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OCRManifest":
        raw = _require_exact_keys(
            raw,
            {"identity", "pdf_hash", "page_count", "pages", "usage", "cost_usd", "status", "quarantine_reasons"},
            "ocr_manifest_invalid",
        )
        try:
            value = cls(
                identity=StageIdentity.from_dict(raw["identity"]),
                pdf_hash=raw["pdf_hash"],
                page_count=raw["page_count"],
                pages=tuple(OCRPage.from_dict(item) for item in raw["pages"]),
                usage=raw["usage"],
                cost_usd=raw["cost_usd"],
                status=raw["status"],
                quarantine_reasons=tuple(raw["quarantine_reasons"]),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("ocr_manifest_invalid") from exc
        value.validate()
        return value


@dataclass(frozen=True)
class ArticleRecord:
    article_id: str
    title: str
    author: str
    source_pages: Tuple[int, ...]
    transcript_start: int
    transcript_end: int
    text: str
    text_hash: str
    start_coherent: bool
    end_coherent: bool
    transitions_ok: bool
    omissions: Tuple[str, ...]
    duplications: Tuple[str, ...]
    adjacent_bleed: Tuple[str, ...]
    attribution_ok: bool
    verdict: bool
    reasons: Tuple[str, ...] = ()

    def validate(self, transcript: str) -> None:
        _require_nonempty(self.article_id, "article_id_required")
        _require_nonempty(self.title, "article_title_required")
        _require_nonempty(self.author, "article_author_required")
        if not isinstance(self.source_pages, tuple) or not self.source_pages:
            raise ArtifactValidationError("article_source_pages_required")
        if tuple(self.source_pages) != tuple(sorted(set(self.source_pages))):
            raise ArtifactValidationError("article_source_pages_invalid")
        for page_number in self.source_pages:
            _require_positive_int(page_number, "article_source_page_invalid")
        start = _require_nonnegative_int(self.transcript_start, "article_transcript_start_invalid")
        end = _require_nonnegative_int(self.transcript_end, "article_transcript_end_invalid")
        if end <= start or end > len(transcript):
            raise ArtifactValidationError("article_span_invalid")
        if not isinstance(self.text, str) or transcript[start:end] != self.text:
            raise ArtifactValidationError("article_text_mismatch")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_hash:
            raise ArtifactValidationError("article_text_hash_mismatch")
        for value in (self.start_coherent, self.end_coherent, self.transitions_ok, self.attribution_ok, self.verdict):
            if not isinstance(value, bool):
                raise ArtifactValidationError("article_verdict_invalid")
        _string_tuple(self.omissions, "article_omissions_invalid")
        _string_tuple(self.duplications, "article_duplications_invalid")
        _string_tuple(self.adjacent_bleed, "article_adjacent_bleed_invalid")
        _string_tuple(self.reasons, "article_reasons_invalid")
        if self.verdict and (
            not self.start_coherent
            or not self.end_coherent
            or not self.transitions_ok
            or bool(self.omissions)
            or bool(self.duplications)
            or bool(self.adjacent_bleed)
            or not self.attribution_ok
        ):
            raise ArtifactValidationError("article_verdict_inconsistent")

    @property
    def article_hash(self) -> str:
        return self.text_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "title": self.title,
            "author": self.author,
            "source_pages": list(self.source_pages),
            "transcript_start": self.transcript_start,
            "transcript_end": self.transcript_end,
            "text": self.text,
            "text_hash": self.text_hash,
            "start_coherent": self.start_coherent,
            "end_coherent": self.end_coherent,
            "transitions_ok": self.transitions_ok,
            "omissions": list(self.omissions),
            "duplications": list(self.duplications),
            "adjacent_bleed": list(self.adjacent_bleed),
            "attribution_ok": self.attribution_ok,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ArticleRecord":
        raw = _require_exact_keys(
            raw,
            {
                "article_id", "title", "author", "source_pages", "transcript_start", "transcript_end",
                "text", "text_hash", "start_coherent", "end_coherent", "transitions_ok", "omissions",
                "duplications", "adjacent_bleed", "attribution_ok", "verdict", "reasons",
            },
            "article_record_invalid",
        )
        try:
            return cls(
                article_id=raw["article_id"],
                title=raw["title"],
                author=raw["author"],
                source_pages=tuple(raw["source_pages"]),
                transcript_start=raw["transcript_start"],
                transcript_end=raw["transcript_end"],
                text=raw["text"],
                text_hash=raw["text_hash"],
                start_coherent=raw["start_coherent"],
                end_coherent=raw["end_coherent"],
                transitions_ok=raw["transitions_ok"],
                omissions=tuple(raw["omissions"]),
                duplications=tuple(raw["duplications"]),
                adjacent_bleed=tuple(raw["adjacent_bleed"]),
                attribution_ok=raw["attribution_ok"],
                verdict=raw["verdict"],
                reasons=tuple(raw["reasons"]),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("article_record_invalid") from exc


@dataclass(frozen=True)
class ArticleManifest:
    identity: StageIdentity
    issue_hash: str
    ocr_artifact_hash: str
    transcript: str
    articles: Tuple[ArticleRecord, ...]
    segmentation_model: str
    segmentation_prompt_fingerprint: str
    segmentation_usage: Mapping[str, float | int]
    segmentation_cost_usd: float
    reviewer_model: str
    reviewer_prompt_fingerprint: str
    reviewer_usage: Mapping[str, float | int]
    reviewer_cost_usd: float
    status: str = "passed"
    quarantine_reasons: Tuple[str, ...] = ()

    def validate(self) -> None:
        self.identity.validate()
        _require_sha256(self.issue_hash, "issue_hash_invalid")
        _require_sha256(self.ocr_artifact_hash, "ocr_artifact_hash_invalid")
        if not isinstance(self.transcript, str):
            raise ArtifactValidationError("issue_transcript_invalid")
        if self.status not in _STAGE_STATUSES:
            raise ArtifactValidationError("article_status_invalid")
        _string_tuple(self.quarantine_reasons, "article_quarantine_reasons_invalid")
        _require_nonempty(self.segmentation_model, "segmentation_model_required")
        _require_sha256(self.segmentation_prompt_fingerprint, "segmentation_prompt_fingerprint_invalid")
        _require_usage(self.segmentation_usage, "segmentation_usage_invalid")
        _require_cost(self.segmentation_cost_usd, "segmentation_cost_invalid")
        _require_nonempty(self.reviewer_model, "article_reviewer_model_required")
        _require_sha256(self.reviewer_prompt_fingerprint, "article_reviewer_prompt_fingerprint_invalid")
        _require_usage(self.reviewer_usage, "article_reviewer_usage_invalid")
        _require_cost(self.reviewer_cost_usd, "article_reviewer_cost_invalid")
        if not isinstance(self.articles, tuple) or not self.articles:
            raise ArtifactValidationError("articles_required")
        seen_ids = set()
        previous_end = 0
        for article in self.articles:
            article.validate(self.transcript)
            if article.article_id in seen_ids:
                raise ArtifactValidationError("article_id_duplicate")
            if article.transcript_start < previous_end:
                raise ArtifactValidationError("article_spans_overlap")
            seen_ids.add(article.article_id)
            previous_end = article.transcript_end
        if self.status == "passed" and not all(article.verdict for article in self.articles):
            raise ArtifactValidationError("article_verdict_failed")

    def article_by_id(self, article_id: str) -> ArticleRecord:
        self.validate()
        for article in self.articles:
            if article.article_id == article_id:
                return article
        raise ArtifactValidationError("article_not_found")

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "issue_hash": self.issue_hash,
            "ocr_artifact_hash": self.ocr_artifact_hash,
            "transcript": self.transcript,
            "articles": [article.to_dict() for article in self.articles],
            "segmentation_model": self.segmentation_model,
            "segmentation_prompt_fingerprint": self.segmentation_prompt_fingerprint,
            "segmentation_usage": dict(self.segmentation_usage),
            "segmentation_cost_usd": self.segmentation_cost_usd,
            "reviewer_model": self.reviewer_model,
            "reviewer_prompt_fingerprint": self.reviewer_prompt_fingerprint,
            "reviewer_usage": dict(self.reviewer_usage),
            "reviewer_cost_usd": self.reviewer_cost_usd,
            "status": self.status,
            "quarantine_reasons": list(self.quarantine_reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ArticleManifest":
        raw = _require_exact_keys(
            raw,
            {
                "identity", "issue_hash", "ocr_artifact_hash", "transcript", "articles", "segmentation_model",
                "segmentation_prompt_fingerprint", "segmentation_usage", "segmentation_cost_usd", "reviewer_model",
                "reviewer_prompt_fingerprint", "reviewer_usage", "reviewer_cost_usd", "status", "quarantine_reasons",
            },
            "article_manifest_invalid",
        )
        try:
            value = cls(
                identity=StageIdentity.from_dict(raw["identity"]),
                issue_hash=raw["issue_hash"],
                ocr_artifact_hash=raw["ocr_artifact_hash"],
                transcript=raw["transcript"],
                articles=tuple(ArticleRecord.from_dict(item) for item in raw["articles"]),
                segmentation_model=raw["segmentation_model"],
                segmentation_prompt_fingerprint=raw["segmentation_prompt_fingerprint"],
                segmentation_usage=raw["segmentation_usage"],
                segmentation_cost_usd=raw["segmentation_cost_usd"],
                reviewer_model=raw["reviewer_model"],
                reviewer_prompt_fingerprint=raw["reviewer_prompt_fingerprint"],
                reviewer_usage=raw["reviewer_usage"],
                reviewer_cost_usd=raw["reviewer_cost_usd"],
                status=raw["status"],
                quarantine_reasons=tuple(raw["quarantine_reasons"]),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("article_manifest_invalid") from exc
        value.validate()
        return value


@dataclass(frozen=True)
class PropositionEvidence:
    proposition_index: int
    content: str
    evidence_text: str
    evidence_start: int
    evidence_end: int
    supported: bool
    missing_qualification: bool
    overstatement: bool
    attribution_ok: bool
    reviewer_reasons: Tuple[str, ...]

    def validate_shape(self, article_text: str) -> None:
        _require_positive_int(self.proposition_index, "proposition_index_invalid")
        _require_nonempty(self.content, "proposition_content_required")
        _require_nonempty(self.evidence_text, "evidence_text_required")
        start = _require_nonnegative_int(self.evidence_start, "evidence_start_invalid")
        end = _require_nonnegative_int(self.evidence_end, "evidence_end_invalid")
        if end <= start or end > len(article_text):
            raise ArtifactValidationError("evidence_offset_mismatch")
        if article_text[start:end] != self.evidence_text:
            raise ArtifactValidationError("evidence_offset_mismatch")
        flags = (
            self.supported,
            self.missing_qualification,
            self.overstatement,
            self.attribution_ok,
        )
        if any(not isinstance(flag, bool) for flag in flags):
            raise ArtifactValidationError("proposition_review_flags_invalid")
        _string_tuple(self.reviewer_reasons, "proposition_reviewer_reasons_invalid")

    def validate(self, article_text: str) -> None:
        self.validate_shape(article_text)
        if (
            not self.supported
            or self.missing_qualification
            or self.overstatement
            or not self.attribution_ok
        ):
            raise ArtifactValidationError("proposition_not_supported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposition_index": self.proposition_index,
            "content": self.content,
            "evidence_text": self.evidence_text,
            "evidence_start": self.evidence_start,
            "evidence_end": self.evidence_end,
            "supported": self.supported,
            "missing_qualification": self.missing_qualification,
            "overstatement": self.overstatement,
            "attribution_ok": self.attribution_ok,
            "reviewer_reasons": list(self.reviewer_reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PropositionEvidence":
        raw = _require_exact_keys(
            raw,
            {
                "proposition_index", "content", "evidence_text", "evidence_start", "evidence_end",
                "supported", "missing_qualification", "overstatement", "attribution_ok", "reviewer_reasons",
            },
            "proposition_evidence_invalid",
        )
        try:
            return cls(
                proposition_index=raw["proposition_index"],
                content=raw["content"],
                evidence_text=raw["evidence_text"],
                evidence_start=raw["evidence_start"],
                evidence_end=raw["evidence_end"],
                supported=raw["supported"],
                missing_qualification=raw["missing_qualification"],
                overstatement=raw["overstatement"],
                attribution_ok=raw["attribution_ok"],
                reviewer_reasons=tuple(raw["reviewer_reasons"]),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("proposition_evidence_invalid") from exc


@dataclass(frozen=True)
class PropositionReview:
    identity: StageIdentity
    article_id: str
    article_hash: str
    article_artifact_hash: str
    model: str
    prompt_version: str
    prompt_fingerprint: str
    extraction_usage: Mapping[str, float | int]
    extraction_cost_usd: float
    reviewer_model: str
    reviewer_prompt_fingerprint: str
    reviewer_usage: Mapping[str, float | int]
    reviewer_cost_usd: float
    article_text: str
    propositions: Tuple[PropositionEvidence, ...]
    status: str = "passed"
    reasons: Tuple[str, ...] = ()

    def validate(self, article_text: str | None = None) -> None:
        self.identity.validate()
        _require_nonempty(self.article_id, "proposition_article_id_required")
        _require_sha256(self.article_hash, "article_hash_invalid")
        _require_sha256(self.article_artifact_hash, "article_artifact_hash_invalid")
        _require_nonempty(self.model, "proposition_model_required")
        _require_nonempty(self.prompt_version, "prompt_version_required")
        _require_sha256(self.prompt_fingerprint, "proposition_prompt_fingerprint_invalid")
        _require_usage(self.extraction_usage, "proposition_extraction_usage_invalid")
        _require_cost(self.extraction_cost_usd, "proposition_extraction_cost_invalid")
        _require_nonempty(self.reviewer_model, "proposition_reviewer_model_required")
        _require_sha256(self.reviewer_prompt_fingerprint, "proposition_reviewer_prompt_fingerprint_invalid")
        _require_usage(self.reviewer_usage, "proposition_reviewer_usage_invalid")
        _require_cost(self.reviewer_cost_usd, "proposition_reviewer_cost_invalid")
        if self.status not in _STAGE_STATUSES:
            raise ArtifactValidationError("proposition_status_invalid")
        _string_tuple(self.reasons, "proposition_reasons_invalid")
        source_text = self.article_text if article_text is None else article_text
        if not isinstance(self.article_text, str) or not isinstance(source_text, str):
            raise ArtifactValidationError("proposition_article_text_invalid")
        if source_text != self.article_text:
            raise ArtifactValidationError("proposition_article_text_mismatch")
        if hashlib.sha256(source_text.encode("utf-8")).hexdigest() != self.article_hash:
            raise ArtifactValidationError("article_hash_mismatch")
        if not isinstance(self.propositions, tuple) or not self.propositions:
            raise ArtifactValidationError("propositions_required")
        if tuple(item.proposition_index for item in self.propositions) != tuple(
            range(1, len(self.propositions) + 1)
        ):
            raise ArtifactValidationError("proposition_indices_not_contiguous")
        for proposition in self.propositions:
            if self.status == "passed":
                proposition.validate(source_text)
            else:
                proposition.validate_shape(source_text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "article_id": self.article_id,
            "article_hash": self.article_hash,
            "article_artifact_hash": self.article_artifact_hash,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "prompt_fingerprint": self.prompt_fingerprint,
            "extraction_usage": dict(self.extraction_usage),
            "extraction_cost_usd": self.extraction_cost_usd,
            "reviewer_model": self.reviewer_model,
            "reviewer_prompt_fingerprint": self.reviewer_prompt_fingerprint,
            "reviewer_usage": dict(self.reviewer_usage),
            "reviewer_cost_usd": self.reviewer_cost_usd,
            "article_text": self.article_text,
            "propositions": [proposition.to_dict() for proposition in self.propositions],
            "status": self.status,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PropositionReview":
        raw = _require_exact_keys(
            raw,
            {
                "identity", "article_id", "article_hash", "article_artifact_hash", "model", "prompt_version",
                "prompt_fingerprint", "extraction_usage", "extraction_cost_usd", "reviewer_model",
                "reviewer_prompt_fingerprint", "reviewer_usage", "reviewer_cost_usd", "article_text",
                "propositions", "status", "reasons",
            },
            "proposition_review_invalid",
        )
        try:
            return cls(
                identity=StageIdentity.from_dict(raw["identity"]),
                article_id=raw["article_id"],
                article_hash=raw["article_hash"],
                article_artifact_hash=raw["article_artifact_hash"],
                model=raw["model"],
                prompt_version=raw["prompt_version"],
                prompt_fingerprint=raw["prompt_fingerprint"],
                extraction_usage=raw["extraction_usage"],
                extraction_cost_usd=raw["extraction_cost_usd"],
                reviewer_model=raw["reviewer_model"],
                reviewer_prompt_fingerprint=raw["reviewer_prompt_fingerprint"],
                reviewer_usage=raw["reviewer_usage"],
                reviewer_cost_usd=raw["reviewer_cost_usd"],
                article_text=raw["article_text"],
                propositions=tuple(PropositionEvidence.from_dict(item) for item in raw["propositions"]),
                status=raw["status"],
                reasons=tuple(raw["reasons"]),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("proposition_review_invalid") from exc


@dataclass(frozen=True)
class ApprovedPropositionSet:
    """Exact approved content plus the provenance ingestion must recheck."""

    article_id: str
    article_hash: str
    model: str
    prompt_version: str
    prompt_fingerprint: str
    propositions: Tuple[Tuple[int, str], ...]

    def validate(self) -> None:
        _require_nonempty(self.article_id, "approved_article_id_required")
        _require_sha256(self.article_hash, "approved_article_hash_invalid")
        _require_nonempty(self.model, "approved_model_required")
        _require_nonempty(self.prompt_version, "approved_prompt_version_required")
        _require_sha256(self.prompt_fingerprint, "approved_prompt_fingerprint_invalid")
        if not isinstance(self.propositions, tuple) or not self.propositions:
            raise ArtifactValidationError("approved_propositions_required")
        expected_index = 1
        for item in self.propositions:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ArtifactValidationError("approved_proposition_invalid")
            index, content = item
            if index != expected_index or isinstance(index, bool):
                raise ArtifactValidationError("approved_proposition_indices_not_contiguous")
            _require_nonempty(content, "approved_proposition_content_required")
            expected_index += 1

    @classmethod
    def from_review(cls, review: PropositionReview) -> "ApprovedPropositionSet":
        review.validate()
        if review.status != "passed":
            raise ArtifactValidationError("proposition_not_supported")
        for proposition in review.propositions:
            proposition.validate(review.article_text)
        value = cls(
            article_id=review.article_id,
            article_hash=review.article_hash,
            model=review.model,
            prompt_version=review.prompt_version,
            prompt_fingerprint=review.prompt_fingerprint,
            propositions=tuple(
                (proposition.proposition_index, proposition.content)
                for proposition in review.propositions
            ),
        )
        value.validate()
        return value

    def as_storage_list(self) -> list[dict[str, object]]:
        self.validate()
        return [
            {"proposition_index": index, "content": content}
            for index, content in self.propositions
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "article_hash": self.article_hash,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "prompt_fingerprint": self.prompt_fingerprint,
            "propositions": [list(item) for item in self.propositions],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ApprovedPropositionSet":
        raw = _require_exact_keys(
            raw,
            {"article_id", "article_hash", "model", "prompt_version", "prompt_fingerprint", "propositions"},
            "approved_proposition_set_invalid",
        )
        try:
            value = cls(
                article_id=raw["article_id"],
                article_hash=raw["article_hash"],
                model=raw["model"],
                prompt_version=raw["prompt_version"],
                prompt_fingerprint=raw["prompt_fingerprint"],
                propositions=tuple(tuple(item) for item in raw["propositions"]),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("approved_proposition_set_invalid") from exc
        value.validate()
        return value


@dataclass(frozen=True)
class IssueArtifacts:
    """The three passing evidence stages required for an issue approval."""

    ocr: OCRManifest
    articles: ArticleManifest
    proposition_reviews: Tuple[PropositionReview, ...]
    ocr_artifact_hash: str
    article_artifact_hash: str
    proposition_artifact_hashes: Mapping[str, str]

    def validate(self) -> None:
        self.ocr.validate()
        self.articles.validate()
        _require_sha256(self.ocr_artifact_hash, "ocr_artifact_hash_invalid")
        _require_sha256(self.article_artifact_hash, "article_artifact_hash_invalid")
        if not isinstance(self.proposition_artifact_hashes, Mapping):
            raise ArtifactValidationError("proposition_artifact_hashes_invalid")
        for article_id, artifact_hash in self.proposition_artifact_hashes.items():
            _require_nonempty(article_id, "proposition_artifact_hashes_invalid")
            _require_sha256(artifact_hash, "proposition_artifact_hashes_invalid")
        if self.articles.ocr_artifact_hash != self.ocr_artifact_hash:
            raise ArtifactValidationError("ocr_predecessor_hash_mismatch")
        if self.ocr.pdf_hash != self.articles.issue_hash:
            raise ArtifactValidationError("issue_hash_mismatch")
        if self.ocr.transcript != self.articles.transcript:
            raise ArtifactValidationError("issue_transcript_mismatch")
        if not isinstance(self.proposition_reviews, tuple):
            raise ArtifactValidationError("proposition_reviews_invalid")
        article_ids = {article.article_id for article in self.articles.articles}
        review_ids = set()
        for review in self.proposition_reviews:
            if review.article_id in review_ids:
                raise ArtifactValidationError("proposition_review_duplicate")
            article = self.articles.article_by_id(review.article_id)
            if review.article_hash != article.article_hash:
                raise ArtifactValidationError("article_hash_mismatch")
            if review.article_artifact_hash != self.article_artifact_hash:
                raise ArtifactValidationError("article_predecessor_hash_mismatch")
            review.validate(article.text)
            review_ids.add(review.article_id)
        if set(self.proposition_artifact_hashes) != review_ids:
            raise ArtifactValidationError("proposition_artifact_reconciliation_failed")
        if review_ids != article_ids:
            raise ArtifactValidationError("article_proposition_reconciliation_failed")
        ocr_pages = {page.page_number for page in self.ocr.pages}
        for article in self.articles.articles:
            if not set(article.source_pages).issubset(ocr_pages):
                raise ArtifactValidationError("article_source_page_missing")


@dataclass(frozen=True)
class IssueDecision:
    identity: StageIdentity
    issue_hash: str
    state: str
    ocr_artifact_hash: str
    article_artifact_hash: str
    proposition_artifact_hashes: Mapping[str, str]
    totals: Mapping[str, int]
    usage: Mapping[str, float | int]
    cost_usd: float
    gate_results: Mapping[str, bool]
    approved_propositions: Tuple[ApprovedPropositionSet, ...] = field(default_factory=tuple)
    reasons: Tuple[str, ...] = ()

    @classmethod
    def approve(cls, artifacts: IssueArtifacts) -> "IssueDecision":
        artifacts.validate()
        if artifacts.ocr.status != "passed" or artifacts.articles.status != "passed":
            raise ArtifactValidationError("issue_stage_not_passed")
        if any(review.status != "passed" for review in artifacts.proposition_reviews):
            raise ArtifactValidationError("issue_stage_not_passed")
        return cls(
            identity=artifacts.ocr.identity,
            issue_hash=artifacts.ocr.pdf_hash,
            state="approved",
            ocr_artifact_hash=artifacts.ocr_artifact_hash,
            article_artifact_hash=artifacts.article_artifact_hash,
            proposition_artifact_hashes=dict(artifacts.proposition_artifact_hashes),
            totals={
                "pages": artifacts.ocr.page_count,
                "articles": len(artifacts.articles.articles),
                "propositions": sum(len(review.propositions) for review in artifacts.proposition_reviews),
            },
            usage={
                "ocr": sum(artifacts.ocr.usage.values()),
                "article_segmentation": sum(artifacts.articles.segmentation_usage.values()),
                "article_review": sum(artifacts.articles.reviewer_usage.values()),
                "proposition_extraction": sum(sum(review.extraction_usage.values()) for review in artifacts.proposition_reviews),
                "proposition_review": sum(sum(review.reviewer_usage.values()) for review in artifacts.proposition_reviews),
            },
            cost_usd=(
                artifacts.ocr.cost_usd
                + artifacts.articles.segmentation_cost_usd
                + artifacts.articles.reviewer_cost_usd
                + sum(review.extraction_cost_usd + review.reviewer_cost_usd for review in artifacts.proposition_reviews)
            ),
            gate_results={"ocr": True, "articles": True, "propositions": True},
            approved_propositions=tuple(
                ApprovedPropositionSet.from_review(review)
                for review in artifacts.proposition_reviews
            ),
        )

    def validate(self) -> None:
        self.identity.validate()
        _require_sha256(self.issue_hash, "issue_hash_invalid")
        _require_sha256(self.ocr_artifact_hash, "ocr_artifact_hash_invalid")
        _require_sha256(self.article_artifact_hash, "article_artifact_hash_invalid")
        if not isinstance(self.proposition_artifact_hashes, Mapping) or not self.proposition_artifact_hashes:
            raise ArtifactValidationError("proposition_artifact_hashes_invalid")
        for article_id, artifact_hash in self.proposition_artifact_hashes.items():
            _require_nonempty(article_id, "proposition_artifact_hashes_invalid")
            _require_sha256(artifact_hash, "proposition_artifact_hashes_invalid")
        if not isinstance(self.totals, Mapping) or set(self.totals) != {"pages", "articles", "propositions"}:
            raise ArtifactValidationError("issue_totals_invalid")
        for total in self.totals.values():
            _require_nonnegative_int(total, "issue_totals_invalid")
        _require_usage(self.usage, "issue_usage_invalid")
        _require_cost(self.cost_usd, "issue_cost_invalid")
        if not isinstance(self.gate_results, Mapping) or set(self.gate_results) != {"ocr", "articles", "propositions"}:
            raise ArtifactValidationError("issue_gate_results_invalid")
        if any(not isinstance(value, bool) for value in self.gate_results.values()):
            raise ArtifactValidationError("issue_gate_results_invalid")
        if self.state == "approved" and not all(self.gate_results.values()):
            raise ArtifactValidationError("issue_gate_failed")
        if self.state not in {"approved", "quarantined", "pipeline_error"}:
            raise ArtifactValidationError("issue_state_invalid")
        _string_tuple(self.reasons, "issue_reasons_invalid")
        if not isinstance(self.approved_propositions, tuple):
            raise ArtifactValidationError("approved_proposition_sets_invalid")
        if self.state == "approved" and not self.approved_propositions:
            raise ArtifactValidationError("approved_proposition_sets_required")
        seen_ids = set()
        for approved in self.approved_propositions:
            approved.validate()
            if approved.article_id in seen_ids:
                raise ArtifactValidationError("approved_article_id_duplicate")
            seen_ids.add(approved.article_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "issue_hash": self.issue_hash,
            "state": self.state,
            "ocr_artifact_hash": self.ocr_artifact_hash,
            "article_artifact_hash": self.article_artifact_hash,
            "proposition_artifact_hashes": dict(self.proposition_artifact_hashes),
            "totals": dict(self.totals),
            "usage": dict(self.usage),
            "cost_usd": self.cost_usd,
            "gate_results": dict(self.gate_results),
            "approved_propositions": [item.to_dict() for item in self.approved_propositions],
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "IssueDecision":
        raw = _require_exact_keys(
            raw,
            {
                "identity", "issue_hash", "state", "ocr_artifact_hash", "article_artifact_hash",
                "proposition_artifact_hashes", "totals", "usage", "cost_usd", "gate_results",
                "approved_propositions", "reasons",
            },
            "issue_decision_invalid",
        )
        try:
            value = cls(
                identity=StageIdentity.from_dict(raw["identity"]),
                issue_hash=raw["issue_hash"],
                state=raw["state"],
                ocr_artifact_hash=raw["ocr_artifact_hash"],
                article_artifact_hash=raw["article_artifact_hash"],
                proposition_artifact_hashes=raw["proposition_artifact_hashes"],
                totals=raw["totals"],
                usage=raw["usage"],
                cost_usd=raw["cost_usd"],
                gate_results=raw["gate_results"],
                approved_propositions=tuple(
                    ApprovedPropositionSet.from_dict(item)
                    for item in raw["approved_propositions"]
                ),
                reasons=tuple(raw["reasons"]),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("issue_decision_invalid") from exc
        value.validate()
        return value
