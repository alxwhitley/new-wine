#!/usr/bin/env python3
"""Review exactly one named New Wine issue into local evidence artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import fitz

from magazine_review import articles as article_review_module
from magazine_review.articles import (
    ARTICLE_MODEL,
    StructuredOutputClient,
    review_articles_against_issue,
    segment_articles,
)
from magazine_review.artifacts import load_valid_artifact, write_artifact
from magazine_review.benchmark import BenchmarkCandidate, OCRProvider
from magazine_review.ocr import (
    OCRReviewConfig,
    PageReviewer,
    VerifiedIssueTranscript,
    review_issue_ocr,
)
from magazine_review.proposition_review import (
    REVIEW_MODEL as PROPOSITION_REVIEW_MODEL,
    REVIEW_PROMPT_FINGERPRINT as PROPOSITION_REVIEW_PROMPT_FINGERPRINT,
    StructuredReviewer,
    expected_proposition_review_identity,
    review_issue_propositions,
)
from magazine_review.schemas import (
    ApprovedPropositionSet,
    ArticleManifest,
    ArtifactValidationError,
    IssueDecision,
    OCRManifest,
    PropositionReview,
    StageIdentity,
    validated_usage,
)
from propositions import (
    EXTRACTION_MODEL,
    prompt_fingerprint as proposition_prompt_fingerprint,
)


ARTICLE_MANIFEST_NAME = "article_manifest.json"
ISSUE_DECISION_NAME = "issue_decision.json"
PROPOSITION_PREFIX = "proposition_review_"
PROVIDER_FACTORY_ENV = "MAGAZINE_REVIEW_PROVIDER_ADAPTER_FACTORY"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ZERO_HASH = "0" * 64


class ReviewConfigurationError(ValueError):
    """The named issue, accepted decision, or adapter setup is unsafe."""


# Backward-compatible name retained for callers of the initial Task 6 commit.
IssueReviewConfigurationError = ReviewConfigurationError


@dataclass(frozen=True)
class AcceptedBenchmarkDecision:
    """A human-accepted Task 1 winner bound to exactly one issue PDF."""

    name: str
    issue_filename: str
    issue_pdf_sha256: str
    accepted_candidate: BenchmarkCandidate
    benchmark_report_sha256: str
    decision_sha256: str

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise IssueReviewConfigurationError("benchmark_decision_name_required")
        if (
            not isinstance(self.issue_filename, str)
            or Path(self.issue_filename).name != self.issue_filename
            or not self.issue_filename.lower().endswith(".pdf")
        ):
            raise IssueReviewConfigurationError("benchmark_decision_issue_invalid")
        for value in (
            self.issue_pdf_sha256,
            self.benchmark_report_sha256,
            self.decision_sha256,
        ):
            if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
                raise IssueReviewConfigurationError("benchmark_decision_hash_invalid")
        candidate = self.accepted_candidate
        if (
            not isinstance(candidate, BenchmarkCandidate)
            or not isinstance(candidate.provider, str)
            or not candidate.provider.strip()
            or not isinstance(candidate.model, str)
            or not candidate.model.strip()
        ):
            raise IssueReviewConfigurationError("benchmark_decision_candidate_invalid")


@dataclass(frozen=True)
class ProviderAdapters:
    """Explicit external boundaries returned by a configured CLI factory."""

    initial_ocr_provider: OCRProvider
    page_reviewer: PageReviewer
    repair_ocr_provider: OCRProvider
    article_client: StructuredOutputClient
    proposition_reviewer: StructuredReviewer | Callable[..., Mapping[str, object]]
    proposition_extractor: Callable[..., object] | None = None
    proposition_extractor_model: str = EXTRACTION_MODEL


@dataclass(frozen=True)
class ReviewIssueConfig:
    """Complete injected configuration for a single no-write review run."""

    benchmark_decision: AcceptedBenchmarkDecision
    ocr: OCRReviewConfig
    article_client: StructuredOutputClient
    proposition_reviewer: StructuredReviewer | Callable[..., Mapping[str, object]]
    proposition_extractor: Callable[..., object] | None = None
    proposition_extractor_model: str = EXTRACTION_MODEL

    def validate(self) -> None:
        if not isinstance(self.benchmark_decision, AcceptedBenchmarkDecision):
            raise ReviewConfigurationError("benchmark_decision_invalid")
        try:
            self.benchmark_decision.validate()
        except ReviewConfigurationError:
            raise
        except Exception as exc:
            raise ReviewConfigurationError("benchmark_decision_invalid") from exc
        if not isinstance(self.ocr, OCRReviewConfig):
            raise ReviewConfigurationError("ocr_review_config_invalid")
        try:
            self.ocr.validate()
        except ReviewConfigurationError:
            raise
        except Exception as exc:
            reason = str(exc).strip() or "ocr_review_config_invalid"
            raise ReviewConfigurationError(reason) from exc
        if self.ocr.accepted_candidate != self.benchmark_decision.accepted_candidate:
            raise ReviewConfigurationError("accepted_candidate_mismatch")
        if self.ocr.benchmark_decision_hash != self.benchmark_decision.decision_sha256:
            raise ReviewConfigurationError("benchmark_decision_hash_mismatch")
        if not callable(getattr(self.article_client, "complete", None)):
            raise ReviewConfigurationError("article_client_invalid")
        if not (
            callable(self.proposition_reviewer)
            or callable(getattr(self.proposition_reviewer, "complete", None))
        ):
            raise ReviewConfigurationError("proposition_reviewer_invalid")
        if self.proposition_extractor is not None and not callable(
            self.proposition_extractor
        ):
            raise ReviewConfigurationError("proposition_extractor_invalid")
        if (
            not isinstance(self.proposition_extractor_model, str)
            or not self.proposition_extractor_model.strip()
        ):
            raise ReviewConfigurationError("proposition_extractor_model_invalid")


def _validate_programmatic_config(config: object) -> ReviewIssueConfig:
    if not isinstance(config, ReviewIssueConfig):
        raise ReviewConfigurationError("review_issue_config_invalid")
    try:
        config.validate()
    except ReviewConfigurationError:
        raise
    except Exception as exc:
        raise ReviewConfigurationError("review_issue_config_invalid") from exc
    return config


def _path_precondition(value: object, reason: str) -> Path:
    try:
        return Path(value)
    except (TypeError, ValueError) as exc:
        raise ReviewConfigurationError(reason) from exc


def article_config_fingerprint(stage: str) -> str:
    """Expose the durable Task 4 fingerprint for orchestration tests/adapters."""

    if stage == "segmentation":
        return article_review_module._config_fingerprint(
            article_review_module._segmentation_config()
        )
    if stage == "review":
        return article_review_module._config_fingerprint(
            article_review_module._review_config()
        )
    raise ValueError("article_stage_invalid")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
        raise IssueReviewConfigurationError("review_config_not_canonical") from exc


def load_accepted_benchmark_decision(path: Path) -> AcceptedBenchmarkDecision:
    """Load one exact, human-accepted benchmark decision document."""

    decision_path = Path(path)
    try:
        raw_bytes = decision_path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
    except FileNotFoundError as exc:
        raise IssueReviewConfigurationError("benchmark_decision_not_found") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IssueReviewConfigurationError("benchmark_decision_invalid_json") from exc
    expected_keys = {
        "schema_version",
        "decision_name",
        "state",
        "issue",
        "accepted_candidate",
        "benchmark_report_sha256",
    }
    if not isinstance(raw, Mapping) or set(raw) != expected_keys:
        raise IssueReviewConfigurationError("benchmark_decision_invalid")
    issue = raw["issue"]
    candidate = raw["accepted_candidate"]
    if (
        raw["schema_version"] != 1
        or raw["state"] != "accepted"
        or not isinstance(issue, Mapping)
        or set(issue) != {"filename", "pdf_sha256"}
        or not isinstance(candidate, Mapping)
        or set(candidate) != {"provider", "model"}
    ):
        raise IssueReviewConfigurationError("benchmark_decision_invalid")
    decision = AcceptedBenchmarkDecision(
        name=raw["decision_name"],
        issue_filename=issue["filename"],
        issue_pdf_sha256=issue["pdf_sha256"],
        accepted_candidate=BenchmarkCandidate(
            provider=candidate["provider"], model=candidate["model"]
        ),
        benchmark_report_sha256=raw["benchmark_report_sha256"],
        decision_sha256=_sha256_bytes(raw_bytes),
    )
    decision.validate()
    return decision


def validate_named_issue(
    pdf_path: Path, decision: AcceptedBenchmarkDecision
) -> str:
    """Require both the exact accepted filename and the exact accepted bytes."""

    decision.validate()
    issue_path = Path(pdf_path)
    if issue_path.name != decision.issue_filename:
        raise IssueReviewConfigurationError("issue_filename_mismatch")
    try:
        pdf_bytes = issue_path.read_bytes()
    except FileNotFoundError as exc:
        raise IssueReviewConfigurationError("issue_pdf_not_found") from exc
    pdf_hash = _sha256_bytes(pdf_bytes)
    if pdf_hash != decision.issue_pdf_sha256:
        raise IssueReviewConfigurationError("issue_pdf_sha256_mismatch")
    return pdf_hash


def _config_from_adapters(
    decision: AcceptedBenchmarkDecision, adapters: ProviderAdapters
) -> ReviewIssueConfig:
    if not isinstance(adapters, ProviderAdapters):
        raise IssueReviewConfigurationError("provider_adapters_invalid")
    return ReviewIssueConfig(
        benchmark_decision=decision,
        ocr=OCRReviewConfig(
            accepted_candidate=decision.accepted_candidate,
            benchmark_decision_hash=decision.decision_sha256,
            initial_provider=adapters.initial_ocr_provider,
            reviewer=adapters.page_reviewer,
            repair_provider=adapters.repair_ocr_provider,
        ),
        article_client=adapters.article_client,
        proposition_reviewer=adapters.proposition_reviewer,
        proposition_extractor=adapters.proposition_extractor,
        proposition_extractor_model=adapters.proposition_extractor_model,
    )


def _decision_identity(pdf_hash: str, config: ReviewIssueConfig) -> StageIdentity:
    ocr = config.ocr
    repair_candidate = getattr(ocr.repair_provider, "candidate", None)
    durable = {
        "accepted_candidate": {
            "provider": config.benchmark_decision.accepted_candidate.provider,
            "model": config.benchmark_decision.accepted_candidate.model,
        },
        "ocr_reviewer_model": getattr(ocr.reviewer, "model", ""),
        "repair_candidate": {
            "provider": getattr(repair_candidate, "provider", ""),
            "model": getattr(repair_candidate, "model", ""),
        },
        "article_model": ARTICLE_MODEL,
        "article_segmentation_fingerprint": article_config_fingerprint("segmentation"),
        "article_review_fingerprint": article_config_fingerprint("review"),
        "proposition_extractor_model": config.proposition_extractor_model,
        "proposition_review_model": PROPOSITION_REVIEW_MODEL,
        "proposition_review_fingerprint": PROPOSITION_REVIEW_PROMPT_FINGERPRINT,
    }
    identity = StageIdentity(
        schema_version=1,
        input_hashes={
            "issue.pdf": pdf_hash,
            "accepted_benchmark_decision": config.benchmark_decision.decision_sha256,
            "reviewed_benchmark_report": config.benchmark_decision.benchmark_report_sha256,
        },
        model="magazine-issue-review-orchestrator-v1",
        prompt_fingerprint=_sha256_bytes(_canonical_json(durable)),
        renderer_settings=durable,
    )
    identity.validate()
    return identity


def _artifact_hash(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _sum_numeric(values: Sequence[float | int], reason: str) -> float | int:
    normalized = validated_usage(
        {str(index): value for index, value in enumerate(values)}, reason
    )
    total = math.fsum(normalized.values())
    if not math.isfinite(total):
        raise ArtifactValidationError(reason)
    if all(isinstance(value, int) for value in values):
        return int(total)
    return total


def _pdf_page_count(pdf_path: Path) -> int:
    try:
        with fitz.open(str(pdf_path)) as document:
            count = document.page_count
    except Exception as exc:
        raise ArtifactValidationError("issue_pdf_invalid") from exc
    if count < 1:
        raise ArtifactValidationError("issue_pdf_has_no_pages")
    return count


def _load_matching_article(
    path: Path, transcript: VerifiedIssueTranscript
) -> ArticleManifest | None:
    transcript_hash = _sha256_bytes(transcript.text.encode("utf-8"))
    expected = article_review_module._stage_identity(transcript, transcript_hash)
    try:
        value = load_valid_artifact(path, expected)
    except ArtifactValidationError as exc:
        if str(exc) in {"artifact_not_found", "artifact_identity_mismatch"}:
            return None
        raise
    if not isinstance(value, ArticleManifest):
        raise ArtifactValidationError("article_resume_artifact_type_invalid")
    article_review_module._validate_manifest_lineage(transcript, transcript_hash, value)
    return value


def _proposition_path(artifact_dir: Path, article_id: str) -> Path:
    stable_name = hashlib.sha256(article_id.encode("utf-8")).hexdigest()[:24]
    return Path(artifact_dir) / f"{PROPOSITION_PREFIX}{stable_name}.json"


def _read_recorded_identity(path: Path) -> StageIdentity:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactValidationError("artifact_not_found") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError("artifact_invalid_json") from exc
    if not isinstance(raw, Mapping) or not isinstance(raw.get("identity"), Mapping):
        raise ArtifactValidationError("artifact_envelope_invalid")
    return StageIdentity.from_dict(raw["identity"])


# Backward-compatible Task 6 name; the implementation lives with Task 5's
# canonical stage definition so resume and ingestion cannot drift apart.
expected_proposition_identity = expected_proposition_review_identity


def _load_matching_proposition(
    path: Path,
    *,
    article: Any,
    article_artifact_hash: str,
    extractor_model: str,
) -> PropositionReview | None:
    try:
        recorded_identity = _read_recorded_identity(path)
    except ArtifactValidationError as exc:
        if str(exc) == "artifact_not_found":
            return None
        raise
    value = load_valid_artifact(path, recorded_identity)
    if not isinstance(value, PropositionReview):
        raise ArtifactValidationError("proposition_resume_artifact_type_invalid")
    expected = expected_proposition_identity(
        value,
        article_hash=article.article_hash,
        article_artifact_hash=article_artifact_hash,
        extractor_model=extractor_model,
    )
    if value.identity != expected:
        return None
    if (
        value.article_id != article.article_id
        or value.article_hash != article.article_hash
        or value.article_artifact_hash != article_artifact_hash
        or value.model != extractor_model
    ):
        return None
    value.validate(article.text)
    return value


def _base_usage(
    ocr: OCRManifest | None,
    articles: ArticleManifest | None,
    reviews: Sequence[PropositionReview],
    accounting: Mapping[str, int],
    partial_usage: Mapping[str, float | int],
) -> dict[str, float | int]:
    usage = {
        "ocr": _sum_numeric(list(ocr.usage.values()), "ocr_usage_total_invalid")
        if ocr is not None
        else 0,
        "article_segmentation": _sum_numeric(
            list(articles.segmentation_usage.values()),
            "article_segmentation_usage_total_invalid",
        )
        if articles is not None
        else 0,
        "article_review": _sum_numeric(
            list(articles.reviewer_usage.values()), "article_review_usage_total_invalid"
        )
        if articles is not None
        else 0,
        "proposition_extraction": _sum_numeric(
            [amount for review in reviews for amount in review.extraction_usage.values()],
            "proposition_extraction_usage_total_invalid",
        ),
        "proposition_review": _sum_numeric(
            [amount for review in reviews for amount in review.reviewer_usage.values()],
            "proposition_review_usage_total_invalid",
        ),
        **dict(accounting),
    }
    for stage, amount in partial_usage.items():
        if stage not in usage:
            raise ArtifactValidationError("partial_usage_stage_invalid")
        usage[stage] = _sum_numeric(
            [usage[stage], amount], f"{stage}_partial_usage_invalid"
        )
    return usage


def _decision(
    *,
    identity: StageIdentity,
    issue_hash: str,
    state: str,
    ocr: OCRManifest | None,
    ocr_artifact_hash: str | None,
    articles: ArticleManifest | None,
    article_artifact_hash: str | None,
    reviews: Sequence[PropositionReview],
    proposition_hashes: Mapping[str, str],
    gate_results: Mapping[str, bool],
    accounting: Mapping[str, int],
    partial_usage: Mapping[str, float | int],
    partial_costs: Mapping[str, float | int],
    reasons: Sequence[str],
) -> IssueDecision:
    reviews_tuple = tuple(reviews)
    article_hashes = {
        article.article_id: article.article_hash
        for article in (articles.articles if articles is not None else ())
    }
    totals = {
        "pages": ocr.page_count if ocr is not None else 0,
        "articles": len(articles.articles) if articles is not None else 0,
        "propositions": sum(len(review.propositions) for review in reviews_tuple),
    }
    costs: list[float | int] = []
    if ocr is not None:
        costs.append(ocr.cost_usd)
    if articles is not None:
        costs.extend((articles.segmentation_cost_usd, articles.reviewer_cost_usd))
    costs.extend(
        cost
        for review in reviews_tuple
        for cost in (review.extraction_cost_usd, review.reviewer_cost_usd)
    )
    costs.extend(partial_costs.values())
    approved = ()
    if state == "approved":
        approved = tuple(
            ApprovedPropositionSet.from_review(
                review, proposition_hashes[review.article_id]
            )
            for review in reviews_tuple
        )
    durable_proposition_hashes = dict(proposition_hashes) or {"__none__": _ZERO_HASH}
    result = IssueDecision(
        identity=identity,
        issue_hash=issue_hash,
        state=state,
        ocr_artifact_hash=ocr_artifact_hash or _ZERO_HASH,
        article_artifact_hash=article_artifact_hash or _ZERO_HASH,
        proposition_artifact_hashes=durable_proposition_hashes,
        article_hashes=article_hashes,
        totals=totals,
        usage=_base_usage(
            ocr, articles, reviews_tuple, accounting, partial_usage
        ),
        cost_usd=float(_sum_numeric(costs, "issue_cost_total_invalid")),
        gate_results=dict(gate_results),
        approved_propositions=approved,
        reasons=tuple(reasons),
    )
    result.validate()
    return result


def _technical_reason(stage: str, exc: BaseException) -> str:
    detail = str(exc).strip() or "no_detail"
    return f"{stage}:{type(exc).__name__}:{detail}"


def review_issue(
    pdf_path: Path, artifact_dir: Path, config: ReviewIssueConfig
) -> IssueDecision:
    """Execute OCR, article, and proposition stages in order for one issue.

    Raises:
        ReviewConfigurationError: the named decision/PDF preconditions do not
            establish a usable issue identity. No stage or provider call has
            begun in this case. Once stage execution begins, technical failures
            are returned as ``pipeline_error`` decisions instead.
    """

    config = _validate_programmatic_config(config)
    issue_path = _path_precondition(pdf_path, "issue_pdf_path_invalid")
    output_dir = _path_precondition(artifact_dir, "artifact_dir_invalid")
    pdf_hash = validate_named_issue(issue_path, config.benchmark_decision)
    identity = _decision_identity(pdf_hash, config)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReviewConfigurationError("artifact_dir_unusable") from exc
    accounting = {
        "attempted": 0,
        "passed": 0,
        "repaired": 0,
        "quarantined": 0,
        "errored": 0,
    }
    gates = {"ocr": False, "articles": False, "propositions": False}
    ocr: OCRManifest | None = None
    articles: ArticleManifest | None = None
    reviews: list[PropositionReview] = []
    ocr_hash: str | None = None
    article_hash: str | None = None
    proposition_hashes: dict[str, str] = {}
    partial_usage: dict[str, float | int] = {
        "ocr": 0,
        "proposition_extraction": 0,
        "proposition_review": 0,
    }
    partial_costs: dict[str, float | int] = {
        "ocr": 0,
        "proposition_extraction": 0,
        "proposition_review": 0,
    }

    def record_partial_accounting(
        stage: str, usage: Mapping[str, float | int], cost: float
    ) -> None:
        if stage not in partial_usage:
            raise ArtifactValidationError("partial_usage_stage_invalid")
        usage_total = _sum_numeric(
            list(validated_usage(usage, "partial_usage_invalid").values()),
            "partial_usage_invalid",
        )
        cost_total = _sum_numeric([cost], "partial_cost_invalid")
        partial_usage[stage] = _sum_numeric(
            [partial_usage[stage], usage_total], "partial_usage_invalid"
        )
        partial_costs[stage] = _sum_numeric(
            [partial_costs[stage], cost_total], "partial_cost_invalid"
        )

    def finish(state: str, reasons: Sequence[str]) -> IssueDecision:
        decision = _decision(
            identity=identity,
            issue_hash=pdf_hash,
            state=state,
            ocr=ocr,
            ocr_artifact_hash=ocr_hash,
            articles=articles,
            article_artifact_hash=article_hash,
            reviews=reviews,
            proposition_hashes=proposition_hashes,
            gate_results=gates,
            accounting=accounting,
            partial_usage=partial_usage,
            partial_costs=partial_costs,
            reasons=reasons,
        )
        write_artifact(output_dir / ISSUE_DECISION_NAME, decision)
        return decision

    accounting["attempted"] += 1
    try:
        ocr = review_issue_ocr(
            issue_path,
            config.ocr,
            output_dir,
            accounting_sink=record_partial_accounting,
        )
        partial_usage["ocr"] = 0
        partial_costs["ocr"] = 0
        ocr.validate()
        if ocr.pdf_hash != pdf_hash or ocr.page_count != _pdf_page_count(issue_path):
            raise ArtifactValidationError("pdf_ocr_page_reconciliation_failed")
        ocr_hash = write_artifact(output_dir / "ocr_manifest.json", ocr)
        accounting["repaired"] = sum(page.repair_attempts for page in ocr.pages)
    except Exception as exc:
        accounting["errored"] += 1
        return finish("pipeline_error", (_technical_reason("ocr", exc),))
    if ocr.status != "passed":
        accounting["quarantined"] += 1
        return finish("quarantined", ocr.quarantine_reasons)
    accounting["passed"] += 1
    gates["ocr"] = True

    accounting["attempted"] += 1
    try:
        transcript = VerifiedIssueTranscript.from_manifest(ocr)
        article_path = output_dir / ARTICLE_MANIFEST_NAME
        articles = _load_matching_article(article_path, transcript)
        if articles is None:
            articles = segment_articles(transcript, config.article_client)
            articles = review_articles_against_issue(
                transcript, articles, config.article_client
            )
            article_hash = write_artifact(article_path, articles)
        else:
            article_hash = _artifact_hash(article_path)
        articles.validate()
        if len(articles.articles) < 1:
            raise ArtifactValidationError("article_review_reconciliation_failed")
    except Exception as exc:
        accounting["errored"] += 1
        return finish("pipeline_error", (_technical_reason("articles", exc),))
    if articles.status != "passed":
        accounting["quarantined"] += 1
        return finish("quarantined", articles.quarantine_reasons)
    accounting["passed"] += 1
    gates["articles"] = True

    accounting["attempted"] += 1
    try:
        for article in articles.articles:
            path = _proposition_path(output_dir, article.article_id)
            review = _load_matching_proposition(
                path,
                article=article,
                article_artifact_hash=article_hash,
                extractor_model=config.proposition_extractor_model,
            )
            if review is None:
                one_article_manifest = replace(articles, articles=(article,))
                review = review_issue_propositions(
                    one_article_manifest,
                    config.proposition_reviewer,
                    extractor=config.proposition_extractor,
                    article_artifact_hash=article_hash,
                    accounting_sink=record_partial_accounting,
                )
                expected_identity = expected_proposition_identity(
                    review,
                    article_hash=article.article_hash,
                    article_artifact_hash=article_hash,
                    extractor_model=config.proposition_extractor_model,
                )
                if review.identity != expected_identity:
                    raise ArtifactValidationError("proposition_identity_mismatch")
                proposition_hashes[article.article_id] = write_artifact(path, review)
            else:
                proposition_hashes[article.article_id] = _artifact_hash(path)
            review.validate(article.text)
            reviews.append(review)
            partial_usage["proposition_extraction"] = 0
            partial_usage["proposition_review"] = 0
            partial_costs["proposition_extraction"] = 0
            partial_costs["proposition_review"] = 0
            if review.status != "passed":
                accounting["quarantined"] += 1
                return finish("quarantined", review.reasons)
        if {review.article_id for review in reviews} != {
            article.article_id for article in articles.articles
        }:
            raise ArtifactValidationError("article_proposition_reconciliation_failed")
    except Exception as exc:
        accounting["errored"] += 1
        return finish("pipeline_error", (_technical_reason("propositions", exc),))
    accounting["passed"] += 1
    gates["propositions"] = True

    return finish("approved", ())


class _SingleUseRequiredOption(argparse.Action):
    """Reject ambiguous repetition of an identity-bearing required option."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        marker = f"_seen_{self.dest}"
        if getattr(namespace, marker, False):
            parser.error(f"{option_string} may be specified only once")
        setattr(namespace, marker, True)
        setattr(namespace, self.dest, values)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf", required=True, type=Path, action=_SingleUseRequiredOption
    )
    parser.add_argument(
        "--artifact-dir",
        required=True,
        type=Path,
        action=_SingleUseRequiredOption,
    )
    parser.add_argument(
        "--benchmark-decision",
        required=True,
        type=Path,
        action=_SingleUseRequiredOption,
    )
    parser.add_argument(
        "--provider-adapter-factory",
        help=(
            "Import path module:function returning ProviderAdapters or "
            "ReviewIssueConfig; may also be set with " + PROVIDER_FACTORY_ENV
        ),
    )
    return parser


def _import_factory(spec: str) -> Callable[[AcceptedBenchmarkDecision], object]:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise IssueReviewConfigurationError("provider_adapter_factory_invalid")
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, attribute)
    except (ImportError, AttributeError) as exc:
        raise IssueReviewConfigurationError("provider_adapter_factory_import_failed") from exc
    if not callable(factory):
        raise IssueReviewConfigurationError("provider_adapter_factory_invalid")
    return factory


def _factory_attribute(value: object, name: str) -> object:
    try:
        return getattr(value, name)
    except AttributeError as exc:
        raise IssueReviewConfigurationError(
            "provider_adapter_factory_result_invalid"
        ) from exc


def _decision_values_equal(
    left: AcceptedBenchmarkDecision, right: object
) -> bool:
    try:
        return (
            _factory_attribute(right, "name") == left.name
            and _factory_attribute(right, "issue_filename") == left.issue_filename
            and _factory_attribute(right, "issue_pdf_sha256")
            == left.issue_pdf_sha256
            and _factory_attribute(right, "accepted_candidate")
            == left.accepted_candidate
            and _factory_attribute(right, "benchmark_report_sha256")
            == left.benchmark_report_sha256
            and _factory_attribute(right, "decision_sha256")
            == left.decision_sha256
        )
    except IssueReviewConfigurationError:
        return False


def _config_from_factory_result(
    decision: AcceptedBenchmarkDecision, configured: object
) -> ReviewIssueConfig:
    """Convert either supported factory shape without module-identity coupling."""

    if hasattr(configured, "initial_ocr_provider"):
        adapters = ProviderAdapters(
            initial_ocr_provider=_factory_attribute(
                configured, "initial_ocr_provider"
            ),
            page_reviewer=_factory_attribute(configured, "page_reviewer"),
            repair_ocr_provider=_factory_attribute(
                configured, "repair_ocr_provider"
            ),
            article_client=_factory_attribute(configured, "article_client"),
            proposition_reviewer=_factory_attribute(
                configured, "proposition_reviewer"
            ),
            proposition_extractor=getattr(
                configured, "proposition_extractor", None
            ),
            proposition_extractor_model=getattr(
                configured, "proposition_extractor_model", EXTRACTION_MODEL
            ),
        )
        return _config_from_adapters(decision, adapters)
    if hasattr(configured, "benchmark_decision"):
        configured_decision = _factory_attribute(configured, "benchmark_decision")
        if not _decision_values_equal(decision, configured_decision):
            raise IssueReviewConfigurationError(
                "provider_factory_decision_mismatch"
            )
        return ReviewIssueConfig(
            benchmark_decision=decision,
            ocr=_factory_attribute(configured, "ocr"),
            article_client=_factory_attribute(configured, "article_client"),
            proposition_reviewer=_factory_attribute(
                configured, "proposition_reviewer"
            ),
            proposition_extractor=getattr(
                configured, "proposition_extractor", None
            ),
            proposition_extractor_model=getattr(
                configured, "proposition_extractor_model", EXTRACTION_MODEL
            ),
        )
    raise IssueReviewConfigurationError("provider_adapter_factory_result_invalid")


def _summary(decision: IssueDecision) -> dict[str, object]:
    return {
        "state": decision.state,
        "attempted": decision.usage["attempted"],
        "passed": decision.usage["passed"],
        "repaired": decision.usage["repaired"],
        "quarantined": decision.usage["quarantined"],
        "errored": decision.usage["errored"],
        "pages": decision.totals["pages"],
        "articles": decision.totals["articles"],
        "propositions": decision.totals["propositions"],
        "usage": {
            name: decision.usage[name]
            for name in (
                "ocr",
                "article_segmentation",
                "article_review",
                "proposition_extraction",
                "proposition_review",
            )
        },
        "cost_usd": decision.cost_usd,
        "reasons": list(decision.reasons),
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    adapter_factory: Callable[[AcceptedBenchmarkDecision], object] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    environment = os.environ if environ is None else environ
    try:
        decision = load_accepted_benchmark_decision(args.benchmark_decision)
        validate_named_issue(args.pdf, decision)
        factory = adapter_factory
        if factory is None:
            factory_spec = args.provider_adapter_factory or environment.get(
                PROVIDER_FACTORY_ENV
            )
            if not factory_spec:
                raise IssueReviewConfigurationError(
                    "provider_adapter_factory_required"
                )
            factory = _import_factory(factory_spec)
        configured = factory(decision)
        config = _config_from_factory_result(decision, configured)
        result = review_issue(args.pdf, args.artifact_dir, config)
    except Exception as exc:
        reason = str(exc).strip() or type(exc).__name__
        print(
            json.dumps(
                {"state": "pipeline_error", "reason": reason},
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(_summary(result), separators=(",", ":"), sort_keys=True))
    return 0 if result.state == "approved" else 1 if result.state == "quarantined" else 2


if __name__ == "__main__":
    raise SystemExit(main())
