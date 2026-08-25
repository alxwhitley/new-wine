"""Fail-closed proposition extraction preview and exact-evidence review."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Mapping, Protocol, Sequence

from propositions import (
    PropositionExtractionComputation,
    extract_propositions_with_evidence,
    prompt_fingerprint,
)

from .schemas import (
    ApprovedPropositionSet,
    ArticleManifest,
    ArtifactValidationError,
    PropositionEvidence,
    PropositionReview,
    StageIdentity,
)


REVIEW_MODEL = "openai/gpt-oss-120b"
REVIEW_REASONING = "medium"
REVIEW_INSTRUCTIONS = (
    "Review every extracted proposition against only the supplied verified article. "
    "For each proposition return one exact, nonempty evidence passage and its Python "
    "character offsets, then decide supported, missing_qualification, overstatement, "
    "and attribution_ok with specific reasons. Do not rewrite proposition content."
)
REVIEW_PROMPT_FINGERPRINT = hashlib.sha256(
    REVIEW_INSTRUCTIONS.encode("utf-8")
).hexdigest()
GROUNDING_FIELDS = (
    "found",
    "grounded",
    "stripped_fabricated",
    "stripped_uncertain",
    "kept_arbitration",
)
PRICING_MODEL = "openai/gpt-oss-120b"
PRICING_INPUT_USD_PER_MILLION = Decimal("0.15")
PRICING_OUTPUT_USD_PER_MILLION = Decimal("0.60")
PRICING_SOURCE_URL = "https://console.groq.com/docs/model/openai/gpt-oss-120b"
PRICING_OBSERVED_DATE = "2026-08-25"


class PropositionReviewError(RuntimeError):
    """A technical or structural failure prevented a support verdict."""


class StructuredReviewer(Protocol):
    def complete(self, request: dict[str, object]) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class _ExtractionEvidence:
    output: tuple[dict[str, object], ...]
    model: str
    usage: Mapping[str, float | int]
    cost_usd: float
    cost_basis: Mapping[str, str]
    grounding_totals: Mapping[str, int]


_approved_sets: dict[str, ApprovedPropositionSet] = {}


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
        raise PropositionReviewError("artifact_not_canonical_json") from exc


def _artifact_hash(value: ArticleManifest | PropositionReview) -> str:
    """Return the exact hash canonical ``write_artifact`` will persist."""
    value.validate()
    base = {
        "artifact_type": type(value).__name__,
        "identity": value.identity.to_dict(),
        "payload": value.to_dict(),
    }
    envelope = dict(base)
    envelope["payload_sha256"] = hashlib.sha256(_canonical_json(base)).hexdigest()
    return hashlib.sha256(_canonical_json(envelope)).hexdigest()


def _review_schema() -> dict[str, object]:
    proposition = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "proposition_index",
            "content",
            "evidence_text",
            "evidence_start",
            "evidence_end",
            "supported",
            "missing_qualification",
            "overstatement",
            "attribution_ok",
            "reviewer_reasons",
        ],
        "properties": {
            "proposition_index": {"type": "integer", "minimum": 1},
            "content": {"type": "string", "minLength": 1},
            "evidence_text": {"type": "string", "minLength": 1},
            "evidence_start": {"type": "integer", "minimum": 0},
            "evidence_end": {"type": "integer", "minimum": 1},
            "supported": {"type": "boolean"},
            "missing_qualification": {"type": "boolean"},
            "overstatement": {"type": "boolean"},
            "attribution_ok": {"type": "boolean"},
            "reviewer_reasons": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
        },
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "magazine_proposition_support_review_v1",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["article_id", "article_hash", "propositions"],
                "properties": {
                    "article_id": {"type": "string", "minLength": 1},
                    "article_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "propositions": {"type": "array", "minItems": 1, "items": proposition},
                },
            },
        },
    }


def _require_mapping(value: object, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PropositionReviewError(reason)
    return value


def _require_exact_keys(
    value: object, keys: set[str], reason: str
) -> Mapping[str, Any]:
    mapping = _require_mapping(value, reason)
    if set(mapping) != keys:
        raise PropositionReviewError(reason)
    return mapping


def _usage(value: object, reason: str) -> dict[str, float | int]:
    mapping = _require_mapping(value, reason)
    result: dict[str, float | int] = {}
    for key, amount in mapping.items():
        if (
            not isinstance(key, str)
            or not key
            or isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(amount)
        ):
            raise PropositionReviewError(reason)
        result[key] = amount
    return result


def _cost(value: object, reason: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise PropositionReviewError(reason)
    return float(value)


def _grounding_totals(computation: PropositionExtractionComputation) -> dict[str, int]:
    grounding = computation.grounding
    values = {
        "found": grounding.n_found,
        "grounded": grounding.n_grounded,
        "stripped_fabricated": grounding.n_stripped_fabricated,
        "stripped_uncertain": grounding.n_stripped_uncertain,
        "kept_arbitration": grounding.n_kept_arbitration,
    }
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in values.values()
    ):
        raise PropositionReviewError("proposition_grounding_totals_invalid")
    if values["found"] != sum(values[name] for name in GROUNDING_FIELDS[1:]):
        raise PropositionReviewError("proposition_grounding_totals_invalid")
    return values


def _normalize_extraction(value: object) -> _ExtractionEvidence:
    if not isinstance(value, PropositionExtractionComputation):
        raise PropositionReviewError("proposition_extraction_result_invalid")
    computation = value
    output = computation.output
    if computation.grounding.propositions != output:
        raise PropositionReviewError("proposition_grounding_output_mismatch")
    model = computation.model
    usage = _usage(computation.usage, "proposition_extraction_usage_invalid")
    grounding_totals = _grounding_totals(computation)

    if not isinstance(output, list):
        raise PropositionReviewError("proposition_extraction_schema_invalid")
    normalized: list[dict[str, object]] = []
    for item in output:
        raw = _require_exact_keys(
            item,
            {"proposition_index", "content"},
            "proposition_extraction_schema_invalid",
        )
        index = raw["proposition_index"]
        content = raw["content"]
        if isinstance(index, bool) or not isinstance(index, int) or index < 1:
            raise PropositionReviewError("proposition_index_invalid")
        if not isinstance(content, str) or not content.strip():
            raise PropositionReviewError("proposition_content_required")
        normalized.append({"proposition_index": index, "content": content})
    if [item["proposition_index"] for item in normalized] != list(
        range(1, len(normalized) + 1)
    ):
        raise PropositionReviewError("proposition_indices_not_contiguous")
    if not isinstance(model, str) or not model.strip():
        raise PropositionReviewError("proposition_model_required")
    if computation.cost_usd is None:
        if model != PRICING_MODEL:
            raise PropositionReviewError("proposition_pricing_model_mismatch")
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        for amount in (input_tokens, output_tokens):
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise PropositionReviewError("proposition_pricing_usage_invalid")
        calculated_cost = (
            Decimal(input_tokens) * PRICING_INPUT_USD_PER_MILLION
            + Decimal(output_tokens) * PRICING_OUTPUT_USD_PER_MILLION
        ) / Decimal(1_000_000)
        cost_usd = float(calculated_cost)
        cost_basis = {
            "type": "pricing_snapshot",
            "model": PRICING_MODEL,
            "currency": "USD",
            "input_usd_per_million_tokens": str(PRICING_INPUT_USD_PER_MILLION),
            "output_usd_per_million_tokens": str(PRICING_OUTPUT_USD_PER_MILLION),
            "source_url": PRICING_SOURCE_URL,
            "observed_date": PRICING_OBSERVED_DATE,
        }
    else:
        cost_usd = _cost(
            computation.cost_usd, "proposition_extraction_cost_invalid"
        )
        cost_basis = {
            "type": "provider_reported",
            "model": model,
            "currency": "USD",
        }
    return _ExtractionEvidence(
        output=tuple(normalized),
        model=model,
        usage=usage,
        cost_usd=cost_usd,
        cost_basis=cost_basis,
        grounding_totals=grounding_totals,
    )


def _identity_renderer_settings(
    *, extractor_model: str, extraction_cost_basis: Mapping[str, str]
) -> dict[str, object]:
    """Return the one canonical durable renderer identity for this stage."""
    return {
        "fresh_context": True,
        "reasoning_effort": REVIEW_REASONING,
        "extractor_model": extractor_model,
        "extractor_prompt_version": "v3.1",
        "extractor_prompt_fingerprint": prompt_fingerprint("v3.1"),
        "extraction_cost_basis": dict(extraction_cost_basis),
        "response_format": _review_schema(),
    }


def _identity(
    *,
    article_hash: str,
    article_artifact_hash: str,
    extractor_model: str,
    extraction_cost_basis: Mapping[str, str],
) -> StageIdentity:
    return StageIdentity(
        schema_version=1,
        input_hashes={
            "article_artifact": article_artifact_hash,
            "article_text": article_hash,
        },
        model=REVIEW_MODEL,
        prompt_fingerprint=REVIEW_PROMPT_FINGERPRINT,
        renderer_settings=_identity_renderer_settings(
            extractor_model=extractor_model,
            extraction_cost_basis=extraction_cost_basis,
        ),
    )


def _stage_identity(
    *,
    article_hash: str,
    article_artifact_hash: str,
    extraction: _ExtractionEvidence,
) -> StageIdentity:
    return _identity(
        article_hash=article_hash,
        article_artifact_hash=article_artifact_hash,
        extractor_model=extraction.model,
        extraction_cost_basis=extraction.cost_basis,
    )


def expected_proposition_review_identity(
    review: PropositionReview,
    *,
    article_hash: str,
    article_artifact_hash: str,
    extractor_model: str,
) -> StageIdentity:
    """Recompute current Task 5 identity from durable, validated inputs."""
    identity = _identity(
        article_hash=article_hash,
        article_artifact_hash=article_artifact_hash,
        extractor_model=extractor_model,
        extraction_cost_basis=review.extraction_cost_basis,
    )
    identity.validate()
    return identity


def _base_review(
    *,
    article: Any,
    article_artifact_hash: str,
    extraction: _ExtractionEvidence,
    propositions: Sequence[PropositionEvidence],
    status: str,
    reasons: Sequence[str],
    reviewer_usage: Mapping[str, float | int] | None = None,
    reviewer_cost_usd: float = 0.0,
) -> PropositionReview:
    return PropositionReview(
        identity=_stage_identity(
            article_hash=article.article_hash,
            article_artifact_hash=article_artifact_hash,
            extraction=extraction,
        ),
        article_id=article.article_id,
        article_hash=article.article_hash,
        article_artifact_hash=article_artifact_hash,
        model=extraction.model,
        prompt_version="v3.1",
        prompt_fingerprint=prompt_fingerprint("v3.1"),
        extraction_usage=dict(extraction.usage),
        extraction_cost_usd=extraction.cost_usd,
        extraction_cost_basis=dict(extraction.cost_basis),
        reviewer_model=REVIEW_MODEL,
        reviewer_prompt_fingerprint=REVIEW_PROMPT_FINGERPRINT,
        reviewer_usage=dict(reviewer_usage or {}),
        reviewer_cost_usd=reviewer_cost_usd,
        article_text=article.text,
        propositions=tuple(propositions),
        grounding_totals=dict(extraction.grounding_totals),
        status=status,
        reasons=tuple(reasons),
    )


def _invoke_reviewer(
    reviewer: StructuredReviewer | Callable[..., Mapping[str, object]],
    request: dict[str, object],
) -> Mapping[str, object]:
    complete = getattr(reviewer, "complete", None)
    response = complete(request) if callable(complete) else reviewer(**request)
    return _require_exact_keys(
        response,
        {"output", "usage", "cost_usd"},
        "proposition_review_response_invalid",
    )


def _semantic_request(article: Any, extraction: _ExtractionEvidence) -> dict[str, object]:
    return {
        "model": REVIEW_MODEL,
        "reasoning_effort": REVIEW_REASONING,
        "instructions": REVIEW_INSTRUCTIONS,
        "fresh_context": True,
        "article": {
            "article_id": article.article_id,
            "title": article.title,
            "author": article.author,
            "text": article.text,
            "text_hash": article.article_hash,
        },
        "propositions": [dict(item) for item in extraction.output],
        "response_format": _review_schema(),
    }


def _exact_or_quarantined_evidence(
    raw: Mapping[str, Any], article_text: str
) -> tuple[PropositionEvidence, bool]:
    evidence_text = raw["evidence_text"]
    start = raw["evidence_start"]
    end = raw["evidence_end"]
    if not isinstance(evidence_text, str) or not evidence_text:
        raise PropositionReviewError("evidence_text_required")
    if isinstance(start, bool) or not isinstance(start, int):
        raise PropositionReviewError("evidence_offset_invalid")
    if isinstance(end, bool) or not isinstance(end, int):
        raise PropositionReviewError("evidence_offset_invalid")
    offset_mismatch = (
        start < 0
        or end <= start
        or end > len(article_text)
        or article_text[start:end] != evidence_text
    )
    if offset_mismatch:
        unique_start = article_text.find(evidence_text)
        if unique_start < 0 or article_text.find(evidence_text, unique_start + 1) >= 0:
            raise PropositionReviewError("evidence_offset_mismatch")
        start = unique_start
        end = unique_start + len(evidence_text)

    flags = (
        raw["supported"],
        raw["missing_qualification"],
        raw["overstatement"],
        raw["attribution_ok"],
    )
    if any(not isinstance(flag, bool) for flag in flags):
        raise PropositionReviewError("proposition_review_flags_invalid")
    reasons = raw["reviewer_reasons"]
    if (
        not isinstance(reasons, list)
        or not reasons
        or any(not isinstance(reason, str) or not reason.strip() for reason in reasons)
    ):
        raise PropositionReviewError("proposition_reviewer_reasons_invalid")
    evidence = PropositionEvidence(
        proposition_index=raw["proposition_index"],
        content=raw["content"],
        evidence_text=evidence_text,
        evidence_start=start,
        evidence_end=end,
        evidence_offset_exact=not offset_mismatch,
        supported=raw["supported"],
        missing_qualification=raw["missing_qualification"],
        overstatement=raw["overstatement"],
        attribution_ok=raw["attribution_ok"],
        reviewer_reasons=tuple(reasons),
    )
    evidence.validate_shape(article_text)
    return evidence, offset_mismatch


def review_issue_propositions(
    article_manifest: ArticleManifest,
    reviewer: StructuredReviewer | Callable[..., Mapping[str, object]],
    *,
    extractor: Callable[..., object] | None = None,
    article_artifact_hash: str | None = None,
) -> PropositionReview:
    """Extract and review one verified article without regenerating its text.

    Task 6 invokes this per article and aggregates every returned review into the
    issue-wide all-or-nothing decision. A one-article manifest makes that unit
    explicit and prevents an ambiguous singular return from dropping articles.
    """
    article_manifest.validate()
    if article_manifest.status != "passed":
        raise PropositionReviewError("article_manifest_not_passed")
    if len(article_manifest.articles) != 1:
        raise PropositionReviewError("article_manifest_requires_one_article")
    article = article_manifest.articles[0]
    _approved_sets.pop(article.article_id, None)
    if not article.text.strip():
        raise PropositionReviewError("article_text_empty")

    predecessor_hash = article_artifact_hash or _artifact_hash(article_manifest)
    extraction_adapter = extractor or extract_propositions_with_evidence
    extraction = _normalize_extraction(
        extraction_adapter(
            text=article.text,
            doc_id=article.article_id,
            speaker=article.author,
            prompt_version="v3.1",
            grounding_review_sink=None,
        )
    )
    if not extraction.output:
        result = _base_review(
            article=article,
            article_artifact_hash=predecessor_hash,
            extraction=extraction,
            propositions=(),
            status="quarantined",
            reasons=(f"article:{article.article_id}:zero_propositions",),
        )
        result.validate()
        return result

    response = _invoke_reviewer(reviewer, _semantic_request(article, extraction))
    output = _require_exact_keys(
        response["output"],
        {"article_id", "article_hash", "propositions"},
        "proposition_review_output_invalid",
    )
    if (
        output["article_id"] != article.article_id
        or output["article_hash"] != article.article_hash
    ):
        raise PropositionReviewError("proposition_review_lineage_mismatch")
    reviewed = output["propositions"]
    if not isinstance(reviewed, list) or len(reviewed) != len(extraction.output):
        raise PropositionReviewError("review_proposition_reconciliation_failed")

    evidence_items: list[PropositionEvidence] = []
    quarantine_reasons: list[str] = []
    expected_keys = {
        "proposition_index",
        "content",
        "evidence_text",
        "evidence_start",
        "evidence_end",
        "supported",
        "missing_qualification",
        "overstatement",
        "attribution_ok",
        "reviewer_reasons",
    }
    for expected, item in zip(extraction.output, reviewed):
        raw = _require_exact_keys(
            item, expected_keys, "proposition_review_schema_invalid"
        )
        if (
            raw["proposition_index"] != expected["proposition_index"]
            or raw["content"] != expected["content"]
        ):
            raise PropositionReviewError("review_proposition_mismatch")
        evidence, offset_mismatch = _exact_or_quarantined_evidence(raw, article.text)
        evidence_items.append(evidence)
        prefix = f"article:{article.article_id}:proposition:{evidence.proposition_index}"
        if offset_mismatch:
            quarantine_reasons.append("evidence_offset_mismatch")
        if not evidence.supported:
            quarantine_reasons.append(f"{prefix}:unsupported")
        if evidence.missing_qualification:
            quarantine_reasons.append(f"{prefix}:missing_qualification")
        if evidence.overstatement:
            quarantine_reasons.append(f"{prefix}:overstatement")
        if not evidence.attribution_ok:
            quarantine_reasons.append(f"{prefix}:attribution_mismatch")

    status = "quarantined" if quarantine_reasons else "passed"
    result = _base_review(
        article=article,
        article_artifact_hash=predecessor_hash,
        extraction=extraction,
        propositions=evidence_items,
        status=status,
        reasons=quarantine_reasons,
        reviewer_usage=_usage(
            response["usage"], "proposition_reviewer_usage_invalid"
        ),
        reviewer_cost_usd=_cost(
            response["cost_usd"], "proposition_reviewer_cost_invalid"
        ),
    )
    result.validate()
    if result.status == "passed":
        review_artifact_hash = _artifact_hash(result)
        _approved_sets[article.article_id] = ApprovedPropositionSet.from_review(
            result, review_artifact_hash
        )
    return result


def approved_propositions_for(article_id: str) -> list[dict]:
    """Return only exact content from the latest passing bound review."""
    approved = _approved_sets.get(article_id)
    if approved is None:
        raise ArtifactValidationError("proposition_not_supported")
    return approved.as_storage_list()
