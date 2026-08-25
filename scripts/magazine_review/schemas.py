"""Immutable, fail-closed records for the New Wine review pipeline."""

from __future__ import annotations

import hashlib
import json
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
        if not isinstance(raw, Mapping):
            raise ArtifactValidationError("stage_identity_invalid")
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
    text: str
    transcript_start: int
    transcript_end: int
    repair_attempts: int = 0
    complete: bool = True
    reasons: Tuple[str, ...] = ()

    def validate(self) -> None:
        _require_positive_int(self.page_number, "page_number_invalid")
        _require_sha256(self.image_hash, "page_image_hash_invalid")
        if not isinstance(self.text, str):
            raise ArtifactValidationError("page_text_invalid")
        start = _require_nonnegative_int(self.transcript_start, "page_transcript_start_invalid")
        end = _require_nonnegative_int(self.transcript_end, "page_transcript_end_invalid")
        if end - start != len(self.text):
            raise ArtifactValidationError("page_transcript_span_mismatch")
        if isinstance(self.repair_attempts, bool) or self.repair_attempts not in (0, 1):
            raise ArtifactValidationError("page_repair_attempts_invalid")
        if not isinstance(self.complete, bool):
            raise ArtifactValidationError("page_complete_invalid")
        _string_tuple(self.reasons, "page_reasons_invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "image_hash": self.image_hash,
            "text": self.text,
            "transcript_start": self.transcript_start,
            "transcript_end": self.transcript_end,
            "repair_attempts": self.repair_attempts,
            "complete": self.complete,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OCRPage":
        try:
            return cls(
                page_number=raw["page_number"],
                image_hash=raw["image_hash"],
                text=raw["text"],
                transcript_start=raw["transcript_start"],
                transcript_end=raw["transcript_end"],
                repair_attempts=raw.get("repair_attempts", 0),
                complete=raw.get("complete", True),
                reasons=tuple(raw.get("reasons", ())),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("ocr_page_invalid") from exc


@dataclass(frozen=True)
class OCRManifest:
    identity: StageIdentity
    pdf_hash: str
    page_count: int
    pages: Tuple[OCRPage, ...]
    status: str = "passed"
    quarantine_reasons: Tuple[str, ...] = ()

    def validate(self) -> None:
        self.identity.validate()
        _require_sha256(self.pdf_hash, "pdf_hash_invalid")
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
            "status": self.status,
            "quarantine_reasons": list(self.quarantine_reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OCRManifest":
        try:
            value = cls(
                identity=StageIdentity.from_dict(raw["identity"]),
                pdf_hash=raw["pdf_hash"],
                page_count=raw["page_count"],
                pages=tuple(OCRPage.from_dict(item) for item in raw["pages"]),
                status=raw.get("status", "passed"),
                quarantine_reasons=tuple(raw.get("quarantine_reasons", ())),
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
        _string_tuple(self.reasons, "article_reasons_invalid")

    @property
    def article_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "title": self.title,
            "author": self.author,
            "source_pages": list(self.source_pages),
            "transcript_start": self.transcript_start,
            "transcript_end": self.transcript_end,
            "text": self.text,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ArticleRecord":
        try:
            return cls(
                article_id=raw["article_id"],
                title=raw["title"],
                author=raw["author"],
                source_pages=tuple(raw["source_pages"]),
                transcript_start=raw["transcript_start"],
                transcript_end=raw["transcript_end"],
                text=raw["text"],
                reasons=tuple(raw.get("reasons", ())),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("article_record_invalid") from exc


@dataclass(frozen=True)
class ArticleManifest:
    identity: StageIdentity
    issue_hash: str
    transcript: str
    articles: Tuple[ArticleRecord, ...]
    status: str = "passed"
    quarantine_reasons: Tuple[str, ...] = ()

    def validate(self) -> None:
        self.identity.validate()
        _require_sha256(self.issue_hash, "issue_hash_invalid")
        if not isinstance(self.transcript, str):
            raise ArtifactValidationError("issue_transcript_invalid")
        if self.status not in _STAGE_STATUSES:
            raise ArtifactValidationError("article_status_invalid")
        _string_tuple(self.quarantine_reasons, "article_quarantine_reasons_invalid")
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
            "transcript": self.transcript,
            "articles": [article.to_dict() for article in self.articles],
            "status": self.status,
            "quarantine_reasons": list(self.quarantine_reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ArticleManifest":
        try:
            value = cls(
                identity=StageIdentity.from_dict(raw["identity"]),
                issue_hash=raw["issue_hash"],
                transcript=raw["transcript"],
                articles=tuple(ArticleRecord.from_dict(item) for item in raw["articles"]),
                status=raw.get("status", "passed"),
                quarantine_reasons=tuple(raw.get("quarantine_reasons", ())),
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
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PropositionEvidence":
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
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("proposition_evidence_invalid") from exc


@dataclass(frozen=True)
class PropositionReview:
    identity: StageIdentity
    article_id: str
    article_hash: str
    model: str
    prompt_version: str
    prompt_fingerprint: str
    article_text: str
    propositions: Tuple[PropositionEvidence, ...]
    status: str = "passed"
    reasons: Tuple[str, ...] = ()

    def validate(self, article_text: str | None = None) -> None:
        self.identity.validate()
        _require_nonempty(self.article_id, "proposition_article_id_required")
        _require_sha256(self.article_hash, "article_hash_invalid")
        _require_nonempty(self.model, "proposition_model_required")
        _require_nonempty(self.prompt_version, "prompt_version_required")
        _require_sha256(self.prompt_fingerprint, "proposition_prompt_fingerprint_invalid")
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
            "model": self.model,
            "prompt_version": self.prompt_version,
            "prompt_fingerprint": self.prompt_fingerprint,
            "article_text": self.article_text,
            "propositions": [proposition.to_dict() for proposition in self.propositions],
            "status": self.status,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PropositionReview":
        try:
            return cls(
                identity=StageIdentity.from_dict(raw["identity"]),
                article_id=raw["article_id"],
                article_hash=raw["article_hash"],
                model=raw["model"],
                prompt_version=raw["prompt_version"],
                prompt_fingerprint=raw["prompt_fingerprint"],
                article_text=raw["article_text"],
                propositions=tuple(PropositionEvidence.from_dict(item) for item in raw["propositions"]),
                status=raw.get("status", "passed"),
                reasons=tuple(raw.get("reasons", ())),
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

    def validate(self) -> None:
        self.ocr.validate()
        self.articles.validate()
        if self.ocr.identity != self.articles.identity:
            raise ArtifactValidationError("stage_identity_mismatch")
        if self.ocr.pdf_hash != self.articles.issue_hash:
            raise ArtifactValidationError("issue_hash_mismatch")
        if self.ocr.transcript != self.articles.transcript:
            raise ArtifactValidationError("issue_transcript_mismatch")
        if not isinstance(self.proposition_reviews, tuple):
            raise ArtifactValidationError("proposition_reviews_invalid")
        article_ids = {article.article_id for article in self.articles.articles}
        review_ids = set()
        for review in self.proposition_reviews:
            if review.identity != self.articles.identity:
                raise ArtifactValidationError("stage_identity_mismatch")
            article = self.articles.article_by_id(review.article_id)
            if review.article_hash != article.article_hash:
                raise ArtifactValidationError("article_hash_mismatch")
            review.validate(article.text)
            review_ids.add(review.article_id)
        if review_ids != article_ids:
            raise ArtifactValidationError("article_proposition_reconciliation_failed")


@dataclass(frozen=True)
class IssueDecision:
    identity: StageIdentity
    issue_hash: str
    state: str
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
            approved_propositions=tuple(
                ApprovedPropositionSet.from_review(review)
                for review in artifacts.proposition_reviews
            ),
        )

    def validate(self) -> None:
        self.identity.validate()
        _require_sha256(self.issue_hash, "issue_hash_invalid")
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
            "approved_propositions": [item.to_dict() for item in self.approved_propositions],
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "IssueDecision":
        try:
            value = cls(
                identity=StageIdentity.from_dict(raw["identity"]),
                issue_hash=raw["issue_hash"],
                state=raw["state"],
                approved_propositions=tuple(
                    ApprovedPropositionSet.from_dict(item)
                    for item in raw.get("approved_propositions", ())
                ),
                reasons=tuple(raw.get("reasons", ())),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ArtifactValidationError("issue_decision_invalid") from exc
        value.validate()
        return value
