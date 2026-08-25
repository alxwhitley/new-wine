#!/usr/bin/env python3
"""Issue-wide article segmentation and completeness review contracts."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import replace

import pytest

from magazine_review.articles import (
    ArticleReviewError,
    review_articles_against_issue,
    segment_articles,
)
from magazine_review.ocr import VerifiedIssueTranscript, VerifiedTranscriptPage


MODEL = "openai/gpt-oss-120b"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verified_transcript(*page_texts: str) -> VerifiedIssueTranscript:
    parts: list[str] = []
    pages: list[VerifiedTranscriptPage] = []
    cursor = 0
    for page_number, page_text in enumerate(page_texts, start=1):
        if parts:
            parts.append("\n\n")
            cursor += 2
        marker = f"=== PAGE {page_number} ===\n"
        parts.append(marker)
        cursor += len(marker)
        start = cursor
        parts.append(page_text)
        cursor += len(page_text)
        pages.append(
            VerifiedTranscriptPage(
                page_number=page_number,
                image_hash=digest(f"page-{page_number}"),
                transcript_start=start,
                transcript_end=cursor,
            )
        )
    return VerifiedIssueTranscript(
        text="".join(parts),
        pages=tuple(pages),
        ocr_identity=digest("ocr-artifact"),
    )


class FakeStructuredClient:
    """No-network client double that records complete structured requests."""

    def __init__(self, *responses: dict[str, object]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    @property
    def last_request(self) -> dict[str, object]:
        return self.requests[-1]

    def complete(self, request: dict[str, object]) -> dict[str, object]:
        self.requests.append(copy.deepcopy(request))
        if not self.responses:
            raise AssertionError("unexpected structured-output request")
        return copy.deepcopy(self.responses.pop(0))


@pytest.fixture
def verified_issue() -> VerifiedIssueTranscript:
    return verified_transcript(
        "FIRST LIGHT\nBy Ada North\nA complete opening develops its point.\n",
        "The thought continues and reaches a coherent conclusion.\n"
        "SECOND VOICE\nBy Ben South\nA neighboring article stands alone.",
    )


def proposed_article(
    transcript: VerifiedIssueTranscript,
    *,
    article_id: str,
    filename: str,
    title: str,
    author: str,
    source_pages: list[int],
    start_text: str,
    end_text: str,
) -> dict[str, object]:
    start = transcript.text.index(start_text)
    end = transcript.text.index(end_text, start) + len(end_text)
    return {
        "article_id": article_id,
        "filename": filename,
        "title": title,
        "author": author,
        "source_pages": source_pages,
        "transcript_start": start,
        "transcript_end": end,
        "text": transcript.text[start:end],
    }


def segmentation_response(
    transcript: VerifiedIssueTranscript,
    articles: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "output": {
            "ocr_identity": transcript.ocr_identity,
            "transcript_hash": digest(transcript.text),
            "articles": articles,
        },
        "usage": {"input_tokens": 120, "output_tokens": 35},
        "cost_usd": 0.012,
    }


def passing_review_response(transcript, articles):
    article_set_hash = digest(
        "\n".join(
            f"{article['article_id']}:{digest(str(article['text']))}" for article in articles
        )
    )
    return {
        "output": {
            "ocr_identity": transcript.ocr_identity,
            "transcript_hash": digest(transcript.text),
            "article_set_hash": article_set_hash,
            "articles": [
                {
                    "article_id": article["article_id"],
                    "start_coherent": True,
                    "end_coherent": True,
                    "transitions_ok": True,
                    "omissions": [],
                    "duplications": [],
                    "adjacent_bleed": [],
                    "attribution_ok": True,
                    "reasons": [],
                }
                for article in articles
            ],
        },
        "usage": {"input_tokens": 500, "output_tokens": 80},
        "cost_usd": 0.025,
    }


def two_proposals(transcript: VerifiedIssueTranscript) -> list[dict[str, object]]:
    return [
        proposed_article(
            transcript,
            article_id="first-light",
            filename="first-light.txt",
            title="First Light",
            author="Ada North",
            source_pages=[1, 2],
            start_text="FIRST LIGHT",
            end_text="coherent conclusion.",
        ),
        proposed_article(
            transcript,
            article_id="second-voice",
            filename="second-voice.txt",
            title="Second Voice",
            author="Ben South",
            source_pages=[2],
            start_text="SECOND VOICE",
            end_text="stands alone.",
        ),
    ]


def test_segmentation_uses_complete_issue_low_reasoning_and_strict_json(verified_issue):
    """A truncated prompt or unconstrained response could silently lose articles."""
    proposals = two_proposals(verified_issue)
    client = FakeStructuredClient(segmentation_response(verified_issue, proposals))

    manifest = segment_articles(verified_issue, client)

    request = client.last_request
    assert request["model"] == MODEL
    assert request["reasoning_effort"] == "low"
    assert request["issue_transcript"] == verified_issue.text
    assert request["pages"] == [
        {
            "page_number": page.page_number,
            "image_hash": page.image_hash,
            "transcript_start": page.transcript_start,
            "transcript_end": page.transcript_end,
        }
        for page in verified_issue.pages
    ]
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True
    assert manifest.status == "quarantined"
    assert manifest.quarantine_reasons == ("semantic_review_required",)
    assert [article.source_pages for article in manifest.articles] == [(1, 2), (2,)]


def test_reviewer_receives_complete_issue_and_all_articles(verified_issue):
    """Reviewing isolated excerpts cannot detect omissions, duplication, or bleed."""
    proposals = two_proposals(verified_issue)
    client = FakeStructuredClient(
        segmentation_response(verified_issue, proposals),
        passing_review_response(verified_issue, proposals),
    )
    segmented = segment_articles(verified_issue, client)

    reviewed = review_articles_against_issue(verified_issue, segmented, client)

    request = client.last_request
    assert request["reasoning_effort"] == "medium"
    assert request["issue_transcript"] == verified_issue.text
    assert len(request["articles"]) == 2
    assert [item["text"] for item in request["articles"]] == [
        article.text for article in segmented.articles
    ]
    assert "verdict" not in request["articles"][0]
    assert "reasons" not in request["articles"][0]
    assert request["fresh_context"] is True
    assert reviewed.status == "passed"
    assert all(article.verdict for article in reviewed.articles)


def test_mid_thought_ending_quarantines_issue(verified_issue):
    """A missing final paragraph must never survive issue approval."""
    proposal = two_proposals(verified_issue)[:1]
    response = passing_review_response(verified_issue, proposal)
    response["output"]["articles"][0].update(
        end_coherent=False,
        reasons=["ending_mid_thought"],
    )
    client = FakeStructuredClient(
        segmentation_response(verified_issue, proposal),
        response,
    )

    manifest = review_articles_against_issue(
        verified_issue, segment_articles(verified_issue, client), client
    )

    assert manifest.status == "quarantined"
    assert "ending_mid_thought" in manifest.articles[0].reasons
    assert manifest.articles[0].verdict is False


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda output: output["articles"][0].update(source_pages=[99]), "article_source_page_unknown"),
        (lambda output: output["articles"][0].update(source_pages=[2, 1]), "article_source_pages_invalid"),
        (lambda output: output["articles"][0].update(transcript_end=10_000), "article_span_invalid"),
        (lambda output: output["articles"][0].update(text="fabricated"), "article_text_mismatch"),
        (
            lambda output: output["articles"][1].update(
                article_id=output["articles"][0]["article_id"]
            ),
            "article_id_duplicate",
        ),
        (
            lambda output: output["articles"][1].update(
                filename=output["articles"][0]["filename"]
            ),
            "article_filename_duplicate",
        ),
        (
            lambda output: output["articles"][1].update(
                transcript_start=output["articles"][0]["transcript_start"]
            ),
            "article_spans_overlap",
        ),
        (lambda output: output.update(ocr_identity=digest("other-ocr")), "ocr_lineage_mismatch"),
        (
            lambda output: output.update(transcript_hash=digest("other-transcript")),
            "transcript_lineage_mismatch",
        ),
    ],
)
def test_deterministic_segmentation_rejects_unsafe_proposals(
    verified_issue, mutation, reason
):
    """Mechanical corruption must be rejected before a semantic model can approve it."""
    proposals = two_proposals(verified_issue)
    response = segmentation_response(verified_issue, proposals)
    mutation(response["output"])
    client = FakeStructuredClient(response)

    with pytest.raises(ArticleReviewError, match=reason):
        segment_articles(verified_issue, client)


@pytest.mark.parametrize(
    ("review_mutation", "reason"),
    [
        ({"start_coherent": False, "reasons": ["opening_missing"]}, "opening_missing"),
        ({"end_coherent": False, "reasons": ["ending_mid_thought"]}, "ending_mid_thought"),
        ({"transitions_ok": False, "reasons": ["continuation_broken"]}, "continuation_broken"),
        ({"omissions": ["final paragraph"] , "reasons": ["content_omitted"]}, "content_omitted"),
        ({"duplications": ["page 2 repeated"], "reasons": ["page_duplicated"]}, "page_duplicated"),
        ({"adjacent_bleed": ["advertisement"] , "reasons": ["adjacent_bleed"]}, "adjacent_bleed"),
        ({"attribution_ok": False, "reasons": ["adjacent_byline"]}, "adjacent_byline"),
    ],
)
def test_any_failed_semantic_verdict_quarantines_the_issue(
    verified_issue, review_mutation, reason
):
    """Every completeness axis is binding, rather than advisory metadata."""
    proposals = two_proposals(verified_issue)
    response = passing_review_response(verified_issue, proposals)
    response["output"]["articles"][0].update(review_mutation)
    client = FakeStructuredClient(
        segmentation_response(verified_issue, proposals),
        response,
    )

    reviewed = review_articles_against_issue(
        verified_issue, segment_articles(verified_issue, client), client
    )

    assert reviewed.status == "quarantined"
    assert reason in reviewed.articles[0].reasons
    assert reason in reviewed.quarantine_reasons


def test_review_rejects_missing_article_and_mismatched_lineage(verified_issue):
    """A reviewer cannot silently skip an article or review another issue generation."""
    proposals = two_proposals(verified_issue)
    response = passing_review_response(verified_issue, proposals)
    response["output"]["articles"].pop()
    client = FakeStructuredClient(
        segmentation_response(verified_issue, proposals),
        response,
    )

    with pytest.raises(ArticleReviewError, match="review_article_reconciliation_failed"):
        review_articles_against_issue(
            verified_issue, segment_articles(verified_issue, client), client
        )

    good_client = FakeStructuredClient(segmentation_response(verified_issue, proposals))
    segmented = segment_articles(verified_issue, good_client)
    invalid_lineage = replace(segmented, ocr_artifact_hash=digest("wrong-predecessor"))
    no_call_client = FakeStructuredClient()
    with pytest.raises(ArticleReviewError, match="manifest_ocr_lineage_mismatch"):
        review_articles_against_issue(verified_issue, invalid_lineage, no_call_client)
    assert no_call_client.requests == []
