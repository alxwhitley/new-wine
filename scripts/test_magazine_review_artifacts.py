#!/usr/bin/env python3
"""Fail-closed contracts for resumable New Wine review artifacts."""

from __future__ import annotations

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
                text=ARTICLE_TEXT,
                transcript_start=0,
                transcript_end=len(ARTICLE_TEXT),
            ),
        ),
    )
    article = ArticleRecord(
        article_id="a1",
        title="Grace",
        author="New Wine",
        source_pages=(1,),
        transcript_start=0,
        transcript_end=len(ARTICLE_TEXT),
        text=ARTICLE_TEXT,
    )
    articles = ArticleManifest(
        identity=identity,
        issue_hash=sha("a"),
        transcript=ARTICLE_TEXT,
        articles=(article,),
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
    )
    review = PropositionReview(
        identity=identity,
        article_id="a1",
        article_hash=article.article_hash,
        model="openai/gpt-oss-120b",
        prompt_version="v3.1",
        prompt_fingerprint=sha("b"),
        article_text=ARTICLE_TEXT,
        propositions=(proposition,),
    )
    return IssueArtifacts(ocr=ocr, articles=articles, proposition_reviews=(review,))


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


def test_write_reopens_and_detects_corrupted_artifact(tmp_path, valid_issue_artifacts):
    """A partial or modified direct write is never accepted as a resume artifact."""
    path = tmp_path / "issue-decision.json"
    write_artifact(path, IssueDecision.approve(valid_issue_artifacts))
    path.write_text('{"artifact_type":"IssueDecision"}', encoding="utf-8")

    with pytest.raises(ArtifactValidationError, match="artifact_payload_sha256_mismatch"):
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


def test_approved_proposition_set_preserves_order_and_requires_provenance(
    valid_issue_artifacts,
):
    """Ingestion receives only exact reviewed proposition content and provenance."""
    review = valid_issue_artifacts.proposition_reviews[0]
    approved = ApprovedPropositionSet.from_review(review)

    assert approved.propositions == ((1, "The author teaches grace."),)
    with pytest.raises(ArtifactValidationError, match="approved_model_required"):
        replace(approved, model="").validate()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
