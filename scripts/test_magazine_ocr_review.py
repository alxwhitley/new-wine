#!/usr/bin/env python3
"""Credential-free behavior tests for page-level magazine OCR review."""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from pathlib import Path

import fitz
import pytest

import extract_magazine
from magazine_review.artifacts import write_artifact
from magazine_review.benchmark import BenchmarkCandidate, OCRResponse
from magazine_review.ocr import (
    OCRReviewConfig,
    OCRReviewError,
    PageReviewResponse,
    VerifiedIssueTranscript,
    review_issue_ocr,
    validate_current_ocr_manifest,
)
from magazine_review.schemas import ArtifactValidationError


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture
def two_page_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "NewWineMagazine_Issue_02-1974.pdf"
    document = fitz.open()
    article = document.new_page(width=288, height=432)
    article.insert_text((36, 72), "ARTICLE PAGE ONE")
    advertisement = document.new_page(width=288, height=432)
    advertisement.insert_text((36, 72), "ADVERTISEMENT PAGE TWO")
    document.save(path)
    document.close()
    return path


@pytest.fixture
def one_page_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "NewWineMagazine_Issue_03-1974.pdf"
    document = fitz.open()
    page = document.new_page(width=288, height=432)
    page.insert_text((36, 72), "ONLY PAGE")
    document.save(path)
    document.close()
    return path


class FakeOCRProvider:
    def __init__(
        self,
        candidate: BenchmarkCandidate,
        texts: dict[int, str],
        *,
        usage: dict[str, int] | None = None,
        cost_usd: float = 0.10,
    ) -> None:
        self.candidate = candidate
        self.texts = texts
        self.usage = usage or {"input_tokens": 10, "output_tokens": 2}
        self.cost_usd = cost_usd
        self.page_numbers: list[int] = []
        self.fixtures: list[object] = []

    def transcribe(self, fixture) -> OCRResponse:
        self.page_numbers.append(fixture.page_number)
        self.fixtures.append(fixture)
        return OCRResponse(
            text=self.texts[fixture.page_number],
            usage=self.usage,
            cost_usd=self.cost_usd,
        )


def review(
    complete: bool,
    *,
    missing_regions: tuple[str, ...] = (),
    reading_order_errors: tuple[str, ...] = (),
    duplicated_text: tuple[str, ...] = (),
    reason: str = "complete",
) -> PageReviewResponse:
    return PageReviewResponse(
        review={
            "complete": complete,
            "missing_regions": list(missing_regions),
            "reading_order_errors": list(reading_order_errors),
            "duplicated_text": list(duplicated_text),
            "reason": reason,
        },
        usage={"input_tokens": 3, "output_tokens": 1},
        cost_usd=0.02,
    )


class FakeReviewer:
    model = "gemini-3.6-flash"

    def __init__(self, responses: list[PageReviewResponse]) -> None:
        self.responses = list(responses)
        self.page_numbers: list[int] = []
        self.instructions: list[str] = []

    def review(self, page, ocr_text: str, instructions: str) -> PageReviewResponse:
        self.page_numbers.append(page.page_number)
        self.instructions.append(instructions)
        return self.responses.pop(0)


def config(
    *,
    initial: FakeOCRProvider,
    reviewer: FakeReviewer,
    repair: FakeOCRProvider,
    accepted_candidate: BenchmarkCandidate | None = None,
) -> OCRReviewConfig:
    return OCRReviewConfig(
        accepted_candidate=accepted_candidate or initial.candidate,
        benchmark_decision_hash=sha("alex-accepted-blind-benchmark"),
        initial_provider=initial,
        reviewer=reviewer,
        repair_provider=repair,
    )


def passing_config(page_texts: dict[int, str]) -> OCRReviewConfig:
    initial = FakeOCRProvider(
        BenchmarkCandidate("accepted-provider", "accepted-model"), page_texts
    )
    reviewer = FakeReviewer([review(True) for _ in page_texts])
    repair = FakeOCRProvider(
        BenchmarkCandidate("Gemini", "gemini-3.6-flash"), page_texts
    )
    return config(initial=initial, reviewer=reviewer, repair=repair)


def test_reviews_ad_page_and_repairs_only_failed_page(
    two_page_pdf: Path, tmp_path: Path
) -> None:
    """Skipping ad-like pages or repairing passing pages must fail this test."""
    initial = FakeOCRProvider(
        BenchmarkCandidate("accepted-provider", "accepted-model"),
        {1: "article page one", 2: "advertisement page two"},
    )
    reviewer = FakeReviewer(
        [
            review(True),
            review(False, missing_regions=("coupon price",), reason="missing ad copy"),
            review(True),
        ]
    )
    repair = FakeOCRProvider(
        BenchmarkCandidate("Gemini", "gemini-3.6-flash"),
        {2: "repaired advertisement page two with coupon price"},
        usage={"input_tokens": 5, "output_tokens": 2},
        cost_usd=0.03,
    )

    manifest = review_issue_ocr(
        two_page_pdf,
        config(initial=initial, reviewer=reviewer, repair=repair),
        tmp_path / "artifacts",
    )

    assert initial.page_numbers == [1, 2]
    assert reviewer.page_numbers == [1, 2, 2]
    assert repair.page_numbers == [2]
    assert manifest.status == "passed"
    assert manifest.pages[0].repair_attempts == 0
    assert manifest.pages[1].repair_attempts == 1
    assert manifest.pages[1].text == "repaired advertisement page two with coupon price"
    assert "advertisements and non-article material" in reviewer.instructions[0].lower()
    assert "coupon price" in repair.fixtures[0].target_regions
    assert "failed page completely" in repair.fixtures[0].instructions
    assert repair.fixtures[0].image_hash == manifest.pages[1].image_hash


def test_contradictory_complete_verdict_conservatively_triggers_repair(
    one_page_pdf: Path, tmp_path: Path
) -> None:
    initial = FakeOCRProvider(
        BenchmarkCandidate("accepted-provider", "accepted-model"),
        {1: "page missing footer"},
    )
    reviewer = FakeReviewer(
        [
            review(
                True,
                missing_regions=("footer",),
                reason="Footer was not captured.",
            ),
            review(True),
        ]
    )
    repair = FakeOCRProvider(
        BenchmarkCandidate("Gemini", "gemini-3.6-flash"),
        {1: "page including footer"},
    )

    manifest = review_issue_ocr(
        one_page_pdf,
        config(initial=initial, reviewer=reviewer, repair=repair),
        tmp_path / "artifacts",
    )

    assert repair.page_numbers == [1]
    assert manifest.status == "passed"
    assert manifest.pages[0].repair_attempts == 1
    assert "complete=true" in manifest.pages[0].reviewer_reasons[0]


def test_second_failure_quarantines_entire_issue(
    one_page_pdf: Path, tmp_path: Path
) -> None:
    """A second completeness failure must never be treated as verified OCR."""
    initial = FakeOCRProvider(
        BenchmarkCandidate("accepted-provider", "accepted-model"),
        {1: "incomplete page"},
    )
    reviewer = FakeReviewer(
        [
            review(False, missing_regions=("bottom half",), reason="missing text"),
            review(False, missing_regions=("footer",), reason="still missing text"),
        ]
    )
    repair = FakeOCRProvider(
        BenchmarkCandidate("Gemini", "gemini-3.6-flash"),
        {1: "still incomplete page"},
    )

    manifest = review_issue_ocr(
        one_page_pdf,
        config(initial=initial, reviewer=reviewer, repair=repair),
        tmp_path / "artifacts",
    )

    assert manifest.status == "quarantined"
    assert manifest.quarantine_reasons == ("page:1:ocr_incomplete_after_repair",)
    assert manifest.pages[0].repair_attempts == 1
    assert manifest.pages[0].complete is False
    assert reviewer.page_numbers == [1, 1]
    assert repair.page_numbers == [1]
    with pytest.raises(ArtifactValidationError, match="verified_transcript_requires_passed_ocr"):
        VerifiedIssueTranscript.from_manifest(manifest)


def test_verified_transcript_has_stable_delimiters_and_exact_page_offsets(
    two_page_pdf: Path, tmp_path: Path
) -> None:
    """Broken page delimiters or offsets must not reach article review."""
    manifest = review_issue_ocr(
        two_page_pdf,
        passing_config({1: "first page", 2: "second page"}),
        tmp_path / "artifacts",
    )

    transcript = VerifiedIssueTranscript.from_manifest(manifest)

    assert transcript.text == (
        "=== PAGE 1 ===\nfirst page\n\n=== PAGE 2 ===\nsecond page"
    )
    assert transcript.pages[0].transcript_start == len("=== PAGE 1 ===\n")
    assert transcript.pages[0].transcript_end == len("=== PAGE 1 ===\nfirst page")
    assert transcript.pages[1].transcript_start == len(
        "=== PAGE 1 ===\nfirst page\n\n=== PAGE 2 ===\n"
    )
    assert transcript.text[
        transcript.pages[1].transcript_start : transcript.pages[1].transcript_end
    ] == "second page"
    assert manifest.pages[0].transcript_start == 0
    assert manifest.pages[1].transcript_start == len("first page")


def test_usage_and_cost_reconcile_every_external_call(
    two_page_pdf: Path, tmp_path: Path
) -> None:
    """Dropping initial, review, or repair accounting must fail reconciliation."""
    initial = FakeOCRProvider(
        BenchmarkCandidate("accepted-provider", "accepted-model"),
        {1: "first page", 2: "second page"},
    )
    reviewer = FakeReviewer(
        [review(True), review(False, reason="retry"), review(True)]
    )
    repair = FakeOCRProvider(
        BenchmarkCandidate("Gemini", "gemini-3.6-flash"),
        {2: "repaired second page"},
        usage={"input_tokens": 5, "output_tokens": 2},
        cost_usd=0.03,
    )

    manifest = review_issue_ocr(
        two_page_pdf,
        config(initial=initial, reviewer=reviewer, repair=repair),
        tmp_path / "artifacts",
    )

    assert manifest.usage == {"input_tokens": 34, "output_tokens": 9}
    assert manifest.cost_usd == pytest.approx(0.29)
    assert manifest.pages[1].reviewer_usage == {
        "input_tokens": 6,
        "output_tokens": 2,
    }
    assert manifest.pages[1].reviewer_cost_usd == pytest.approx(0.04)
    assert repair.fixtures[0].target_regions == ("retry",)


def test_matching_manifest_resumes_without_provider_or_reviewer_calls(
    two_page_pdf: Path, tmp_path: Path
) -> None:
    """A valid matching cache must prevent repeated paid calls."""
    artifact_dir = tmp_path / "artifacts"
    first = review_issue_ocr(
        two_page_pdf,
        passing_config({1: "first page", 2: "second page"}),
        artifact_dir,
    )
    resumed_config = passing_config({1: "unused", 2: "unused"})

    resumed = review_issue_ocr(two_page_pdf, resumed_config, artifact_dir)

    assert resumed == first
    assert resumed_config.initial_provider.page_numbers == []
    assert resumed_config.reviewer.page_numbers == []
    assert resumed_config.repair_provider.page_numbers == []


def test_render_hash_mismatch_recomputes_instead_of_resuming_stale_manifest(
    two_page_pdf: Path, tmp_path: Path
) -> None:
    """A changed deterministic render must recompute rather than abort or resume."""
    artifact_dir = tmp_path / "artifacts"
    first = review_issue_ocr(
        two_page_pdf,
        passing_config({1: "old first page", 2: "old second page"}),
        artifact_dir,
    )
    stale_first_page = replace(first.pages[0], image_hash=sha("stale-render"))
    stale = replace(first, pages=(stale_first_page, first.pages[1]))
    write_artifact(artifact_dir / "ocr_manifest.json", stale)
    refreshed_config = passing_config({1: "new first page", 2: "new second page"})

    refreshed = review_issue_ocr(two_page_pdf, refreshed_config, artifact_dir)

    assert refreshed_config.initial_provider.page_numbers == [1, 2]
    assert refreshed_config.reviewer.page_numbers == [1, 2]
    assert refreshed_config.repair_provider.page_numbers == []
    assert refreshed.pages[0].image_hash == first.pages[0].image_hash
    assert refreshed.pages[0].text == "new first page"
    assert refreshed != stale


def test_initial_provider_must_match_explicit_accepted_benchmark_candidate(
    one_page_pdf: Path, tmp_path: Path
) -> None:
    """Changing the provider without a new accepted decision must stop all calls."""
    initial = FakeOCRProvider(
        BenchmarkCandidate("unaccepted-provider", "unaccepted-model"),
        {1: "page"},
    )
    reviewer = FakeReviewer([review(True)])
    repair = FakeOCRProvider(
        BenchmarkCandidate("Gemini", "gemini-3.6-flash"), {1: "page"}
    )
    review_config = config(
        initial=initial,
        reviewer=reviewer,
        repair=repair,
        accepted_candidate=BenchmarkCandidate("accepted-provider", "accepted-model"),
    )

    with pytest.raises(OCRReviewError, match="initial_provider_not_accepted_benchmark_winner"):
        review_issue_ocr(one_page_pdf, review_config, tmp_path / "artifacts")

    assert initial.page_numbers == []
    assert reviewer.page_numbers == []
    assert repair.page_numbers == []


def test_image_only_page_accepts_exact_empty_text_only_after_passing_review(
    one_page_pdf: Path, tmp_path: Path
) -> None:
    """A genuinely text-free page may pass, retaining the exact empty-text hash."""
    initial = FakeOCRProvider(
        BenchmarkCandidate("accepted-provider", "accepted-model"), {1: ""}
    )
    reviewer = FakeReviewer([review(True, reason="image-only page has no visible text")])
    repair = FakeOCRProvider(
        BenchmarkCandidate("Gemini", "gemini-3.6-flash"), {1: "unused"}
    )

    manifest = review_issue_ocr(
        one_page_pdf,
        config(initial=initial, reviewer=reviewer, repair=repair),
        tmp_path / "artifacts",
    )

    assert manifest.status == "passed"
    assert manifest.pages[0].text == ""
    assert manifest.pages[0].final_text_hash == hashlib.sha256(b"").hexdigest()
    assert repair.page_numbers == []


def test_ocr_accounting_sink_records_completed_call_before_later_failure(
    one_page_pdf: Path, tmp_path: Path
) -> None:
    """A later reviewer exception cannot erase the completed initial OCR spend."""
    initial = FakeOCRProvider(
        BenchmarkCandidate("accepted-provider", "accepted-model"),
        {1: "verified initial text"},
    )

    class FailingReviewer:
        model = "gemini-3.6-flash"

        def review(self, *_args, **_kwargs):
            raise TimeoutError("review failed after initial OCR")

    repair = FakeOCRProvider(
        BenchmarkCandidate("Gemini", "gemini-3.6-flash"), {1: "unused"}
    )
    recorded = []
    kwargs = {}
    if "accounting_sink" in inspect.signature(review_issue_ocr).parameters:
        kwargs["accounting_sink"] = (
            lambda stage, usage, cost: recorded.append((stage, dict(usage), cost))
        )

    with pytest.raises(TimeoutError, match="review failed after initial OCR"):
        review_issue_ocr(
            one_page_pdf,
            config(initial=initial, reviewer=FailingReviewer(), repair=repair),
            tmp_path / "artifacts",
            **kwargs,
        )

    assert recorded == [
        ("ocr", {"input_tokens": 10, "output_tokens": 2}, 0.10)
    ]


def test_current_ocr_validator_rejects_stale_identity_and_render(
    one_page_pdf: Path, tmp_path: Path
) -> None:
    """Ingestion-time validation must bind both current config and rendered bytes."""
    review_config = passing_config({1: "verified page"})
    manifest = review_issue_ocr(
        one_page_pdf, review_config, tmp_path / "artifacts"
    )

    with pytest.raises(ArtifactValidationError, match="current_ocr_identity_mismatch"):
        validate_current_ocr_manifest(
            one_page_pdf,
            replace(manifest, identity=replace(manifest.identity, model="stale")),
            accepted_candidate=review_config.accepted_candidate,
            benchmark_decision_hash=review_config.benchmark_decision_hash,
        )

    rendered = list(
        __import__("magazine_review.ocr", fromlist=["_render_pages"])._render_pages(
            one_page_pdf, manifest.pdf_hash
        )
    )
    rendered[0] = replace(rendered[0], image_hash=sha("stale render"))
    with pytest.raises(ArtifactValidationError, match="current_ocr_render_mismatch"):
        validate_current_ocr_manifest(
            one_page_pdf,
            manifest,
            accepted_candidate=review_config.accepted_candidate,
            benchmark_decision_hash=review_config.benchmark_decision_hash,
            render_pages=lambda _path, _hash: tuple(rendered),
        )


def test_review_pipeline_legacy_entry_uses_verified_pages_without_moving_pdf(
    one_page_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opt-in review mode must replace Pass 1, use GPT-OSS, and retain the PDF."""
    issue_root = tmp_path / "extracted"
    artifact_root = tmp_path / "artifacts"
    models: list[str] = []
    monkeypatch.setattr(extract_magazine, "EXTRACTED_DIR", issue_root)
    monkeypatch.setattr(extract_magazine, "init_tracker", lambda: None)
    monkeypatch.setattr(extract_magazine, "update_tracker_row", lambda *_: None)
    monkeypatch.setattr(
        extract_magazine,
        "pass1_extract",
        lambda *_: pytest.fail("legacy Pass 1 ran in review mode"),
    )
    monkeypatch.setattr(
        extract_magazine,
        "pass2_segment",
        lambda _issue_dir, _meta, *, model: models.append(model) or 0,
    )
    monkeypatch.setattr(
        extract_magazine,
        "pass3_qa",
        lambda *_args, **_kwargs: {"pass": 0, "warn": 0, "flag": 0},
    )

    result = extract_magazine.process_issue(
        one_page_pdf,
        review_pipeline=True,
        artifact_dir=artifact_root,
        review_config=passing_config({1: "verified only page"}),
    )

    raw_text = issue_root / one_page_pdf.stem / "raw_text.txt"
    assert result == "processed"
    assert models == ["openai/gpt-oss-120b"]
    assert raw_text.read_text(encoding="utf-8") == "=== PAGE 1 ===\nverified only page"
    assert (artifact_root / one_page_pdf.stem / "ocr_manifest.json").exists()
    assert one_page_pdf.exists()


def test_review_pipeline_quarantine_stops_legacy_article_stages(
    one_page_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed page must stop both legacy article stages without moving the PDF."""
    initial = FakeOCRProvider(
        BenchmarkCandidate("accepted-provider", "accepted-model"), {1: "bad page"}
    )
    reviewer = FakeReviewer([review(False, reason="bad"), review(False, reason="bad")])
    repair = FakeOCRProvider(
        BenchmarkCandidate("Gemini", "gemini-3.6-flash"), {1: "still bad"}
    )
    monkeypatch.setattr(extract_magazine, "EXTRACTED_DIR", tmp_path / "extracted")
    monkeypatch.setattr(extract_magazine, "init_tracker", lambda: None)
    monkeypatch.setattr(extract_magazine, "update_tracker_row", lambda *_: None)
    monkeypatch.setattr(
        extract_magazine,
        "pass1_extract",
        lambda *_: pytest.fail("legacy Pass 1 ran in review mode"),
    )
    monkeypatch.setattr(
        extract_magazine,
        "pass2_segment",
        lambda *_args, **_kwargs: pytest.fail("article segmentation ran after quarantine"),
    )
    monkeypatch.setattr(
        extract_magazine,
        "pass3_qa",
        lambda *_args, **_kwargs: pytest.fail("article QA ran after quarantine"),
    )

    result = extract_magazine.process_issue(
        one_page_pdf,
        review_pipeline=True,
        artifact_dir=tmp_path / "artifacts",
        review_config=config(initial=initial, reviewer=reviewer, repair=repair),
    )

    assert result == "failed"
    assert one_page_pdf.exists()


def test_review_config_requires_artifact_directory_before_any_page_call(
    one_page_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The opt-in legacy mode must not fall back when its artifact path is absent."""
    monkeypatch.setattr(extract_magazine, "init_tracker", lambda: None)
    monkeypatch.setattr(extract_magazine, "update_tracker_row", lambda *_: None)
    review_config = passing_config({1: "page"})

    with pytest.raises(ValueError, match="review_pipeline_artifact_dir_required"):
        extract_magazine.process_issue(
            one_page_pdf,
            review_pipeline=True,
            review_config=review_config,
        )

    assert review_config.initial_provider.page_numbers == []


def test_legacy_cli_entry_point_passes_only_existing_options() -> None:
    """Adding review-only arguments to the legacy entry point must fail this test."""
    calls: list[dict[str, object]] = []

    exit_code = extract_magazine.main(
        ["--time-limit", "1.5", "--max-issues", "2"],
        runner=lambda **kwargs: calls.append(kwargs),
    )

    assert exit_code == 0
    assert calls == [{"time_limit_min": 1.5, "max_issues": 2}]


def test_review_flags_are_deferred_to_the_task_6_entry_point() -> None:
    """The legacy CLI must not advertise an unusable review configuration."""
    calls: list[dict[str, object]] = []

    with pytest.raises(SystemExit) as exc:
        extract_magazine.main(
            ["--review-pipeline", "--artifact-dir", "/tmp/review-artifacts"],
            runner=lambda **kwargs: calls.append(kwargs),
        )

    assert exc.value.code == 2
    assert calls == []


def test_default_run_calls_the_legacy_issue_path_without_review_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default batch execution must keep its pre-review process_issue boundary."""
    queue_dir = tmp_path / "queue"
    extracted_dir = tmp_path / "extracted"
    queue_dir.mkdir()
    pdf_path = queue_dir / "legacy.pdf"
    pdf_path.write_bytes(b"process_issue is injected and will not open this fixture")
    calls: list[Path] = []

    def legacy_process_issue(candidate: Path) -> str:
        calls.append(candidate)
        return "processed"

    monkeypatch.setattr(extract_magazine, "TO_EXTRACT_DIR", queue_dir)
    monkeypatch.setattr(extract_magazine, "EXTRACTED_DIR", extracted_dir)
    monkeypatch.setattr(extract_magazine, "process_issue", legacy_process_issue)

    extract_magazine.run(max_issues=1)

    assert calls == [pdf_path]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
