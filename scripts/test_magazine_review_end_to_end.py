#!/usr/bin/env python3
"""Credential-free proof of the complete New Wine review and preview flow."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz
import pytest

import ingest_magazine
import propositions
import review_magazine_issue as runner
import shared_ingest
from magazine_review.benchmark import BenchmarkCandidate, OCRResponse
from magazine_review.ocr import (
    INITIAL_OCR_INSTRUCTIONS,
    PAGE_REVIEW_INSTRUCTIONS,
    REPAIR_OCR_INSTRUCTIONS,
    OCRReviewConfig,
    PageReviewResponse,
    RenderedPage,
)
from magazine_review.schemas import OCRManifest
from magazine_review.transcript import canonical_verified_transcript
from propositions import PropositionExtractionComputation, ReferenceGroundingComputation


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "magazine_review"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_fixture(name: str) -> dict[str, Any]:
    raw = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert set(raw) == {
        "schema_version",
        "issue",
        "pages",
        "verified_transcript",
        "article_review",
        "proposition_review",
        "expected",
    }
    encoded = json.dumps(raw, sort_keys=True).casefold()
    for forbidden in ("api_key", "service_key", "password", "credentials", "secret"):
        assert forbidden not in encoded
    return raw


@dataclass
class ExternalCalls:
    initial_ocr: int = 0
    page_review: int = 0
    repair_ocr: int = 0
    article_model: int = 0
    proposition_extraction: int = 0
    proposition_review: int = 0


def _fixture_image(page: dict[str, Any]) -> bytes:
    image_bytes = base64.b64decode(page["image_bytes_base64"], validate=True)
    assert hashlib.sha256(image_bytes).hexdigest() == page["image_sha256"], (
        "fixture_image_hash_mismatch"
    )
    return image_bytes


def _fixture_rendered_pages(
    pdf_path: Path, pdf_hash: str, pages: list[dict[str, Any]]
) -> tuple[RenderedPage, ...]:
    assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == pdf_hash
    return tuple(
        RenderedPage(
            pdf_path=pdf_path,
            pdf_hash=pdf_hash,
            page_number=page["page_number"],
            image_bytes=_fixture_image(page),
            image_hash=page["image_sha256"],
            width=page["image_width"],
            height=page["image_height"],
        )
        for page in pages
    )


class _FixtureOCRProvider:
    def __init__(
        self,
        candidate: BenchmarkCandidate,
        pages: list[dict[str, Any]],
        calls: ExternalCalls,
        *,
        repair: bool,
    ) -> None:
        self.candidate = candidate
        self._pages = {page["page_number"]: page for page in pages}
        self._calls = calls
        self._repair = repair

    def transcribe(self, page_fixture) -> OCRResponse:
        page = self._pages[page_fixture.page_number]
        key = "repaired_ocr" if self._repair else "initial_ocr"
        assert page_fixture.image_bytes == _fixture_image(page)
        assert page_fixture.image_hash == page["image_sha256"]
        assert page_fixture.pdf_sha256 == hashlib.sha256(
            page_fixture.pdf_path.read_bytes()
        ).hexdigest()
        assert page_fixture.instructions == (
            REPAIR_OCR_INSTRUCTIONS if self._repair else INITIAL_OCR_INSTRUCTIONS
        )
        assert page_fixture.target_regions == (
            tuple(page["expected_repair_targets"]) if self._repair else ()
        )
        if self._repair:
            self._calls.repair_ocr += 1
        else:
            self._calls.initial_ocr += 1
        response = page[key]
        if response is None:
            raise AssertionError(f"unexpected {key} call for page {page_fixture.page_number}")
        return OCRResponse(
            text=response["text"],
            usage=dict(response["usage"]),
            cost_usd=response["cost_usd"],
        )


class _FixturePageReviewer:
    model = "gemini-3.6-flash"

    def __init__(self, pages: list[dict[str, Any]], calls: ExternalCalls) -> None:
        self._responses = [
            (page, response)
            for page in pages
            for response in page["reviews"]
        ]
        self._calls = calls

    def review(self, page, ocr_text: str, instructions: str) -> PageReviewResponse:
        self._calls.page_review += 1
        expected_page, response = self._responses.pop(0)
        assert page.page_number == expected_page["page_number"]
        assert page.image_bytes == _fixture_image(expected_page)
        assert page.image_hash == expected_page["image_sha256"]
        assert ocr_text == response["reviewed_text"]
        assert instructions == PAGE_REVIEW_INSTRUCTIONS
        return PageReviewResponse(
            review=copy.deepcopy(response["verdict"]),
            usage=dict(response["usage"]),
            cost_usd=response["cost_usd"],
        )


class _FixtureArticleClient:
    def __init__(self, fixture: dict[str, Any], calls: ExternalCalls) -> None:
        self._fixture = fixture
        self._calls = calls

    def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        self._calls.article_model += 1
        if self._fixture["must_not_run"]:
            raise AssertionError("article model called after OCR quarantine")
        if request["stage"] == "article_segmentation":
            response = self._fixture["segmentation"]
            output = {
                "ocr_identity": request["ocr_identity"],
                "transcript_hash": request["transcript_hash"],
                "articles": [
                    {
                        key: copy.deepcopy(value)
                        for key, value in article.items()
                        if key not in {"text", "source_pages"}
                    }
                    for article in response["articles"]
                ],
            }
        elif request["stage"] == "article_completeness_review":
            response = self._fixture["review"]
            output = {
                "ocr_identity": request["ocr_identity"],
                "transcript_hash": request["transcript_hash"],
                "article_set_hash": request["article_set_hash"],
                "issue_coverage_complete": response.get(
                    "issue_coverage_complete", True
                ),
                "missing_substantive_spans": copy.deepcopy(
                    response.get("missing_substantive_spans", [])
                ),
                "missing_articles": copy.deepcopy(
                    response.get("missing_articles", [])
                ),
                "articles": copy.deepcopy(response["articles"]),
            }
        else:
            raise AssertionError(f"unexpected article stage: {request['stage']}")
        return {
            "output": output,
            "usage": dict(response["usage"]),
            "cost_usd": response["cost_usd"],
        }


class _FixturePropositionReviewer:
    def __init__(self, fixture: dict[str, Any], calls: ExternalCalls) -> None:
        self._fixture = fixture
        self._calls = calls

    def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        self._calls.proposition_review += 1
        if self._fixture["must_not_run"]:
            raise AssertionError("proposition reviewer called after OCR quarantine")
        response = self._fixture["review"]
        return {
            "output": {
                "article_id": request["article"]["article_id"],
                "article_hash": request["article"]["text_hash"],
                "propositions": copy.deepcopy(response["propositions"]),
            },
            "usage": dict(response["usage"]),
            "cost_usd": response["cost_usd"],
        }


def _fixture_extractor(
    fixture: dict[str, Any], calls: ExternalCalls
):
    def extract(**kwargs) -> PropositionExtractionComputation:
        calls.proposition_extraction += 1
        if fixture["must_not_run"]:
            raise AssertionError("proposition extraction called after OCR quarantine")
        response = fixture["extraction"]
        assert kwargs["text"] == response["article_text"]
        assert kwargs["speaker"] == response["speaker"]
        assert kwargs["prompt_version"] == "v3.1"
        output = copy.deepcopy(response["propositions"])
        totals = response["grounding_totals"]
        grounding = ReferenceGroundingComputation(
            propositions=copy.deepcopy(output),
            review_records=[],
            n_found=totals["found"],
            n_grounded=totals["grounded"],
            n_stripped_fabricated=totals["stripped_fabricated"],
            n_stripped_uncertain=totals["stripped_uncertain"],
            n_kept_arbitration=totals["kept_arbitration"],
        )
        return PropositionExtractionComputation(
            output=output,
            model=response["model"],
            usage=dict(response["usage"]),
            cost_usd=response["cost_usd"],
            grounding=grounding,
        )

    return extract


def _build_pdf(issue_dir: Path, fixture: dict[str, Any]) -> Path:
    issue_dir.mkdir(parents=True)
    pdf_path = issue_dir / fixture["issue"]["filename"]
    document = fitz.open()
    for page in fixture["pages"]:
        pdf_page = document.new_page(width=432, height=648)
        pdf_page.insert_textbox(
            fitz.Rect(36, 48, 396, 612),
            page["visible_text"],
            fontsize=11,
        )
    document.save(pdf_path)
    document.close()
    return pdf_path


def _write_reviewed_markdown(issue_dir: Path, fixture: dict[str, Any]) -> None:
    for article in fixture["article_review"]["segmentation"]["articles"]:
        md_path = issue_dir / Path(article["filename"]).with_suffix(".md")
        md_path.write_text(
            "---\n"
            f"TITLE: {article['title']}\n"
            f"AUTHOR: {article['author']}\n"
            f"ISSUE: {fixture['issue']['label']}\n"
            f"DATE: {fixture['issue']['date']}\n"
            "TOPIC_TAGS: Grace, Service\n"
            "BIBLE_REFS:\n"
            "---\n"
            f"{article['text']}\n",
            encoding="utf-8",
        )


@dataclass(frozen=True)
class FixtureRun:
    fixture: dict[str, Any]
    decision: Any
    calls: ExternalCalls
    issue_dir: Path
    artifact_dir: Path


def _run_fixture(name: str, tmp_path: Path, monkeypatch) -> FixtureRun:
    fixture = _load_fixture(name)
    issue_dir = tmp_path / fixture["issue"]["directory"]
    artifact_dir = tmp_path / f"{name}-artifacts"
    pdf_path = _build_pdf(issue_dir, fixture)
    pages = fixture["pages"]
    monkeypatch.setattr(
        "magazine_review.ocr._render_pages",
        lambda rendered_pdf_path, pdf_hash: _fixture_rendered_pages(
            rendered_pdf_path, pdf_hash, pages
        ),
    )
    calls = ExternalCalls()
    accepted = BenchmarkCandidate("fixture-accepted-ocr", "fixture-ocr-v1")
    repair = BenchmarkCandidate("Gemini", "gemini-3.6-flash")
    decision = runner.AcceptedBenchmarkDecision(
        name="fixture-only-accepted-benchmark",
        issue_filename=pdf_path.name,
        issue_pdf_sha256=hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        accepted_candidate=accepted,
        benchmark_report_sha256=_sha256("fixture-reviewed-blind-report"),
        decision_sha256=_sha256("fixture-accepted-decision"),
    )
    config = runner.ReviewIssueConfig(
        benchmark_decision=decision,
        ocr=OCRReviewConfig(
            accepted_candidate=accepted,
            benchmark_decision_hash=decision.decision_sha256,
            initial_provider=_FixtureOCRProvider(accepted, pages, calls, repair=False),
            reviewer=_FixturePageReviewer(pages, calls),
            repair_provider=_FixtureOCRProvider(repair, pages, calls, repair=True),
            timestamp=lambda: "2026-08-25T12:00:00Z",
        ),
        article_client=_FixtureArticleClient(fixture["article_review"], calls),
        proposition_reviewer=_FixturePropositionReviewer(
            fixture["proposition_review"], calls
        ),
        proposition_extractor=_fixture_extractor(
            fixture["proposition_review"], calls
        ),
        proposition_extractor_model="openai/gpt-oss-120b",
    )

    reviewed = runner.review_issue(pdf_path, artifact_dir, config)
    ocr = ingest_magazine._load_artifact(
        artifact_dir / ingest_magazine.OCR_MANIFEST_NAME, OCRManifest
    )
    expected_transcript = fixture["verified_transcript"]
    canonical = canonical_verified_transcript(
        tuple((page.page_number, page.text) for page in ocr.pages)
    )
    assert canonical.text == expected_transcript["text"]
    assert [
        {
            "page_number": page.page_number,
            "transcript_start": page.transcript_start,
            "transcript_end": page.transcript_end,
        }
        for page in canonical.pages
    ] == expected_transcript["pages"]
    assert [page.transcript_start for page in ocr.pages] == [
        page["ocr_transcript_start"] for page in pages
    ]
    assert [page.transcript_end for page in ocr.pages] == [
        page["ocr_transcript_end"] for page in pages
    ]
    assert (reviewed.state == "approved") is expected_transcript["eligible"]
    if reviewed.state == "approved":
        _write_reviewed_markdown(issue_dir, fixture)
    return FixtureRun(fixture, reviewed, calls, issue_dir, artifact_dir)


@dataclass(frozen=True)
class DryIngestPreview:
    proposition_texts: tuple[str, ...]
    stats: dict[str, Any]
    db_calls: int
    embedding_calls: int
    generation_calls: int
    move_calls: int


def _preview_ingest(run: FixtureRun, monkeypatch) -> DryIngestPreview:
    boundary_calls = {"db": 0, "embedding": 0, "generation": 0, "move": 0}

    def forbidden(boundary: str):
        def fail(*_args, **_kwargs):
            boundary_calls[boundary] += 1
            raise AssertionError(f"dry ingest crossed {boundary} boundary")

        return fail

    monkeypatch.setattr(ingest_magazine, "get_db", forbidden("db"))
    monkeypatch.setattr(shared_ingest, "ingest_document", forbidden("db"))
    monkeypatch.setattr(shared_ingest, "_get_openai_client", forbidden("embedding"))
    monkeypatch.setattr(shared_ingest, "_embed_batch_verified", forbidden("embedding"))
    monkeypatch.setattr(propositions, "extract_propositions", forbidden("generation"))
    monkeypatch.setattr(propositions, "_get_groq", forbidden("generation"))
    monkeypatch.setattr(ingest_magazine, "extract_bible_references", lambda _text: [])
    monkeypatch.setattr(ingest_magazine.shutil, "move", forbidden("move"))
    monkeypatch.setattr(ingest_magazine.shutil, "rmtree", forbidden("move"))

    stats = ingest_magazine.ingest_reviewed_issue(
        run.issue_dir, run.artifact_dir, dry_run=True
    )
    proposition_texts = tuple(
        text
        for article in stats["preview_articles"]
        for text in article["proposition_texts"]
    )
    return DryIngestPreview(
        proposition_texts=proposition_texts,
        stats=stats,
        db_calls=boundary_calls["db"],
        embedding_calls=boundary_calls["embedding"],
        generation_calls=boundary_calls["generation"],
        move_calls=boundary_calls["move"],
    )


def test_clean_issue_approves_and_dry_ingest_matches_exact_propositions(
    tmp_path: Path, monkeypatch
) -> None:
    """Regeneration, partial review, or a write-bearing preview must fail."""
    run = _run_fixture("clean_issue", tmp_path, monkeypatch)

    expected = run.fixture["expected"]

    assert run.decision.state == expected["state"]
    assert run.decision.totals == {
        "pages": expected["page_count"],
        "articles": expected["article_count"],
        "propositions": expected["proposition_count"],
    }
    assert len(run.decision.approved_propositions) == expected["eligible_article_count"]
    assert run.decision.cost_usd == pytest.approx(expected["cost_usd"])
    assert run.calls == ExternalCalls(
        initial_ocr=2,
        page_review=2,
        repair_ocr=0,
        article_model=2,
        proposition_extraction=1,
        proposition_review=1,
    )
    source_before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(run.issue_dir.iterdir())
    }

    preview = _preview_ingest(run, monkeypatch)

    assert preview.stats == expected["dry_ingest"]["result"]
    assert preview.stats["preview_articles"] == [
        {
            "article_id": "grace-for-the-journey",
            "article_hash": hashlib.sha256(
                run.fixture["article_review"]["segmentation"]["articles"][0][
                    "text"
                ].encode("utf-8")
            ).hexdigest(),
            "proposition_texts": [
                "Ada North teaches that grace is received by faith, not earned by effort.",
                "Ada North teaches that grace received from God should form humble, generous service to neighbors.",
            ],
        }
    ]
    assert preview.proposition_texts == (
        "Ada North teaches that grace is received by faith, not earned by effort.",
        "Ada North teaches that grace received from God should form humble, generous service to neighbors.",
    )
    assert preview.db_calls == expected["dry_ingest"]["db_calls"]
    assert preview.embedding_calls == expected["dry_ingest"]["embedding_calls"]
    assert preview.generation_calls == expected["dry_ingest"]["generation_calls"]
    assert preview.move_calls == expected["dry_ingest"]["move_calls"]
    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(run.issue_dir.iterdir())
    } == source_before


def test_unrepaired_ocr_failure_blocks_entire_issue(
    tmp_path: Path, monkeypatch
) -> None:
    """One failed repair must make every downstream article ineligible."""
    run = _run_fixture("ocr_failure_issue", tmp_path, monkeypatch)

    expected = run.fixture["expected"]

    assert run.decision.state == expected["state"]
    assert run.decision.reasons == tuple(expected["quarantine_reasons"])
    assert run.decision.totals == {
        "pages": expected["page_count"],
        "articles": expected["article_count"],
        "propositions": expected["proposition_count"],
    }
    assert run.decision.approved_propositions == ()
    assert len(run.decision.approved_propositions) == expected["eligible_article_count"]
    assert run.decision.cost_usd == pytest.approx(expected["cost_usd"])
    assert run.calls == ExternalCalls(
        initial_ocr=1,
        page_review=2,
        repair_ocr=1,
        article_model=0,
        proposition_extraction=0,
        proposition_review=0,
    )
    assert (
        run.calls.article_model
        + run.calls.proposition_extraction
        + run.calls.proposition_review
    ) == expected["downstream_calls"]


def test_fixture_image_tamper_is_refused_before_review(tmp_path: Path) -> None:
    """Changing fixture image bytes without its hash must stop before OCR."""
    fixture = copy.deepcopy(_load_fixture("clean_issue"))
    issue_dir = tmp_path / "tampered-image"
    pdf_path = _build_pdf(issue_dir, fixture)
    fixture["pages"][0]["image_bytes_base64"] = base64.b64encode(
        b"tampered-rendered-page"
    ).decode("ascii")

    with pytest.raises(AssertionError, match="fixture_image_hash_mismatch"):
        _fixture_rendered_pages(
            pdf_path,
            hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
            fixture["pages"],
        )
