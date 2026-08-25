#!/usr/bin/env python3
"""Fail-closed orchestration tests for one reviewed magazine issue."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import fitz
import pytest

import review_magazine_issue as runner
from magazine_review.articles import _stage_identity as article_stage_identity
from magazine_review.artifacts import write_artifact
from magazine_review.benchmark import BenchmarkCandidate
from magazine_review.ocr import OCRReviewConfig, VerifiedIssueTranscript
from magazine_review.schemas import (
    ArticleManifest,
    ArticleRecord,
    OCRManifest,
    OCRPage,
    PropositionEvidence,
    PropositionReview,
    StageIdentity,
)


TEXT = "Ada North teaches that grace is received by faith."


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class NoCallOCR:
    def __init__(self, candidate: BenchmarkCandidate) -> None:
        self.candidate = candidate
        self.calls = 0

    def transcribe(self, fixture):
        self.calls += 1
        raise AssertionError("unexpected OCR provider call")


class NoCallPageReviewer:
    model = "gemini-3.6-flash"

    def __init__(self) -> None:
        self.calls = 0

    def review(self, page, text, instructions):
        self.calls += 1
        raise AssertionError("unexpected page reviewer call")


class NoCallStructuredClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        raise AssertionError("unexpected structured provider call")


@pytest.fixture
def one_page_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "NewWineMagazine_Issue_02-1974.pdf"
    document = fitz.open()
    page = document.new_page(width=288, height=432)
    page.insert_text((36, 72), TEXT)
    document.save(path)
    document.close()
    return path


def accepted_decision(pdf_path: Path) -> runner.AcceptedBenchmarkDecision:
    return runner.AcceptedBenchmarkDecision(
        name="new-wine-ocr-benchmark-2026-08-25",
        issue_filename=pdf_path.name,
        issue_pdf_sha256=hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        accepted_candidate=BenchmarkCandidate("accepted-provider", "accepted-model"),
        benchmark_report_sha256=digest("reviewed-blind-report"),
        decision_sha256=digest("accepted-decision"),
    )


def review_config(pdf_path: Path) -> runner.ReviewIssueConfig:
    decision = accepted_decision(pdf_path)
    initial = NoCallOCR(decision.accepted_candidate)
    repair = NoCallOCR(BenchmarkCandidate("Gemini", "gemini-3.6-flash"))
    return runner.ReviewIssueConfig(
        benchmark_decision=decision,
        ocr=OCRReviewConfig(
            accepted_candidate=decision.accepted_candidate,
            benchmark_decision_hash=decision.decision_sha256,
            initial_provider=initial,
            reviewer=NoCallPageReviewer(),
            repair_provider=repair,
        ),
        article_client=NoCallStructuredClient(),
        proposition_reviewer=NoCallStructuredClient(),
        proposition_extractor=lambda **_: (_ for _ in ()).throw(
            AssertionError("unexpected proposition extractor call")
        ),
        proposition_extractor_model="openai/gpt-oss-120b",
    )


def stage_identity(pdf_hash: str) -> StageIdentity:
    return StageIdentity(
        schema_version=1,
        input_hashes={"issue.pdf": pdf_hash},
        model="test-model",
        prompt_fingerprint=digest("prompt"),
        renderer_settings={},
    )


def passing_ocr(pdf_path: Path) -> OCRManifest:
    pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    return OCRManifest(
        identity=stage_identity(pdf_hash),
        pdf_hash=pdf_hash,
        page_count=1,
        pages=(
            OCRPage(
                page_number=1,
                image_hash=digest("image"),
                initial_text=TEXT,
                initial_text_hash=digest(TEXT),
                initial_provider="accepted-provider",
                initial_model="accepted-model",
                initial_prompt_fingerprint=digest("initial-prompt"),
                initial_usage={"input_tokens": 10, "output_tokens": 4},
                initial_cost_usd=0.1,
                initial_timestamp="2026-08-25T00:00:00Z",
                reviewer_model="gemini-3.6-flash",
                reviewer_prompt_fingerprint=digest("review-prompt"),
                reviewer_complete=True,
                reviewer_reasons=(),
                reviewer_usage={"input_tokens": 3, "output_tokens": 1},
                reviewer_cost_usd=0.02,
                reviewer_timestamp="2026-08-25T00:00:01Z",
                repaired_text=None,
                repaired_text_hash=None,
                repair_provider=None,
                repair_model=None,
                repair_prompt_fingerprint=None,
                repair_usage=None,
                repair_cost_usd=None,
                repair_timestamp=None,
                text=TEXT,
                final_text_hash=digest(TEXT),
                transcript_start=0,
                transcript_end=len(TEXT),
            ),
        ),
        usage={"input_tokens": 13, "output_tokens": 5},
        cost_usd=0.12,
    )


def passing_articles(ocr: OCRManifest) -> ArticleManifest:
    transcript = VerifiedIssueTranscript.from_manifest(ocr)
    start = transcript.text.index(TEXT)
    article = ArticleRecord(
        article_id="a1",
        filename="grace-by-faith.txt",
        title="Grace by Faith",
        author="Ada North",
        source_pages=(1,),
        transcript_start=start,
        transcript_end=start + len(TEXT),
        text=TEXT,
        text_hash=digest(TEXT),
        start_coherent=True,
        end_coherent=True,
        transitions_ok=True,
        omissions=(),
        duplications=(),
        adjacent_bleed=(),
        attribution_ok=True,
        verdict=True,
    )
    transcript_hash = digest(transcript.text)
    return ArticleManifest(
        identity=article_stage_identity(transcript, transcript_hash),
        issue_hash=transcript_hash,
        ocr_artifact_hash=transcript.ocr_identity,
        transcript=transcript.text,
        articles=(article,),
        segmentation_model="openai/gpt-oss-120b",
        segmentation_prompt_fingerprint=runner.article_config_fingerprint("segmentation"),
        segmentation_usage={"input_tokens": 20, "output_tokens": 8},
        segmentation_cost_usd=0.2,
        reviewer_model="openai/gpt-oss-120b",
        reviewer_prompt_fingerprint=runner.article_config_fingerprint("review"),
        reviewer_usage={"input_tokens": 15, "output_tokens": 5},
        reviewer_cost_usd=0.15,
    )


def passing_proposition(article_manifest: ArticleManifest) -> PropositionReview:
    article = article_manifest.articles[0]
    evidence_text = "grace is received by faith"
    start = article.text.index(evidence_text)
    return PropositionReview(
        identity=stage_identity(article.article_hash),
        article_id=article.article_id,
        article_hash=article.article_hash,
        article_artifact_hash=digest("article-artifact"),
        model="openai/gpt-oss-120b",
        prompt_version="v3.1",
        prompt_fingerprint=runner.proposition_prompt_fingerprint("v3.1"),
        extraction_usage={"input_tokens": 7, "output_tokens": 3},
        extraction_cost_usd=0.03,
        extraction_cost_basis={
            "type": "provider_reported",
            "model": "openai/gpt-oss-120b",
            "currency": "USD",
        },
        reviewer_model="openai/gpt-oss-120b",
        reviewer_prompt_fingerprint=runner.PROPOSITION_REVIEW_PROMPT_FINGERPRINT,
        reviewer_usage={"input_tokens": 6, "output_tokens": 2},
        reviewer_cost_usd=0.04,
        article_text=article.text,
        propositions=(
            PropositionEvidence(
                proposition_index=1,
                content="Ada North teaches that grace is received by faith.",
                evidence_text=evidence_text,
                evidence_start=start,
                evidence_end=start + len(evidence_text),
                evidence_offset_exact=True,
                supported=True,
                missing_qualification=False,
                overstatement=False,
                attribution_ok=True,
                reviewer_reasons=(),
            ),
        ),
        grounding_totals={
            "found": 0,
            "grounded": 0,
            "stripped_fabricated": 0,
            "stripped_uncertain": 0,
            "kept_arbitration": 0,
        },
    )


def install_passing_stages(monkeypatch, pdf_path: Path):
    ocr = passing_ocr(pdf_path)
    articles = passing_articles(ocr)
    proposition = passing_proposition(articles)
    proposition = replace(proposition, article_artifact_hash=digest("article-artifact"))
    calls = {"ocr": 0, "segment": 0, "article_review": 0, "proposition": 0}

    def fake_ocr(*args, **kwargs):
        calls["ocr"] += 1
        return ocr

    def fake_segment(*args, **kwargs):
        calls["segment"] += 1
        return articles

    def fake_article_review(*args, **kwargs):
        calls["article_review"] += 1
        return articles

    def fake_proposition(one_article, reviewer, **kwargs):
        calls["proposition"] += 1
        result = replace(
            proposition, article_artifact_hash=kwargs["article_artifact_hash"]
        )
        return replace(
            result,
            identity=runner.expected_proposition_identity(
                result,
                article_hash=result.article_hash,
                article_artifact_hash=kwargs["article_artifact_hash"],
                extractor_model="openai/gpt-oss-120b",
            ),
        )

    monkeypatch.setattr(runner, "review_issue_ocr", fake_ocr)
    monkeypatch.setattr(runner, "segment_articles", fake_segment)
    monkeypatch.setattr(runner, "review_articles_against_issue", fake_article_review)
    monkeypatch.setattr(runner, "review_issue_propositions", fake_proposition)
    return ocr, articles, proposition, calls


def test_ocr_quarantine_prevents_downstream_calls(
    monkeypatch, one_page_pdf: Path, tmp_path: Path
) -> None:
    """A failed OCR gate must make article and proposition calls unreachable."""
    ocr, _, _, calls = install_passing_stages(monkeypatch, one_page_pdf)
    quarantined = replace(
        ocr,
        status="quarantined",
        quarantine_reasons=("page:1:ocr_incomplete_after_repair",),
    )
    monkeypatch.setattr(runner, "review_issue_ocr", lambda *args, **kwargs: quarantined)

    decision = runner.review_issue(one_page_pdf, tmp_path / "artifacts", review_config(one_page_pdf))

    assert decision.state == "quarantined"
    assert calls["segment"] == 0
    assert calls["proposition"] == 0
    assert decision.usage["quarantined"] == 1


def test_technical_exception_is_not_content_quarantine(
    monkeypatch, one_page_pdf: Path, tmp_path: Path
) -> None:
    """Provider timeouts must remain technical errors, never content verdicts."""
    _, _, _, calls = install_passing_stages(monkeypatch, one_page_pdf)

    def timeout(*args, **kwargs):
        raise TimeoutError("provider timeout")

    monkeypatch.setattr(runner, "review_issue_ocr", timeout)

    decision = runner.review_issue(one_page_pdf, tmp_path / "artifacts", review_config(one_page_pdf))

    assert decision.state == "pipeline_error"
    assert decision.reasons == ("ocr:TimeoutError:provider timeout",)
    assert calls["segment"] == 0
    assert calls["proposition"] == 0
    assert decision.usage["errored"] == 1


def test_article_and_proposition_quarantines_stop_immediately(
    monkeypatch, one_page_pdf: Path, tmp_path: Path
) -> None:
    """Either downstream semantic gate must prevent every later review unit."""
    ocr, articles, proposition, calls = install_passing_stages(monkeypatch, one_page_pdf)
    bad_article = replace(
        articles.articles[0],
        end_coherent=False,
        verdict=False,
        failure_reasons={"end_coherent": "ending_mid_thought"},
        reasons=("ending_mid_thought",),
    )
    quarantined_articles = replace(
        articles,
        articles=(bad_article,),
        status="quarantined",
        quarantine_reasons=("ending_mid_thought",),
    )
    monkeypatch.setattr(
        runner, "review_articles_against_issue", lambda *args, **kwargs: quarantined_articles
    )

    article_decision = runner.review_issue(
        one_page_pdf, tmp_path / "article-quarantine", review_config(one_page_pdf)
    )
    assert article_decision.state == "quarantined"
    assert calls["proposition"] == 0

    install_passing_stages(monkeypatch, one_page_pdf)
    bad_evidence = replace(proposition.propositions[0], supported=False)
    bad_proposition = replace(
        proposition,
        propositions=(bad_evidence,),
        status="quarantined",
        reasons=("article:a1:proposition:1:unsupported",),
    )
    def quarantined_proposition(one_article, reviewer, **kwargs):
        result = replace(
            bad_proposition, article_artifact_hash=kwargs["article_artifact_hash"]
        )
        return replace(
            result,
            identity=runner.expected_proposition_identity(
                result,
                article_hash=result.article_hash,
                article_artifact_hash=kwargs["article_artifact_hash"],
                extractor_model="openai/gpt-oss-120b",
            ),
        )

    monkeypatch.setattr(
        runner, "review_issue_propositions", quarantined_proposition
    )
    proposition_decision = runner.review_issue(
        one_page_pdf, tmp_path / "proposition-quarantine", review_config(one_page_pdf)
    )
    assert proposition_decision.state == "quarantined"
    assert proposition_decision.gate_results == {
        "ocr": True,
        "articles": True,
        "propositions": False,
    }


def test_clean_approval_reconciles_all_counts_usage_and_cost(
    monkeypatch, one_page_pdf: Path, tmp_path: Path
) -> None:
    """Dropping any reviewed unit or stage accounting must break this literal total."""
    install_passing_stages(monkeypatch, one_page_pdf)

    decision = runner.review_issue(one_page_pdf, tmp_path / "artifacts", review_config(one_page_pdf))

    assert decision.state == "approved"
    assert decision.totals == {"pages": 1, "articles": 1, "propositions": 1}
    assert decision.usage == {
        "ocr": 18,
        "article_segmentation": 28,
        "article_review": 20,
        "proposition_extraction": 10,
        "proposition_review": 8,
        "attempted": 3,
        "passed": 3,
        "repaired": 0,
        "quarantined": 0,
        "errored": 0,
    }
    assert decision.cost_usd == pytest.approx(0.54)
    assert len(decision.approved_propositions) == 1


def test_matching_article_and_proposition_artifacts_resume_without_calls(
    monkeypatch, one_page_pdf: Path, tmp_path: Path
) -> None:
    """A complete matching cache must resume rather than repeat paid model stages."""
    _, _, _, calls = install_passing_stages(monkeypatch, one_page_pdf)
    artifact_dir = tmp_path / "artifacts"
    first = runner.review_issue(one_page_pdf, artifact_dir, review_config(one_page_pdf))
    assert first.state == "approved"
    assert calls["segment"] == 1
    assert calls["article_review"] == 1
    assert calls["proposition"] == 1

    second = runner.review_issue(one_page_pdf, artifact_dir, review_config(one_page_pdf))

    assert second.state == "approved"
    assert calls["segment"] == 1
    assert calls["article_review"] == 1
    assert calls["proposition"] == 1


def test_named_accepted_decision_is_exact_and_binds_one_pdf(
    one_page_pdf: Path, tmp_path: Path
) -> None:
    """A decision for a different filename or bytes must fail before adapter setup."""
    decision_path = tmp_path / "accepted-decision.json"
    raw = {
        "schema_version": 1,
        "decision_name": "new-wine-ocr-benchmark-2026-08-25",
        "state": "accepted",
        "issue": {
            "filename": one_page_pdf.name,
            "pdf_sha256": hashlib.sha256(one_page_pdf.read_bytes()).hexdigest(),
        },
        "accepted_candidate": {"provider": "accepted-provider", "model": "accepted-model"},
        "benchmark_report_sha256": digest("reviewed-blind-report"),
    }
    decision_path.write_text(json.dumps(raw), encoding="utf-8")
    decision = runner.load_accepted_benchmark_decision(decision_path)
    runner.validate_named_issue(one_page_pdf, decision)

    wrong = replace(decision, issue_filename="different.pdf")
    with pytest.raises(runner.IssueReviewConfigurationError, match="issue_filename_mismatch"):
        runner.validate_named_issue(one_page_pdf, wrong)
    with pytest.raises(runner.IssueReviewConfigurationError, match="benchmark_decision_invalid"):
        decision_path.write_text(json.dumps({**raw, "extra": True}), encoding="utf-8")
        runner.load_accepted_benchmark_decision(decision_path)


def test_cli_requires_named_inputs_and_fails_before_calls_without_adapter_factory(
    one_page_pdf: Path, tmp_path: Path, capsys
) -> None:
    """The real CLI cannot depend on an undiscoverable injected Python object."""
    decision_path = tmp_path / "accepted-decision.json"
    decision_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "decision_name": "accepted-one-issue",
                "state": "accepted",
                "issue": {
                    "filename": one_page_pdf.name,
                    "pdf_sha256": hashlib.sha256(one_page_pdf.read_bytes()).hexdigest(),
                },
                "accepted_candidate": {
                    "provider": "accepted-provider",
                    "model": "accepted-model",
                },
                "benchmark_report_sha256": digest("report"),
            }
        ),
        encoding="utf-8",
    )

    exit_code = runner.main(
        [
            "--pdf",
            str(one_page_pdf),
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--benchmark-decision",
            str(decision_path),
        ],
        environ={},
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output["state"] == "pipeline_error"
    assert output["reason"] == "provider_adapter_factory_required"
    assert "apply" not in runner.build_parser().format_help().lower()
    assert "database" not in runner.build_parser().format_help().lower()


def test_cli_factory_cannot_substitute_a_different_accepted_decision(
    one_page_pdf: Path, tmp_path: Path, capsys
) -> None:
    """Factory construction must not replace the explicitly named human decision."""
    decision_path = tmp_path / "accepted-decision.json"
    decision_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "decision_name": "accepted-one-issue",
                "state": "accepted",
                "issue": {
                    "filename": one_page_pdf.name,
                    "pdf_sha256": hashlib.sha256(one_page_pdf.read_bytes()).hexdigest(),
                },
                "accepted_candidate": {
                    "provider": "accepted-provider",
                    "model": "accepted-model",
                },
                "benchmark_report_sha256": digest("report"),
            }
        ),
        encoding="utf-8",
    )

    def substituting_factory(decision):
        base = review_config(one_page_pdf)
        ocr = replace(
            base.ocr,
            benchmark_decision_hash=decision.decision_sha256,
        )
        return replace(
            base,
            benchmark_decision=replace(decision, name="substituted-decision"),
            ocr=ocr,
        )

    exit_code = runner.main(
        [
            "--pdf",
            str(one_page_pdf),
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--benchmark-decision",
            str(decision_path),
        ],
        adapter_factory=substituting_factory,
        environ={},
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output == {
        "state": "pipeline_error",
        "reason": "provider_factory_decision_mismatch",
    }


def decision_document(pdf_path: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "decision_name": "accepted-one-issue",
        "state": "accepted",
        "issue": {
            "filename": pdf_path.name,
            "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        },
        "accepted_candidate": {
            "provider": "accepted-provider",
            "model": "accepted-model",
        },
        "benchmark_report_sha256": digest("report"),
    }


def test_direct_script_accepts_imported_structural_provider_adapters(
    one_page_pdf: Path, tmp_path: Path
) -> None:
    """`__main__` and imported class identities must not block a valid factory."""
    decision_path = tmp_path / "accepted-decision.json"
    decision_path.write_text(json.dumps(decision_document(one_page_pdf)), encoding="utf-8")
    factory_path = tmp_path / "offline_factory.py"
    factory_path.write_text(
        """
from review_magazine_issue import ProviderAdapters
from magazine_review.benchmark import BenchmarkCandidate

class Initial:
    def __init__(self, candidate):
        self.candidate = candidate
    def transcribe(self, fixture):
        raise RuntimeError("offline_pipeline_reached")

class Repair:
    candidate = BenchmarkCandidate("Gemini", "gemini-3.6-flash")
    def transcribe(self, fixture):
        raise AssertionError("repair must not run")

class PageReviewer:
    model = "gemini-3.6-flash"
    def review(self, page, text, instructions):
        raise AssertionError("review must not run")

class Structured:
    def complete(self, request):
        raise AssertionError("structured review must not run")

def build(decision):
    return ProviderAdapters(
        initial_ocr_provider=Initial(decision.accepted_candidate),
        page_reviewer=PageReviewer(),
        repair_ocr_provider=Repair(),
        article_client=Structured(),
        proposition_reviewer=Structured(),
    )
""".lstrip(),
        encoding="utf-8",
    )
    scripts_dir = Path(__file__).parent
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((str(tmp_path), str(scripts_dir)))

    completed = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "review_magazine_issue.py"),
            "--pdf",
            str(one_page_pdf),
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--benchmark-decision",
            str(decision_path),
            "--provider-adapter-factory",
            "offline_factory:build",
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 2
    output = json.loads(completed.stdout)
    assert output["state"] == "pipeline_error"
    assert output["reasons"] == ["ocr:RuntimeError:offline_pipeline_reached"]
    assert "provider_adapter_factory_result_invalid" not in completed.stdout


@pytest.mark.parametrize("duplicate", ["--pdf", "--artifact-dir", "--benchmark-decision"])
def test_cli_rejects_duplicate_required_option(duplicate: str) -> None:
    """A repeated identity-bearing option must not silently replace its first value."""
    arguments = [
        "--pdf",
        "issue.pdf",
        "--artifact-dir",
        "artifacts",
        "--benchmark-decision",
        "decision.json",
        duplicate,
        "substitute",
    ]

    with pytest.raises(SystemExit) as exc_info:
        runner.build_parser().parse_args(arguments)

    assert exc_info.value.code == 2


def test_stale_ocr_invalidates_article_and_proposition_dependents(
    monkeypatch, one_page_pdf: Path, tmp_path: Path
) -> None:
    """A refreshed OCR identity must rerun article and proposition stages in order."""
    ocr, _, _, calls = install_passing_stages(monkeypatch, one_page_pdf)
    artifact_dir = tmp_path / "artifacts"
    first = runner.review_issue(one_page_pdf, artifact_dir, review_config(one_page_pdf))
    assert first.state == "approved"
    stale_ocr = replace(ocr, identity=replace(ocr.identity, model="stale-ocr-model"))
    write_artifact(artifact_dir / "ocr_manifest.json", stale_ocr)

    refreshed_ocr = replace(ocr, identity=replace(ocr.identity, model="refreshed-ocr-model"))
    refreshed_articles = replace(
        passing_articles(refreshed_ocr),
        reviewer_usage={"input_tokens": 16, "output_tokens": 5},
    )

    def refresh_ocr(*args, **kwargs):
        calls["ocr"] += 1
        return refreshed_ocr

    def refresh_segments(*args, **kwargs):
        calls["segment"] += 1
        return refreshed_articles

    def refresh_articles(*args, **kwargs):
        calls["article_review"] += 1
        return refreshed_articles

    monkeypatch.setattr(runner, "review_issue_ocr", refresh_ocr)
    monkeypatch.setattr(runner, "segment_articles", refresh_segments)
    monkeypatch.setattr(runner, "review_articles_against_issue", refresh_articles)

    second = runner.review_issue(one_page_pdf, artifact_dir, review_config(one_page_pdf))

    assert second.state == "approved"
    assert calls == {"ocr": 2, "segment": 2, "article_review": 2, "proposition": 2}


def test_stale_article_resumes_ocr_and_reruns_proposition_dependent(
    monkeypatch, one_page_pdf: Path, tmp_path: Path
) -> None:
    """A stale article artifact must preserve OCR and invalidate propositions."""
    _, articles, _, calls = install_passing_stages(monkeypatch, one_page_pdf)
    artifact_dir = tmp_path / "artifacts"
    first = runner.review_issue(one_page_pdf, artifact_dir, review_config(one_page_pdf))
    assert first.state == "approved"
    stale = replace(articles, identity=replace(articles.identity, model="stale-article-model"))
    write_artifact(artifact_dir / runner.ARTICLE_MANIFEST_NAME, stale)
    refreshed = replace(
        articles, reviewer_usage={"input_tokens": 16, "output_tokens": 5}
    )

    def refresh_articles(*args, **kwargs):
        calls["article_review"] += 1
        return refreshed

    monkeypatch.setattr(runner, "review_articles_against_issue", refresh_articles)

    second = runner.review_issue(one_page_pdf, artifact_dir, review_config(one_page_pdf))

    assert second.state == "approved"
    assert calls["segment"] == 2
    assert calls["article_review"] == 2
    assert calls["proposition"] == 2
    assert second.usage["ocr"] == first.usage["ocr"]


def test_stale_proposition_resumes_valid_predecessors(
    monkeypatch, one_page_pdf: Path, tmp_path: Path
) -> None:
    """Only proposition review reruns when both predecessor artifacts still match."""
    _, articles, proposition, calls = install_passing_stages(monkeypatch, one_page_pdf)
    artifact_dir = tmp_path / "artifacts"
    first = runner.review_issue(one_page_pdf, artifact_dir, review_config(one_page_pdf))
    assert first.state == "approved"
    article_hash = first.article_artifact_hash
    current = replace(proposition, article_artifact_hash=article_hash)
    current = replace(
        current,
        identity=runner.expected_proposition_identity(
            current,
            article_hash=articles.articles[0].article_hash,
            article_artifact_hash=article_hash,
            extractor_model="openai/gpt-oss-120b",
        ),
    )
    stale = replace(current, identity=replace(current.identity, model="stale-proposition-model"))
    write_artifact(runner._proposition_path(artifact_dir, "a1"), stale)

    second = runner.review_issue(one_page_pdf, artifact_dir, review_config(one_page_pdf))

    assert second.state == "approved"
    assert calls["segment"] == 1
    assert calls["article_review"] == 1
    assert calls["proposition"] == 2


def test_article_technical_exception_is_pipeline_error_and_stops_propositions(
    monkeypatch, one_page_pdf: Path, tmp_path: Path
) -> None:
    """An article provider failure is technical and cannot reach propositions."""
    _, _, _, calls = install_passing_stages(monkeypatch, one_page_pdf)

    def article_timeout(*args, **kwargs):
        raise TimeoutError("article provider timeout")

    monkeypatch.setattr(runner, "review_articles_against_issue", article_timeout)

    decision = runner.review_issue(
        one_page_pdf, tmp_path / "artifacts", review_config(one_page_pdf)
    )

    assert decision.state == "pipeline_error"
    assert decision.reasons == ("articles:TimeoutError:article provider timeout",)
    assert calls["proposition"] == 0


def test_proposition_technical_exception_is_pipeline_error(
    monkeypatch, one_page_pdf: Path, tmp_path: Path
) -> None:
    """A proposition provider failure remains distinct from unsupported content."""
    install_passing_stages(monkeypatch, one_page_pdf)

    def proposition_timeout(*args, **kwargs):
        raise TimeoutError("proposition provider timeout")

    monkeypatch.setattr(runner, "review_issue_propositions", proposition_timeout)

    decision = runner.review_issue(
        one_page_pdf, tmp_path / "artifacts", review_config(one_page_pdf)
    )

    assert decision.state == "pipeline_error"
    assert decision.reasons == (
        "propositions:TimeoutError:proposition provider timeout",
    )


def test_programmatic_identity_precondition_raises_before_provider_calls(
    one_page_pdf: Path, tmp_path: Path
) -> None:
    """Without a usable named issue identity, no pipeline decision can be created."""
    config = review_config(one_page_pdf)
    wrong_issue = replace(
        config,
        benchmark_decision=replace(
            config.benchmark_decision, issue_filename="different-issue.pdf"
        ),
    )

    with pytest.raises(runner.ReviewConfigurationError, match="issue_filename_mismatch"):
        runner.review_issue(one_page_pdf, tmp_path / "artifacts", wrong_issue)

    assert config.ocr.initial_provider.calls == 0
    assert config.ocr.reviewer.calls == 0
    assert config.article_client.calls == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
