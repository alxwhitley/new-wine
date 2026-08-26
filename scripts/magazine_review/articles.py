"""Fail-closed, issue-wide magazine article segmentation and review."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import replace
from typing import Any, Mapping, Protocol

from .ocr import VerifiedIssueTranscript
from .schemas import (
    ArticleManifest,
    ArticleRecord,
    ArtifactValidationError,
    StageIdentity,
)


ARTICLE_MODEL = "openai/gpt-oss-120b"
SEGMENTATION_REASONING = "low"
REVIEW_REASONING = "medium"
SEGMENTATION_INSTRUCTIONS = (
    "Segment every authored article in the complete verified magazine transcript. "
    "Return each article exactly once, in transcript order, with its stable identity, "
    "unique output filename, title, author, and exact transcript span. Do not return "
    "article text or source pages: the pipeline derives them from the verified "
    "transcript after validating each span. Return spans in ascending transcript "
    "order; article spans must never overlap."
)
REVIEW_INSTRUCTIONS = (
    "Review the complete proposed article set against the complete verified issue in "
    "fresh context. For every article decide whether its beginning is genuine, ending "
    "is coherent, cross-page transitions are intact, content is omitted or duplicated, "
    "adjacent material bleeds into it, and author attribution is correct. Report a "
    "specific reason for every failed field. Also issue one binding whole-issue "
    "coverage verdict and identify every substantive authored article omitted from "
    "the proposed set, with its exact transcript span and a specific reason."
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SEMANTIC_FIELDS = (
    "start_coherent",
    "end_coherent",
    "transitions_ok",
    "omissions",
    "duplications",
    "adjacent_bleed",
    "attribution_ok",
)


class ArticleReviewError(ArtifactValidationError):
    """Raised when article evidence is malformed or fails deterministic checks."""


class StructuredOutputClient(Protocol):
    """Injected, no-policy boundary around one stateless structured model call."""

    def complete(self, request: dict[str, object]) -> Mapping[str, object]:
        """Return output, usage, and cost for exactly one request."""


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ArticleReviewError("article_evidence_not_canonical_json") from exc


def _require_mapping(value: object, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ArticleReviewError(reason)
    return value


def _require_exact_keys(value: object, keys: set[str], reason: str) -> Mapping[str, Any]:
    mapping = _require_mapping(value, reason)
    if set(mapping) != keys:
        raise ArticleReviewError(reason)
    return mapping


def _require_nonempty(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArticleReviewError(reason)
    return value


def _require_sha256(value: object, reason: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ArticleReviewError(reason)
    return value


def _require_int(value: object, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArticleReviewError(reason)
    return value


def _require_bool(value: object, reason: str) -> bool:
    if not isinstance(value, bool):
        raise ArticleReviewError(reason)
    return value


def _canonical_filename(value: object) -> str:
    suggested = _require_nonempty(value, "article_filename_required")
    stem = suggested.rsplit(".", 1)[0]
    ascii_stem = (
        unicodedata.normalize("NFKD", stem)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_stem).strip("-")
    if not slug:
        raise ArticleReviewError("article_filename_invalid")
    return f"{slug}.txt"


def _require_string_list(value: object, reason: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ArticleReviewError(reason)
    return tuple(value)


def _validate_verified_transcript(transcript: VerifiedIssueTranscript) -> str:
    if not isinstance(transcript, VerifiedIssueTranscript):
        raise ArticleReviewError("verified_issue_transcript_required")
    _require_sha256(transcript.ocr_identity, "ocr_lineage_invalid")
    if not isinstance(transcript.text, str) or not transcript.text:
        raise ArticleReviewError("issue_transcript_required")
    if not isinstance(transcript.pages, tuple) or not transcript.pages:
        raise ArticleReviewError("verified_issue_pages_required")

    expected_numbers = tuple(range(1, len(transcript.pages) + 1))
    if tuple(page.page_number for page in transcript.pages) != expected_numbers:
        raise ArticleReviewError("verified_issue_pages_not_contiguous")
    previous_end = 0
    for page in transcript.pages:
        _require_sha256(page.image_hash, "verified_page_image_hash_invalid")
        start = _require_int(page.transcript_start, "verified_page_span_invalid")
        end = _require_int(page.transcript_end, "verified_page_span_invalid")
        if start < previous_end or start > end or end > len(transcript.text):
            raise ArticleReviewError("verified_page_span_invalid")
        marker = f"=== PAGE {page.page_number} ===\n"
        marker_start = start - len(marker)
        if marker_start < 0 or transcript.text[marker_start:start] != marker:
            raise ArticleReviewError("verified_page_marker_mismatch")
        previous_end = end
    return _fingerprint(transcript.text)


def _page_payload(transcript: VerifiedIssueTranscript) -> list[dict[str, object]]:
    return [
        {
            "page_number": page.page_number,
            "image_hash": page.image_hash,
            "transcript_start": page.transcript_start,
            "transcript_end": page.transcript_end,
        }
        for page in transcript.pages
    ]


def _response_envelope(response: object, reason: str) -> tuple[Mapping[str, Any], Mapping[str, float | int], float]:
    envelope = _require_exact_keys(response, {"output", "usage", "cost_usd"}, reason)
    output = _require_mapping(envelope["output"], reason)
    usage_raw = _require_mapping(envelope["usage"], "article_usage_invalid")
    usage: dict[str, float | int] = {}
    for name, amount in usage_raw.items():
        if (
            not isinstance(name, str)
            or not name
            or isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(amount)
            or amount < 0
        ):
            raise ArticleReviewError("article_usage_invalid")
        usage[name] = amount
    cost = envelope["cost_usd"]
    if (
        isinstance(cost, bool)
        or not isinstance(cost, (int, float))
        or not math.isfinite(cost)
        or cost < 0
    ):
        raise ArticleReviewError("article_cost_invalid")
    return output, usage, float(cost)


def _segmentation_config() -> dict[str, object]:
    return {
        "model": ARTICLE_MODEL,
        "reasoning_effort": SEGMENTATION_REASONING,
        "instructions": SEGMENTATION_INSTRUCTIONS,
        "response_format": _segmentation_schema(),
    }


def _review_config() -> dict[str, object]:
    return {
        "model": ARTICLE_MODEL,
        "reasoning_effort": REVIEW_REASONING,
        "fresh_context": True,
        "instructions": REVIEW_INSTRUCTIONS,
        "response_format": _review_schema(),
    }


def _config_fingerprint(config: Mapping[str, object]) -> str:
    return _fingerprint(_canonical_json(config))


def _stage_identity(transcript: VerifiedIssueTranscript, transcript_hash: str) -> StageIdentity:
    durable_config = {
        "segmentation": _segmentation_config(),
        "review": _review_config(),
    }
    identity = StageIdentity(
        schema_version=1,
        input_hashes={
            "ocr_artifact": transcript.ocr_identity,
            "verified_issue_transcript": transcript_hash,
        },
        model=ARTICLE_MODEL,
        prompt_fingerprint=_fingerprint(_canonical_json(durable_config)),
        renderer_settings={
            "page_image_hashes": {
                str(page.page_number): page.image_hash for page in transcript.pages
            }
        },
    )
    identity.validate()
    return identity


def _segmentation_schema() -> dict[str, object]:
    article = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "article_id",
            "filename",
            "title",
            "author",
            "transcript_start",
            "transcript_end",
        ],
        "properties": {
            "article_id": {"type": "string", "minLength": 1},
            "filename": {"type": "string", "minLength": 1},
            "title": {"type": "string", "minLength": 1},
            "author": {"type": "string", "minLength": 1},
            "transcript_start": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Exact inclusive start offset; starts must be ascending and "
                    "article spans non-overlapping."
                ),
            },
            "transcript_end": {
                "type": "integer",
                "minimum": 1,
                "description": (
                    "Exact exclusive end offset; must not exceed the next article's "
                    "start."
                ),
            },
        },
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "magazine_article_segmentation",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["ocr_identity", "transcript_hash", "articles"],
                "properties": {
                    "ocr_identity": {"type": "string"},
                    "transcript_hash": {"type": "string"},
                    "articles": {"type": "array", "minItems": 1, "items": article},
                },
            },
        },
    }


def _review_schema() -> dict[str, object]:
    string_list = {"type": "array", "items": {"type": "string", "minLength": 1}}
    article = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "article_id",
            "start_coherent",
            "end_coherent",
            "transitions_ok",
            "omissions",
            "duplications",
            "adjacent_bleed",
            "attribution_ok",
            "failure_reasons",
        ],
        "properties": {
            "article_id": {"type": "string", "minLength": 1},
            "start_coherent": {"type": "boolean"},
            "end_coherent": {"type": "boolean"},
            "transitions_ok": {"type": "boolean"},
            "omissions": string_list,
            "duplications": string_list,
            "adjacent_bleed": string_list,
            "attribution_ok": {"type": "boolean"},
            "failure_reasons": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    field: {"type": "string", "minLength": 1}
                    for field in _SEMANTIC_FIELDS
                },
            },
        },
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "magazine_article_completeness_review",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "ocr_identity",
                    "transcript_hash",
                    "article_set_hash",
                    "issue_coverage_complete",
                    "missing_substantive_spans",
                    "missing_articles",
                    "articles",
                ],
                "properties": {
                    "ocr_identity": {"type": "string"},
                    "transcript_hash": {"type": "string"},
                    "article_set_hash": {"type": "string"},
                    "issue_coverage_complete": {"type": "boolean"},
                    "missing_substantive_spans": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["transcript_start", "transcript_end", "reason"],
                            "properties": {
                                "transcript_start": {"type": "integer", "minimum": 0},
                                "transcript_end": {"type": "integer", "minimum": 1},
                                "reason": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                    "missing_articles": string_list,
                    "articles": {"type": "array", "minItems": 1, "items": article},
                },
            },
        },
    }


def _source_pages_for_span(
    transcript: VerifiedIssueTranscript, start: int, end: int
) -> tuple[int, ...]:
    return tuple(
        page.page_number
        for page in transcript.pages
        if start < page.transcript_end and end > page.transcript_start
    )


def segment_articles(
    transcript: VerifiedIssueTranscript, client: StructuredOutputClient
) -> ArticleManifest:
    """Propose every article, then reject any mechanically unsafe segmentation."""

    transcript_hash = _validate_verified_transcript(transcript)
    request: dict[str, object] = {
        "stage": "article_segmentation",
        "model": ARTICLE_MODEL,
        "reasoning_effort": SEGMENTATION_REASONING,
        "instructions": SEGMENTATION_INSTRUCTIONS,
        "ocr_identity": transcript.ocr_identity,
        "transcript_hash": transcript_hash,
        "issue_transcript": transcript.text,
        "pages": _page_payload(transcript),
        "response_format": _segmentation_schema(),
    }
    output, usage, cost = _response_envelope(
        client.complete(request), "segmentation_response_invalid"
    )
    output = _require_exact_keys(
        output,
        {"ocr_identity", "transcript_hash", "articles"},
        "segmentation_output_invalid",
    )
    if output["ocr_identity"] != transcript.ocr_identity:
        raise ArticleReviewError("ocr_lineage_mismatch")
    if output["transcript_hash"] != transcript_hash:
        raise ArticleReviewError("transcript_lineage_mismatch")
    raw_articles = output["articles"]
    if not isinstance(raw_articles, list) or not raw_articles:
        raise ArticleReviewError("articles_required")

    seen_ids: set[str] = set()
    seen_filenames: set[str] = set()
    articles: list[ArticleRecord] = []
    previous_end = 0
    article_keys = {
        "article_id",
        "filename",
        "title",
        "author",
        "transcript_start",
        "transcript_end",
    }
    for raw in raw_articles:
        proposed = _require_exact_keys(raw, article_keys, "segmentation_article_invalid")
        article_id = _require_nonempty(proposed["article_id"], "article_id_required")
        filename = _canonical_filename(proposed["filename"])
        normalized_id = article_id.casefold()
        normalized_filename = filename.casefold()
        if normalized_id in seen_ids:
            raise ArticleReviewError("article_id_duplicate")
        if normalized_filename in seen_filenames:
            raise ArticleReviewError("article_filename_duplicate")

        start = _require_int(proposed["transcript_start"], "article_span_invalid")
        end = _require_int(proposed["transcript_end"], "article_span_invalid")
        if start < 0 or start >= end or end > len(transcript.text):
            raise ArticleReviewError("article_span_invalid")
        if start < previous_end:
            raise ArticleReviewError("article_spans_overlap")
        source_pages = _source_pages_for_span(transcript, start, end)
        if not source_pages:
            raise ArticleReviewError("article_source_pages_required")
        text = transcript.text[start:end]

        record = ArticleRecord(
            article_id=article_id,
            filename=filename,
            title=_require_nonempty(proposed["title"], "article_title_required"),
            author=_require_nonempty(proposed["author"], "article_author_required"),
            source_pages=source_pages,
            transcript_start=start,
            transcript_end=end,
            text=text,
            text_hash=_fingerprint(text),
            start_coherent=False,
            end_coherent=False,
            transitions_ok=False,
            omissions=(),
            duplications=(),
            adjacent_bleed=(),
            attribution_ok=False,
            verdict=False,
            failure_reasons={
                "start_coherent": "semantic_review_required",
                "end_coherent": "semantic_review_required",
                "transitions_ok": "semantic_review_required",
                "attribution_ok": "semantic_review_required",
            },
            reasons=(
                "semantic_review_required",
                "semantic_review_required",
                "semantic_review_required",
                "semantic_review_required",
            ),
        )
        record.validate(transcript.text)
        articles.append(record)
        seen_ids.add(normalized_id)
        seen_filenames.add(normalized_filename)
        previous_end = end

    manifest = ArticleManifest(
        identity=_stage_identity(transcript, transcript_hash),
        issue_hash=transcript_hash,
        ocr_artifact_hash=transcript.ocr_identity,
        transcript=transcript.text,
        articles=tuple(articles),
        segmentation_model=ARTICLE_MODEL,
        segmentation_prompt_fingerprint=_config_fingerprint(_segmentation_config()),
        segmentation_usage=usage,
        segmentation_cost_usd=cost,
        reviewer_model=ARTICLE_MODEL,
        reviewer_prompt_fingerprint=_config_fingerprint(_review_config()),
        reviewer_usage={},
        reviewer_cost_usd=0.0,
        issue_coverage_complete=False,
        status="quarantined",
        quarantine_reasons=("semantic_review_required",),
    )
    manifest.validate()
    return manifest


def _article_set_hash(articles: tuple[ArticleRecord, ...]) -> str:
    return _fingerprint(
        _canonical_json([_article_review_payload(article) for article in articles])
    )


def _article_review_payload(article: ArticleRecord) -> dict[str, object]:
    """Return source proposal evidence without placeholder review judgments."""

    return {
        "article_id": article.article_id,
        "filename": article.filename,
        "title": article.title,
        "author": article.author,
        "source_pages": list(article.source_pages),
        "transcript_start": article.transcript_start,
        "transcript_end": article.transcript_end,
        "text": article.text,
        "text_hash": article.text_hash,
    }


def _validate_manifest_lineage(
    transcript: VerifiedIssueTranscript,
    transcript_hash: str,
    manifest: ArticleManifest,
) -> None:
    try:
        manifest.validate()
    except ArtifactValidationError as exc:
        raise ArticleReviewError(str(exc)) from exc
    if manifest.ocr_artifact_hash != transcript.ocr_identity:
        raise ArticleReviewError("manifest_ocr_lineage_mismatch")
    if manifest.issue_hash != transcript_hash or manifest.transcript != transcript.text:
        raise ArticleReviewError("manifest_transcript_lineage_mismatch")
    if manifest.segmentation_model != ARTICLE_MODEL:
        raise ArticleReviewError("manifest_segmentation_model_mismatch")
    if manifest.segmentation_prompt_fingerprint != _config_fingerprint(_segmentation_config()):
        raise ArticleReviewError("manifest_segmentation_prompt_mismatch")
    if manifest.reviewer_model != ARTICLE_MODEL:
        raise ArticleReviewError("manifest_review_model_mismatch")
    if manifest.reviewer_prompt_fingerprint != _config_fingerprint(_review_config()):
        raise ArticleReviewError("manifest_review_prompt_mismatch")
    expected_identity = _stage_identity(transcript, transcript_hash)
    if manifest.identity != expected_identity:
        raise ArticleReviewError("manifest_identity_mismatch")


def review_articles_against_issue(
    transcript: VerifiedIssueTranscript,
    manifest: ArticleManifest,
    client: StructuredOutputClient,
) -> ArticleManifest:
    """Run a separate, fresh-context semantic review over the whole issue."""

    transcript_hash = _validate_verified_transcript(transcript)
    _validate_manifest_lineage(transcript, transcript_hash, manifest)
    article_set_hash = _article_set_hash(manifest.articles)
    request_articles = [_article_review_payload(article) for article in manifest.articles]
    request: dict[str, object] = {
        "stage": "article_completeness_review",
        "model": ARTICLE_MODEL,
        "reasoning_effort": REVIEW_REASONING,
        "fresh_context": True,
        "instructions": REVIEW_INSTRUCTIONS,
        "ocr_identity": transcript.ocr_identity,
        "transcript_hash": transcript_hash,
        "article_set_hash": article_set_hash,
        "issue_transcript": transcript.text,
        "pages": _page_payload(transcript),
        "articles": request_articles,
        "response_format": _review_schema(),
    }
    output, usage, cost = _response_envelope(
        client.complete(request), "article_review_response_invalid"
    )
    output = _require_exact_keys(
        output,
        {
            "ocr_identity",
            "transcript_hash",
            "article_set_hash",
            "issue_coverage_complete",
            "missing_substantive_spans",
            "missing_articles",
            "articles",
        },
        "article_review_output_invalid",
    )
    if output["ocr_identity"] != transcript.ocr_identity:
        raise ArticleReviewError("review_ocr_lineage_mismatch")
    if output["transcript_hash"] != transcript_hash:
        raise ArticleReviewError("review_transcript_lineage_mismatch")
    if output["article_set_hash"] != article_set_hash:
        raise ArticleReviewError("review_article_set_lineage_mismatch")
    issue_coverage_complete = _require_bool(
        output["issue_coverage_complete"], "article_issue_coverage_invalid"
    )
    missing_articles = _require_string_list(
        output["missing_articles"], "article_missing_articles_invalid"
    )
    raw_missing_spans = output["missing_substantive_spans"]
    if not isinstance(raw_missing_spans, list):
        raise ArticleReviewError("article_missing_spans_invalid")
    missing_spans: list[tuple[int, int, str]] = []
    for raw_span in raw_missing_spans:
        span = _require_exact_keys(
            raw_span,
            {"transcript_start", "transcript_end", "reason"},
            "article_missing_spans_invalid",
        )
        start = _require_int(span["transcript_start"], "article_missing_spans_invalid")
        end = _require_int(span["transcript_end"], "article_missing_spans_invalid")
        reason = _require_nonempty(span["reason"], "article_missing_spans_invalid")
        if start < 0 or end <= start or end > len(transcript.text):
            raise ArticleReviewError("article_missing_spans_invalid")
        missing_spans.append((start, end, reason))
    if issue_coverage_complete != (not missing_spans and not missing_articles):
        raise ArticleReviewError("article_issue_coverage_inconsistent")
    raw_reviews = output["articles"]
    if not isinstance(raw_reviews, list):
        raise ArticleReviewError("review_articles_invalid")
    expected_ids = [article.article_id for article in manifest.articles]
    review_ids = [
        raw.get("article_id") if isinstance(raw, Mapping) else None for raw in raw_reviews
    ]
    if review_ids != expected_ids:
        raise ArticleReviewError("review_article_reconciliation_failed")

    review_keys = {
        "article_id",
        "start_coherent",
        "end_coherent",
        "transitions_ok",
        "omissions",
        "duplications",
        "adjacent_bleed",
        "attribution_ok",
        "failure_reasons",
    }
    reviewed_articles: list[ArticleRecord] = []
    quarantine_reasons: list[str] = []
    for missing_article in missing_articles:
        quarantine_reasons.append(f"missing_article:{missing_article}")
    for start, end, reason in missing_spans:
        quarantine_reasons.append(
            f"missing_substantive_span:{start}:{end}:{reason}"
        )
    for article, raw in zip(manifest.articles, raw_reviews):
        review = _require_exact_keys(raw, review_keys, "article_review_invalid")
        start_coherent = _require_bool(review["start_coherent"], "article_review_invalid")
        end_coherent = _require_bool(review["end_coherent"], "article_review_invalid")
        transitions_ok = _require_bool(review["transitions_ok"], "article_review_invalid")
        omissions = _require_string_list(review["omissions"], "article_review_invalid")
        duplications = _require_string_list(review["duplications"], "article_review_invalid")
        adjacent_bleed = _require_string_list(review["adjacent_bleed"], "article_review_invalid")
        attribution_ok = _require_bool(review["attribution_ok"], "article_review_invalid")
        raw_failure_reasons = _require_mapping(
            review["failure_reasons"], "article_failure_reasons_invalid"
        )
        verdict = (
            start_coherent
            and end_coherent
            and transitions_ok
            and not omissions
            and not duplications
            and not adjacent_bleed
            and attribution_ok
        )
        failed_fields = {
            field
            for field, failed in (
                ("start_coherent", not start_coherent),
                ("end_coherent", not end_coherent),
                ("transitions_ok", not transitions_ok),
                ("omissions", bool(omissions)),
                ("duplications", bool(duplications)),
                ("adjacent_bleed", bool(adjacent_bleed)),
                ("attribution_ok", not attribution_ok),
            )
            if failed
        }
        if set(raw_failure_reasons) != failed_fields:
            raise ArticleReviewError("article_failure_reasons_invalid")
        failure_reasons = {
            field: _require_nonempty(
                raw_failure_reasons[field], "article_failure_reasons_invalid"
            )
            for field in _SEMANTIC_FIELDS
            if field in raw_failure_reasons
        }
        reasons = tuple(failure_reasons.values())
        reviewed = replace(
            article,
            start_coherent=start_coherent,
            end_coherent=end_coherent,
            transitions_ok=transitions_ok,
            omissions=omissions,
            duplications=duplications,
            adjacent_bleed=adjacent_bleed,
            attribution_ok=attribution_ok,
            verdict=verdict,
            failure_reasons=failure_reasons,
            reasons=reasons,
        )
        reviewed.validate(transcript.text)
        reviewed_articles.append(reviewed)
        if not verdict:
            for reason in reasons:
                if reason not in quarantine_reasons:
                    quarantine_reasons.append(reason)

    status = "quarantined" if quarantine_reasons else "passed"
    reviewed_manifest = replace(
        manifest,
        articles=tuple(reviewed_articles),
        reviewer_model=ARTICLE_MODEL,
        reviewer_prompt_fingerprint=_config_fingerprint(_review_config()),
        reviewer_usage=usage,
        reviewer_cost_usd=cost,
        issue_coverage_complete=issue_coverage_complete,
        missing_substantive_spans=tuple(missing_spans),
        missing_articles=missing_articles,
        status=status,
        quarantine_reasons=tuple(quarantine_reasons),
    )
    reviewed_manifest.validate()
    return reviewed_manifest
