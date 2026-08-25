"""Deterministic, resumable page OCR review for one magazine issue."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol, TypedDict

import fitz

from .artifacts import load_valid_artifact, write_artifact
from .benchmark import (
    BenchmarkCandidate,
    BenchmarkFixture,
    OCRProvider,
    OCRResponse,
)
from .schemas import (
    ArtifactValidationError,
    OCRManifest,
    OCRPage,
    StageIdentity,
)
from .transcript import canonical_verified_transcript


RENDERER_SETTINGS = {
    "dpi": 300,
    "colorspace": "RGB",
    "alpha": False,
    "annotations": True,
    "image_format": "png",
}
PAGE_REVIEW_MODEL = "gemini-3.6-flash"
OCR_MANIFEST_NAME = "ocr_manifest.json"
INITIAL_OCR_INSTRUCTIONS = (
    "Transcribe every visible text region on this magazine page in material reading "
    "order. Preserve wording, headings, captions, tables, advertisements, and forms."
)
REPAIR_OCR_INSTRUCTIONS = (
    "Re-transcribe this failed page completely, including every region identified by "
    "the completeness review. Return the full page, not only the missing region."
)
PAGE_REVIEW_INSTRUCTIONS = (
    "Compare the rendered page image with the OCR text region by region. "
    "Advertisements and non-article material are still content and must be reviewed. "
    "Set complete=true only when every visible text region is present and material "
    "reading order is preserved. complete=true is forbidden when any visible text "
    "region is absent, materially reordered, or duplicated. Return only the structured "
    "PageReview fields."
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class OCRReviewError(ValueError):
    """Raised when configuration or external review evidence is invalid."""


class PageReview(TypedDict):
    complete: bool
    missing_regions: list[str]
    reading_order_errors: list[str]
    duplicated_text: list[str]
    reason: str


@dataclass(frozen=True)
class PageReviewResponse:
    """One structured completeness verdict with measured accounting."""

    review: PageReview
    usage: Mapping[str, float | int]
    cost_usd: float


@dataclass(frozen=True)
class RenderedPage:
    """A fixed-rendering page supplied to the multimodal reviewer."""

    pdf_path: Path
    pdf_hash: str
    page_number: int
    image_bytes: bytes
    image_hash: str
    width: int
    height: int


@dataclass(frozen=True)
class IssuePageOCRFixture(BenchmarkFixture):
    """Task 1 provider input extended with the rendered page and stage prompt."""

    image_bytes: bytes
    image_hash: str
    instructions: str
    target_regions: tuple[str, ...]


class PageReviewer(Protocol):
    """The injectable boundary around the external multimodal reviewer."""

    model: str

    def review(
        self, page: RenderedPage, ocr_text: str, instructions: str
    ) -> PageReviewResponse:
        """Compare one rendered page with one complete OCR transcript."""


class GeminiPageReviewer:
    """Callback adapter locked to the structured Gemini completeness model."""

    model = PAGE_REVIEW_MODEL

    def __init__(
        self,
        reviewer: Callable[[RenderedPage, str, str], PageReviewResponse],
    ) -> None:
        self._reviewer = reviewer

    def review(
        self, page: RenderedPage, ocr_text: str, instructions: str
    ) -> PageReviewResponse:
        return self._reviewer(page, ocr_text, instructions)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class OCRReviewConfig:
    """Explicit accepted benchmark selection and injected external boundaries."""

    accepted_candidate: BenchmarkCandidate
    benchmark_decision_hash: str
    initial_provider: OCRProvider
    reviewer: PageReviewer
    repair_provider: OCRProvider
    timestamp: Callable[[], str] = _utc_timestamp

    def validate(self) -> None:
        _validate_candidate(self.accepted_candidate, "accepted_candidate_invalid")
        if _SHA256_RE.fullmatch(self.benchmark_decision_hash) is None:
            raise OCRReviewError("benchmark_decision_hash_invalid")
        initial_candidate = getattr(self.initial_provider, "candidate", None)
        if initial_candidate != self.accepted_candidate:
            raise OCRReviewError("initial_provider_not_accepted_benchmark_winner")
        _validate_candidate(initial_candidate, "initial_provider_candidate_invalid")
        repair_candidate = getattr(self.repair_provider, "candidate", None)
        _validate_candidate(repair_candidate, "repair_provider_candidate_invalid")
        if repair_candidate != BenchmarkCandidate("Gemini", PAGE_REVIEW_MODEL):
            raise OCRReviewError("repair_provider_must_be_gemini_3_6_flash")
        if getattr(self.reviewer, "model", None) != PAGE_REVIEW_MODEL:
            raise OCRReviewError("reviewer_must_be_gemini_3_6_flash")
        if not callable(getattr(self.initial_provider, "transcribe", None)):
            raise OCRReviewError("initial_provider_invalid")
        if not callable(getattr(self.repair_provider, "transcribe", None)):
            raise OCRReviewError("repair_provider_invalid")
        if not callable(getattr(self.reviewer, "review", None)):
            raise OCRReviewError("reviewer_invalid")
        if not callable(self.timestamp):
            raise OCRReviewError("timestamp_factory_invalid")


@dataclass(frozen=True)
class VerifiedTranscriptPage:
    page_number: int
    image_hash: str
    transcript_start: int
    transcript_end: int


@dataclass(frozen=True)
class VerifiedIssueTranscript:
    """The only page transcript shape eligible for article segmentation."""

    text: str
    pages: tuple[VerifiedTranscriptPage, ...]
    ocr_identity: str

    @classmethod
    def from_manifest(cls, manifest: OCRManifest) -> "VerifiedIssueTranscript":
        manifest.validate()
        if manifest.status != "passed":
            raise ArtifactValidationError("verified_transcript_requires_passed_ocr")
        canonical = canonical_verified_transcript(
            tuple((page.page_number, page.text) for page in manifest.pages)
        )
        pages = tuple(
            VerifiedTranscriptPage(
                page_number=span.page_number,
                image_hash=page.image_hash,
                transcript_start=span.transcript_start,
                transcript_end=span.transcript_end,
            )
            for page, span in zip(manifest.pages, canonical.pages)
        )
        transcript = cls(
            text=canonical.text,
            pages=pages,
            ocr_identity=manifest.identity.digest,
        )
        transcript.validate(manifest)
        return transcript

    def validate(self, manifest: OCRManifest) -> None:
        if self.ocr_identity != manifest.identity.digest:
            raise ArtifactValidationError("verified_transcript_identity_mismatch")
        if len(self.pages) != manifest.page_count:
            raise ArtifactValidationError("verified_transcript_page_count_mismatch")
        for transcript_page, ocr_page in zip(self.pages, manifest.pages):
            if (
                transcript_page.page_number != ocr_page.page_number
                or transcript_page.image_hash != ocr_page.image_hash
                or self.text[
                    transcript_page.transcript_start : transcript_page.transcript_end
                ]
                != ocr_page.text
            ):
                raise ArtifactValidationError("verified_transcript_page_mismatch")


def _validate_candidate(value: object, reason: str) -> None:
    if (
        not isinstance(value, BenchmarkCandidate)
        or not isinstance(value.provider, str)
        or not value.provider.strip()
        or not isinstance(value.model, str)
        or not value.model.strip()
    ):
        raise OCRReviewError(reason)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _prompt_fingerprint(value: str) -> str:
    return _sha256_text(value)


def _expected_stage_identity(
    pdf_hash: str,
    accepted_candidate: BenchmarkCandidate,
    benchmark_decision_hash: str,
) -> StageIdentity:
    repair_candidate = BenchmarkCandidate("Gemini", PAGE_REVIEW_MODEL)
    model_identity = json.dumps(
        {
            "initial_provider": accepted_candidate.provider,
            "initial_model": accepted_candidate.model,
            "reviewer_model": PAGE_REVIEW_MODEL,
            "repair_provider": repair_candidate.provider,
            "repair_model": repair_candidate.model,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    prompts = json.dumps(
        {
            "initial": _prompt_fingerprint(INITIAL_OCR_INSTRUCTIONS),
            "review": _prompt_fingerprint(PAGE_REVIEW_INSTRUCTIONS),
            "repair": _prompt_fingerprint(REPAIR_OCR_INSTRUCTIONS),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    identity = StageIdentity(
        schema_version=1,
        input_hashes={
            "issue.pdf": pdf_hash,
            "accepted_benchmark_decision": benchmark_decision_hash,
        },
        model=model_identity,
        prompt_fingerprint=_prompt_fingerprint(prompts),
        renderer_settings=RENDERER_SETTINGS,
    )
    identity.validate()
    return identity


def _stage_identity(pdf_hash: str, config: OCRReviewConfig) -> StageIdentity:
    return _expected_stage_identity(
        pdf_hash, config.accepted_candidate, config.benchmark_decision_hash
    )


def _render_pages(pdf_path: Path, pdf_hash: str) -> tuple[RenderedPage, ...]:
    pages: list[RenderedPage] = []
    with fitz.open(str(pdf_path)) as document:
        if document.page_count < 1:
            raise OCRReviewError("pdf_has_no_pages")
        for page_number, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(
                dpi=RENDERER_SETTINGS["dpi"],
                colorspace=fitz.csRGB,
                alpha=RENDERER_SETTINGS["alpha"],
                annots=RENDERER_SETTINGS["annotations"],
            )
            image_bytes = pixmap.tobytes(RENDERER_SETTINGS["image_format"])
            pages.append(
                RenderedPage(
                    pdf_path=pdf_path,
                    pdf_hash=pdf_hash,
                    page_number=page_number,
                    image_bytes=image_bytes,
                    image_hash=_sha256_bytes(image_bytes),
                    width=pixmap.width,
                    height=pixmap.height,
                )
            )
    return tuple(pages)


def validate_current_ocr_manifest(
    pdf_path: Path,
    manifest: OCRManifest,
    *,
    accepted_candidate: BenchmarkCandidate,
    benchmark_decision_hash: str,
    render_pages: Callable[[Path, str], tuple[RenderedPage, ...]] | None = None,
) -> None:
    """Revalidate durable OCR evidence against current code and source renders."""
    manifest.validate()
    _validate_candidate(accepted_candidate, "accepted_candidate_invalid")
    if _SHA256_RE.fullmatch(benchmark_decision_hash) is None:
        raise OCRReviewError("benchmark_decision_hash_invalid")
    issue_path = Path(pdf_path)
    pdf_hash = _sha256_bytes(issue_path.read_bytes())
    if manifest.pdf_hash != pdf_hash:
        raise ArtifactValidationError("current_ocr_pdf_mismatch")
    expected_identity = _expected_stage_identity(
        pdf_hash, accepted_candidate, benchmark_decision_hash
    )
    if manifest.identity != expected_identity:
        raise ArtifactValidationError("current_ocr_identity_mismatch")
    renderer = render_pages or _render_pages
    rendered = renderer(issue_path, pdf_hash)
    if (
        manifest.page_count != len(rendered)
        or tuple(page.image_hash for page in manifest.pages)
        != tuple(page.image_hash for page in rendered)
    ):
        raise ArtifactValidationError("current_ocr_render_mismatch")
    initial_prompt = _prompt_fingerprint(INITIAL_OCR_INSTRUCTIONS)
    review_prompt = _prompt_fingerprint(PAGE_REVIEW_INSTRUCTIONS)
    repair_prompt = _prompt_fingerprint(REPAIR_OCR_INSTRUCTIONS)
    for page in manifest.pages:
        if (
            page.initial_provider != accepted_candidate.provider
            or page.initial_model != accepted_candidate.model
            or page.initial_prompt_fingerprint != initial_prompt
            or page.reviewer_model != PAGE_REVIEW_MODEL
            or page.reviewer_prompt_fingerprint != review_prompt
        ):
            raise ArtifactValidationError("current_ocr_page_identity_mismatch")
        if page.repair_attempts and (
            page.repair_provider != "Gemini"
            or page.repair_model != PAGE_REVIEW_MODEL
            or page.repair_prompt_fingerprint != repair_prompt
        ):
            raise ArtifactValidationError("current_ocr_repair_identity_mismatch")


def _validate_accounting(
    usage: object, cost_usd: object, reason_prefix: str
) -> tuple[dict[str, float | int], float]:
    if not isinstance(usage, Mapping) or not usage:
        raise OCRReviewError(f"{reason_prefix}_usage_required")
    clean_usage: dict[str, float | int] = {}
    for name, amount in usage.items():
        if (
            not isinstance(name, str)
            or not name
            or isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(amount)
            or amount < 0
        ):
            raise OCRReviewError(f"{reason_prefix}_usage_invalid")
        clean_usage[name] = amount
    if (
        isinstance(cost_usd, bool)
        or not isinstance(cost_usd, (int, float))
        or not math.isfinite(cost_usd)
        or cost_usd < 0
    ):
        raise OCRReviewError(f"{reason_prefix}_cost_invalid")
    return clean_usage, float(cost_usd)


def _validate_ocr_response(response: object, reason_prefix: str) -> OCRResponse:
    if not isinstance(response, OCRResponse):
        raise OCRReviewError(f"{reason_prefix}_response_invalid")
    if not isinstance(response.text, str):
        raise OCRReviewError(f"{reason_prefix}_text_invalid")
    usage, cost = _validate_accounting(response.usage, response.cost_usd, reason_prefix)
    return OCRResponse(text=response.text, usage=usage, cost_usd=cost)


def _validate_review_response(response: object) -> PageReviewResponse:
    if not isinstance(response, PageReviewResponse):
        raise OCRReviewError("reviewer_response_invalid")
    raw = response.review
    if not isinstance(raw, Mapping) or set(raw) != {
        "complete",
        "missing_regions",
        "reading_order_errors",
        "duplicated_text",
        "reason",
    }:
        raise OCRReviewError("reviewer_structured_output_invalid")
    complete = raw["complete"]
    if not isinstance(complete, bool):
        raise OCRReviewError("reviewer_complete_invalid")
    findings: dict[str, list[str]] = {}
    for field in ("missing_regions", "reading_order_errors", "duplicated_text"):
        value = raw[field]
        if (
            not isinstance(value, list)
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise OCRReviewError("reviewer_findings_invalid")
        findings[field] = list(value)
    reason = raw["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise OCRReviewError("reviewer_reason_required")
    if complete and any(findings.values()):
        raise OCRReviewError("reviewer_complete_with_findings")
    usage, cost = _validate_accounting(response.usage, response.cost_usd, "reviewer")
    return PageReviewResponse(
        review={
            "complete": complete,
            "missing_regions": findings["missing_regions"],
            "reading_order_errors": findings["reading_order_errors"],
            "duplicated_text": findings["duplicated_text"],
            "reason": reason,
        },
        usage=usage,
        cost_usd=cost,
    )


def _review_reasons(response: PageReviewResponse) -> tuple[str, ...]:
    verdict = response.review
    if verdict["complete"]:
        return ()
    reasons = [verdict["reason"]]
    for region in verdict["missing_regions"]:
        reasons.append(f"missing_region:{region}")
    for error in verdict["reading_order_errors"]:
        reasons.append(f"reading_order_error:{error}")
    for duplicate in verdict["duplicated_text"]:
        reasons.append(f"duplicated_text:{duplicate}")
    return tuple(reasons)


def _repair_targets(response: PageReviewResponse) -> tuple[str, ...]:
    verdict = response.review
    targets = tuple(
        verdict["missing_regions"]
        + verdict["reading_order_errors"]
        + verdict["duplicated_text"]
    )
    return targets or (verdict["reason"],)


def _add_usage(
    aggregate: dict[str, float | int], usage: Mapping[str, float | int]
) -> None:
    for name, amount in usage.items():
        combined = aggregate.get(name, 0) + amount
        if not math.isfinite(combined):
            raise OCRReviewError("aggregate_usage_invalid")
        aggregate[name] = combined


def _add_cost(total: float, cost: float) -> float:
    combined = total + cost
    if not math.isfinite(combined):
        raise OCRReviewError("aggregate_cost_invalid")
    return combined


def _page_fixture(
    page: RenderedPage,
    instructions: str,
    target_regions: tuple[str, ...] = (),
) -> IssuePageOCRFixture:
    return IssuePageOCRFixture(
        pdf_path=page.pdf_path,
        pdf_sha256=page.pdf_hash,
        page_number=page.page_number,
        fixture_class="issue_review",
        human_scoring={},
        image_bytes=page.image_bytes,
        image_hash=page.image_hash,
        instructions=instructions,
        target_regions=target_regions,
    )


def _matching_resume(
    artifact_path: Path,
    identity: StageIdentity,
    rendered_pages: tuple[RenderedPage, ...],
) -> OCRManifest | None:
    try:
        value = load_valid_artifact(artifact_path, identity)
    except ArtifactValidationError as exc:
        if str(exc) in {"artifact_not_found", "artifact_identity_mismatch"}:
            return None
        raise
    if not isinstance(value, OCRManifest):
        raise ArtifactValidationError("ocr_resume_artifact_type_invalid")
    if value.page_count != len(rendered_pages) or tuple(
        page.image_hash for page in value.pages
    ) != tuple(page.image_hash for page in rendered_pages):
        return None
    return value


def review_issue_ocr(
    pdf_path: Path, config: OCRReviewConfig, artifact_dir: Path
) -> OCRManifest:
    """Review every rendered page and persist one complete OCR stage artifact."""
    config.validate()
    issue_path = Path(pdf_path)
    pdf_bytes = issue_path.read_bytes()
    pdf_hash = _sha256_bytes(pdf_bytes)
    rendered_pages = _render_pages(issue_path, pdf_hash)
    identity = _stage_identity(pdf_hash, config)
    artifact_path = Path(artifact_dir) / OCR_MANIFEST_NAME
    resumed = _matching_resume(artifact_path, identity, rendered_pages)
    if resumed is not None:
        return resumed

    manifest_usage: dict[str, float | int] = {}
    manifest_cost = 0.0
    pages: list[OCRPage] = []
    quarantine_reasons: list[str] = []
    transcript_cursor = 0

    for rendered_page in rendered_pages:
        fixture = _page_fixture(rendered_page, INITIAL_OCR_INSTRUCTIONS)
        initial = _validate_ocr_response(
            config.initial_provider.transcribe(fixture), "initial_ocr"
        )
        initial_timestamp = config.timestamp()
        _add_usage(manifest_usage, initial.usage)
        manifest_cost = _add_cost(manifest_cost, initial.cost_usd)

        first_review = _validate_review_response(
            config.reviewer.review(
                rendered_page, initial.text, PAGE_REVIEW_INSTRUCTIONS
            )
        )
        reviewer_timestamp = config.timestamp()
        reviewer_usage = dict(first_review.usage)
        reviewer_cost = first_review.cost_usd
        _add_usage(manifest_usage, first_review.usage)
        manifest_cost = _add_cost(manifest_cost, first_review.cost_usd)

        repaired_text = None
        repaired_text_hash = None
        repair_provider = None
        repair_model = None
        repair_prompt_fingerprint = None
        repair_usage = None
        repair_cost_usd = None
        repair_timestamp = None
        repair_attempts = 0
        final_text = initial.text
        final_review = first_review

        if not first_review.review["complete"]:
            repair_attempts = 1
            repair_fixture = _page_fixture(
                rendered_page,
                REPAIR_OCR_INSTRUCTIONS,
                _repair_targets(first_review),
            )
            repair = _validate_ocr_response(
                config.repair_provider.transcribe(repair_fixture), "repair_ocr"
            )
            repair_timestamp = config.timestamp()
            repaired_text = repair.text
            repaired_text_hash = _sha256_text(repair.text)
            repair_provider = config.repair_provider.candidate.provider
            repair_model = config.repair_provider.candidate.model
            repair_prompt_fingerprint = _prompt_fingerprint(REPAIR_OCR_INSTRUCTIONS)
            repair_usage = dict(repair.usage)
            repair_cost_usd = repair.cost_usd
            final_text = repair.text
            _add_usage(manifest_usage, repair.usage)
            manifest_cost = _add_cost(manifest_cost, repair.cost_usd)

            final_review = _validate_review_response(
                config.reviewer.review(
                    rendered_page, final_text, PAGE_REVIEW_INSTRUCTIONS
                )
            )
            reviewer_timestamp = config.timestamp()
            _add_usage(reviewer_usage, final_review.usage)
            reviewer_cost = _add_cost(reviewer_cost, final_review.cost_usd)
            _add_usage(manifest_usage, final_review.usage)
            manifest_cost = _add_cost(manifest_cost, final_review.cost_usd)

        complete = final_review.review["complete"]
        reasons = _review_reasons(final_review)
        if not complete:
            quarantine_reasons.append(
                f"page:{rendered_page.page_number}:ocr_incomplete_after_repair"
            )
        page_end = transcript_cursor + len(final_text)
        pages.append(
            OCRPage(
                page_number=rendered_page.page_number,
                image_hash=rendered_page.image_hash,
                initial_text=initial.text,
                initial_text_hash=_sha256_text(initial.text),
                initial_provider=config.initial_provider.candidate.provider,
                initial_model=config.initial_provider.candidate.model,
                initial_prompt_fingerprint=_prompt_fingerprint(
                    INITIAL_OCR_INSTRUCTIONS
                ),
                initial_usage=dict(initial.usage),
                initial_cost_usd=initial.cost_usd,
                initial_timestamp=initial_timestamp,
                reviewer_model=config.reviewer.model,
                reviewer_prompt_fingerprint=_prompt_fingerprint(
                    PAGE_REVIEW_INSTRUCTIONS
                ),
                reviewer_complete=first_review.review["complete"],
                reviewer_reasons=_review_reasons(first_review),
                reviewer_usage=reviewer_usage,
                reviewer_cost_usd=reviewer_cost,
                reviewer_timestamp=reviewer_timestamp,
                repaired_text=repaired_text,
                repaired_text_hash=repaired_text_hash,
                repair_provider=repair_provider,
                repair_model=repair_model,
                repair_prompt_fingerprint=repair_prompt_fingerprint,
                repair_usage=repair_usage,
                repair_cost_usd=repair_cost_usd,
                repair_timestamp=repair_timestamp,
                text=final_text,
                final_text_hash=_sha256_text(final_text),
                transcript_start=transcript_cursor,
                transcript_end=page_end,
                repair_attempts=repair_attempts,
                complete=complete,
                reasons=reasons,
            )
        )
        transcript_cursor = page_end

    manifest = OCRManifest(
        identity=identity,
        pdf_hash=pdf_hash,
        page_count=len(rendered_pages),
        pages=tuple(pages),
        usage=manifest_usage,
        cost_usd=manifest_cost,
        status="quarantined" if quarantine_reasons else "passed",
        quarantine_reasons=tuple(quarantine_reasons),
    )
    manifest.validate()
    write_artifact(artifact_path, manifest)
    return manifest
