#!/usr/bin/env python3
"""Fail-closed contracts for resumable New Wine review artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from magazine_review.artifacts import load_valid_artifact, write_artifact
from magazine_review.schemas import (
    ApprovedPropositionSet,
    ArticleManifest,
    ArticleRecord,
    ArtifactValidationError,
    IssueArtifacts,
    IssueDecision,
    OCRManifest,
    OCRPage,
    PropositionEvidence,
    PropositionReview,
    StageIdentity,
)


ARTICLE_TEXT = "The author teaches grace. Faith receives the gift."


def sha(char: str) -> str:
    return char * 64


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def valid_identity() -> StageIdentity:
    return StageIdentity(
        schema_version=1,
        input_hashes={"issue.pdf": sha("a")},
        model="openai/gpt-oss-120b",
        prompt_fingerprint=sha("b"),
        renderer_settings={"dpi": 300, "colorspace": "RGB"},
    )


@pytest.fixture
def valid_issue_artifacts() -> IssueArtifacts:
    identity = valid_identity()
    ocr = OCRManifest(
        identity=identity,
        pdf_hash=sha("a"),
        page_count=1,
        pages=(
            OCRPage(
                page_number=1,
                image_hash=sha("c"),
                initial_text=ARTICLE_TEXT,
                initial_text_hash=text_hash(ARTICLE_TEXT),
                initial_provider="Gemini",
                initial_model="gemini-3.6-flash",
                initial_prompt_fingerprint=sha("f"),
                initial_usage={"input_tokens": 1},
                initial_cost_usd=0.01,
                initial_timestamp="2026-08-25T00:00:00Z",
                reviewer_model="gemini-3.6-flash",
                reviewer_prompt_fingerprint=sha("a"),
                reviewer_complete=True,
                reviewer_reasons=(),
                reviewer_usage={"input_tokens": 1},
                reviewer_cost_usd=0.01,
                reviewer_timestamp="2026-08-25T00:00:01Z",
                repaired_text=None,
                repaired_text_hash=None,
                repair_provider=None,
                repair_model=None,
                repair_prompt_fingerprint=None,
                repair_usage=None,
                repair_cost_usd=None,
                repair_timestamp=None,
                text=ARTICLE_TEXT,
                final_text_hash=text_hash(ARTICLE_TEXT),
                transcript_start=0,
                transcript_end=len(ARTICLE_TEXT),
            ),
        ),
        usage={"input_tokens": 2},
        cost_usd=0.02,
    )
    article = ArticleRecord(
        article_id="a1",
        filename="grace.txt",
        title="Grace",
        author="New Wine",
        source_pages=(1,),
        transcript_start=0,
        transcript_end=len(ARTICLE_TEXT),
        text=ARTICLE_TEXT,
        text_hash=text_hash(ARTICLE_TEXT),
        start_coherent=True,
        end_coherent=True,
        transitions_ok=True,
        omissions=(),
        duplications=(),
        adjacent_bleed=(),
        attribution_ok=True,
        verdict=True,
    )
    articles = ArticleManifest(
        identity=identity,
        issue_hash=sha("a"),
        ocr_artifact_hash=sha("b"),
        transcript=ARTICLE_TEXT,
        articles=(article,),
        segmentation_model="openai/gpt-oss-120b",
        segmentation_prompt_fingerprint=sha("c"),
        segmentation_usage={"input_tokens": 1},
        segmentation_cost_usd=0.01,
        reviewer_model="openai/gpt-oss-120b",
        reviewer_prompt_fingerprint=sha("d"),
        reviewer_usage={"input_tokens": 1},
        reviewer_cost_usd=0.01,
    )
    proposition = PropositionEvidence(
        proposition_index=1,
        content="The author teaches grace.",
        evidence_text="The author teaches grace.",
        evidence_start=0,
        evidence_end=len("The author teaches grace."),
        supported=True,
        missing_qualification=False,
        overstatement=False,
        attribution_ok=True,
        reviewer_reasons=(),
    )
    review = PropositionReview(
        identity=identity,
        article_id="a1",
        article_hash=article.article_hash,
        article_artifact_hash=sha("e"),
        model="openai/gpt-oss-120b",
        prompt_version="v3.1",
        prompt_fingerprint=sha("b"),
        extraction_usage={"input_tokens": 1},
        extraction_cost_usd=0.01,
        grounding_totals={
            "found": 0,
            "grounded": 0,
            "stripped_fabricated": 0,
            "stripped_uncertain": 0,
            "kept_arbitration": 0,
        },
        reviewer_model="openai/gpt-oss-120b",
        reviewer_prompt_fingerprint=sha("f"),
        reviewer_usage={"input_tokens": 1},
        reviewer_cost_usd=0.01,
        article_text=ARTICLE_TEXT,
        propositions=(proposition,),
    )
    return IssueArtifacts(
        ocr=ocr,
        articles=articles,
        proposition_reviews=(review,),
        ocr_artifact_hash=sha("b"),
        article_artifact_hash=sha("e"),
        proposition_artifact_hashes={"a1": sha("a")},
    )


def mutate(artifacts: IssueArtifacts, mutation: str) -> IssueArtifacts:
    if mutation == "missing_page":
        return replace(artifacts, ocr=replace(artifacts.ocr, pages=()))
    if mutation == "second_repair":
        page = replace(artifacts.ocr.pages[0], repair_attempts=2)
        return replace(artifacts, ocr=replace(artifacts.ocr, pages=(page,)))
    if mutation == "bad_article_span":
        article = replace(artifacts.articles.articles[0], transcript_end=999)
        return replace(artifacts, articles=replace(artifacts.articles, articles=(article,)))
    if mutation == "bad_evidence_offset":
        evidence = replace(artifacts.proposition_reviews[0].propositions[0], evidence_start=1)
        review = replace(artifacts.proposition_reviews[0], propositions=(evidence,))
        return replace(artifacts, proposition_reviews=(review,))
    if mutation == "noncontiguous_proposition_index":
        evidence = replace(artifacts.proposition_reviews[0].propositions[0], proposition_index=2)
        review = replace(artifacts.proposition_reviews[0], propositions=(evidence,))
        return replace(artifacts, proposition_reviews=(review,))
    if mutation == "unsupported_proposition":
        evidence = replace(artifacts.proposition_reviews[0].propositions[0], supported=False)
        review = replace(artifacts.proposition_reviews[0], propositions=(evidence,))
        return replace(artifacts, proposition_reviews=(review,))
    raise AssertionError(f"unknown mutation: {mutation}")


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_page",
        "second_repair",
        "bad_article_span",
        "bad_evidence_offset",
        "noncontiguous_proposition_index",
        "unsupported_proposition",
    ],
)
def test_invalid_evidence_cannot_approve(valid_issue_artifacts, mutation):
    """Removing any evidence control must prevent an approved issue decision."""
    damaged = mutate(valid_issue_artifacts, mutation)

    with pytest.raises(ArtifactValidationError):
        IssueDecision.approve(damaged)


def test_artifact_round_trip_requires_matching_stage_identity(tmp_path, valid_issue_artifacts):
    """A cached artifact for different immutable inputs must never resume."""
    path = tmp_path / "issue-decision.json"
    approved = IssueDecision.approve(valid_issue_artifacts)

    write_artifact(path, approved)

    assert load_valid_artifact(path, valid_identity()) == approved
    stale_identity = replace(valid_identity(), model="different-model")
    with pytest.raises(ArtifactValidationError, match="artifact_identity_mismatch"):
        load_valid_artifact(path, stale_identity)


def test_article_filename_round_trips_and_remains_unique(valid_issue_artifacts):
    """A reloaded manifest must retain and revalidate canonical output filenames."""
    manifest = valid_issue_artifacts.articles
    reloaded = ArticleManifest.from_dict(manifest.to_dict())

    assert reloaded.articles[0].filename == "grace.txt"
    assert reloaded.articles[0].failure_reasons == {}
    duplicate = replace(reloaded.articles[0], article_id="a2")
    with pytest.raises(ArtifactValidationError, match="article_filename_duplicate"):
        replace(reloaded, articles=(reloaded.articles[0], duplicate)).validate()
    with pytest.raises(ArtifactValidationError, match="article_filename_invalid"):
        replace(reloaded.articles[0], filename="../Grace.txt").validate(manifest.transcript)


def test_write_reopens_and_detects_corrupted_artifact(tmp_path, valid_issue_artifacts):
    """A partial or modified direct write is never accepted as a resume artifact."""
    path = tmp_path / "issue-decision.json"
    write_artifact(path, IssueDecision.approve(valid_issue_artifacts))
    path.write_text('{"artifact_type":"IssueDecision"}', encoding="utf-8")

    with pytest.raises(ArtifactValidationError, match="artifact_envelope_invalid"):
        load_valid_artifact(path, valid_identity())


def test_proposition_review_artifact_reopens_with_its_exact_article_context(
    tmp_path, valid_issue_artifacts
):
    """A proposition cache must retain enough source text to recheck offsets."""
    path = tmp_path / "proposition-review.json"
    review = valid_issue_artifacts.proposition_reviews[0]

    write_artifact(path, review)

    assert load_valid_artifact(path, valid_identity()) == review


def test_quarantined_proposition_review_resumes_but_cannot_be_approved(
    tmp_path, valid_issue_artifacts
):
    """A complete failed review is resumable evidence, never an approval input."""
    evidence = replace(valid_issue_artifacts.proposition_reviews[0].propositions[0], supported=False)
    review = replace(
        valid_issue_artifacts.proposition_reviews[0],
        propositions=(evidence,),
        status="quarantined",
        reasons=("proposition_not_supported",),
    )
    path = tmp_path / "quarantined-proposition-review.json"

    write_artifact(path, review)

    assert load_valid_artifact(path, valid_identity()) == review
    with pytest.raises(ArtifactValidationError, match="issue_stage_not_passed"):
        IssueDecision.approve(replace(valid_issue_artifacts, proposition_reviews=(review,)))


def test_zero_proposition_quarantine_is_durable_but_never_approvable(
    tmp_path, valid_issue_artifacts
):
    """A genuine empty extraction is resumable failure evidence, not approval."""
    review = replace(
        valid_issue_artifacts.proposition_reviews[0],
        propositions=(),
        status="quarantined",
        reasons=("article:a1:zero_propositions",),
    )
    path = tmp_path / "zero-proposition-review.json"

    write_artifact(path, review)

    assert load_valid_artifact(path, review.identity) == review
    with pytest.raises(ArtifactValidationError, match="proposition_not_supported"):
        ApprovedPropositionSet.from_review(review, sha("a"))
    with pytest.raises(ArtifactValidationError, match="propositions_required"):
        replace(review, status="passed", reasons=()).validate()
    with pytest.raises(ArtifactValidationError, match="propositions_required"):
        replace(review, reasons=("article:a1:different_reason",)).validate()


def test_proposition_grounding_totals_are_exact_and_reconciled(valid_issue_artifacts):
    """Grounding audit counts cannot be hidden in token usage or fail to add up."""
    review = replace(
        valid_issue_artifacts.proposition_reviews[0],
        grounding_totals={
            "found": 3,
            "grounded": 1,
            "stripped_fabricated": 1,
            "stripped_uncertain": 0,
            "kept_arbitration": 1,
        },
    )

    PropositionReview.from_dict(review.to_dict()).validate()
    assert review.extraction_usage == {"input_tokens": 1}
    with pytest.raises(ArtifactValidationError, match="proposition_grounding_totals_invalid"):
        replace(review, grounding_totals={**review.grounding_totals, "found": 4}).validate()


def test_approved_proposition_set_preserves_order_and_requires_provenance(
    valid_issue_artifacts,
):
    """Ingestion receives only exact reviewed proposition content and provenance."""
    review = valid_issue_artifacts.proposition_reviews[0]
    approved = ApprovedPropositionSet.from_review(review, sha("a"))

    assert approved.propositions == ((1, "The author teaches grace."),)
    with pytest.raises(ArtifactValidationError, match="approved_model_required"):
        replace(approved, model="").validate()


def test_predecessor_links_allow_distinct_stage_identities(valid_issue_artifacts):
    """Each provider stage has its own identity; hashes, not equality, link it."""
    article_identity = replace(valid_identity(), model="article-model", prompt_fingerprint=sha("d"))
    proposition_identity = replace(
        valid_identity(), model="proposition-model", prompt_fingerprint=sha("e")
    )
    articles = replace(valid_issue_artifacts.articles, identity=article_identity)
    review = replace(valid_issue_artifacts.proposition_reviews[0], identity=proposition_identity)

    decision = IssueDecision.approve(
        replace(valid_issue_artifacts, articles=articles, proposition_reviews=(review,))
    )

    assert decision.state == "approved"


def test_deserialization_rejects_missing_approval_field(valid_issue_artifacts):
    """A missing page verdict must not silently default to passing."""
    raw = valid_issue_artifacts.ocr.pages[0].to_dict()
    del raw["complete"]

    with pytest.raises(ArtifactValidationError, match="ocr_page_invalid"):
        OCRPage.from_dict(raw)


def test_durable_ocr_record_includes_initial_and_repair_audit_evidence(
    valid_issue_artifacts,
):
    """An OCR page artifact must retain evidence sufficient for audit."""
    raw = valid_issue_artifacts.ocr.pages[0].to_dict()

    assert {
        "initial_text",
        "initial_text_hash",
        "initial_provider",
        "initial_model",
        "reviewer_model",
        "reviewer_complete",
        "repaired_text",
        "final_text_hash",
        "initial_usage",
        "initial_cost_usd",
        "reviewer_usage",
        "reviewer_cost_usd",
    }.issubset(raw)


def test_duplicate_proposition_reviews_cannot_approve(valid_issue_artifacts):
    """Set reconciliation cannot conceal two reviews for one article."""
    duplicated = replace(
        valid_issue_artifacts,
        proposition_reviews=(
            valid_issue_artifacts.proposition_reviews[0],
            valid_issue_artifacts.proposition_reviews[0],
        ),
    )

    with pytest.raises(ArtifactValidationError, match="proposition_review_duplicate"):
        IssueDecision.approve(duplicated)


def test_quarantined_review_cannot_be_converted_to_approved_set(valid_issue_artifacts):
    """Only a fully passing semantic review may enter the ingestion transport."""
    evidence = replace(valid_issue_artifacts.proposition_reviews[0].propositions[0], supported=False)
    review = replace(
        valid_issue_artifacts.proposition_reviews[0],
        propositions=(evidence,),
        status="quarantined",
    )

    with pytest.raises(ArtifactValidationError, match="proposition_not_supported"):
        ApprovedPropositionSet.from_review(review, sha("a"))


def test_article_source_pages_must_exist_in_ocr_manifest(valid_issue_artifacts):
    """An article cannot cite a page absent from the verified OCR manifest."""
    article = replace(valid_issue_artifacts.articles.articles[0], source_pages=(2,))
    artifacts = replace(
        valid_issue_artifacts,
        articles=replace(valid_issue_artifacts.articles, articles=(article,)),
    )

    with pytest.raises(ArtifactValidationError, match="article_source_page_missing"):
        IssueDecision.approve(artifacts)


def test_failed_article_verdict_cannot_hide_inside_a_passing_manifest(
    valid_issue_artifacts,
):
    """Structured coherence findings must contribute to the issue gate."""
    article = replace(
        valid_issue_artifacts.articles.articles[0],
        end_coherent=False,
        verdict=False,
        failure_reasons={"end_coherent": "ending_mid_thought"},
        reasons=("ending_mid_thought",),
    )
    artifacts = replace(
        valid_issue_artifacts,
        articles=replace(valid_issue_artifacts.articles, articles=(article,)),
    )

    with pytest.raises(ArtifactValidationError, match="article_verdict_failed"):
        IssueDecision.approve(artifacts)


def test_approved_issue_requires_every_recorded_gate_to_pass(valid_issue_artifacts):
    """Issue-level accounting cannot label a failed gate as approved."""
    decision = IssueDecision.approve(valid_issue_artifacts)

    with pytest.raises(ArtifactValidationError, match="issue_gate_failed"):
        replace(decision, gate_results={"ocr": True, "articles": False, "propositions": True}).validate()


def test_unrepaired_final_ocr_text_must_equal_initial_evidence(valid_issue_artifacts):
    """A page without a repair cannot silently substitute a different final text."""
    page = valid_issue_artifacts.ocr.pages[0]
    altered_text = "The author teaches mercy. Faith receives the gift."
    tampered = replace(page, text=altered_text, final_text_hash=text_hash(altered_text))

    with pytest.raises(ArtifactValidationError, match="final_ocr_provenance_mismatch"):
        tampered.validate()


def test_repaired_final_ocr_text_must_equal_repair_evidence(valid_issue_artifacts):
    """A repaired page must carry its repair output—not an unrelated final text."""
    page = valid_issue_artifacts.ocr.pages[0]
    repaired_text = "The author teaches mercy. Faith receives the gift."
    repaired = replace(
        page,
        repair_attempts=1,
        repaired_text=repaired_text,
        repaired_text_hash=text_hash(repaired_text),
        repair_provider="Gemini",
        repair_model="gemini-3.6-flash",
        repair_prompt_fingerprint=sha("a"),
        repair_usage={"input_tokens": 1},
        repair_cost_usd=0.01,
        repair_timestamp="2026-08-25T00:00:02Z",
    )

    with pytest.raises(ArtifactValidationError, match="final_ocr_provenance_mismatch"):
        repaired.validate()


def test_approved_decision_reconciles_totals_and_artifact_keys(valid_issue_artifacts):
    """Approval accounting must correspond exactly to the transport sets."""
    decision = IssueDecision.approve(valid_issue_artifacts)

    with pytest.raises(ArtifactValidationError, match="issue_totals_mismatch"):
        replace(decision, totals={"pages": 1, "articles": 2, "propositions": 1}).validate()
    with pytest.raises(ArtifactValidationError, match="proposition_artifact_reconciliation_failed"):
        replace(decision, proposition_artifact_hashes={"a1": sha("a"), "extra": sha("b")}).validate()


def test_approved_decision_reconciles_article_hashes(valid_issue_artifacts):
    """The persisted decision cannot claim a different approved article hash."""
    decision = IssueDecision.approve(valid_issue_artifacts)

    with pytest.raises(ArtifactValidationError, match="approved_article_hash_mismatch"):
        replace(decision, article_hashes={"a1": sha("c")}).validate()


def test_approved_decision_binds_each_article_to_its_proposition_artifact(
    valid_issue_artifacts,
):
    """A valid-looking hash for the same article ID cannot swap review evidence."""
    decision = IssueDecision.approve(valid_issue_artifacts)

    with pytest.raises(ArtifactValidationError, match="approved_proposition_artifact_hash_mismatch"):
        replace(decision, proposition_artifact_hashes={"a1": sha("b")}).validate()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
