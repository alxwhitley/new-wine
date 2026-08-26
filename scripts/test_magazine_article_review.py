#!/usr/bin/env python3
"""Issue-wide article segmentation and completeness review contracts."""

from __future__ import annotations

import copy
import hashlib
import json
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
            "articles": [
                {
                    key: value
                    for key, value in article.items()
                    if key not in {"text", "source_pages"}
                }
                for article in articles
            ],
        },
        "usage": {"input_tokens": 120, "output_tokens": 35},
        "cost_usd": 0.012,
    }


def passing_review_response(transcript, articles):
    article_set_hash = digest(
        json.dumps(
            [
                {
                    "article_id": article["article_id"],
                    "filename": article["filename"],
                    "title": article["title"],
                    "author": article["author"],
                    "source_pages": article["source_pages"],
                    "transcript_start": article["transcript_start"],
                    "transcript_end": article["transcript_end"],
                    "text": article["text"],
                    "text_hash": digest(str(article["text"])),
                }
                for article in articles
            ],
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return {
        "output": {
            "ocr_identity": transcript.ocr_identity,
            "transcript_hash": digest(transcript.text),
            "article_set_hash": article_set_hash,
            "issue_coverage_complete": True,
            "missing_substantive_spans": [],
            "missing_articles": [],
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
                    "failure_reasons": {},
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
    assert "must never overlap" in request["instructions"]
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
    article_schema = request["response_format"]["json_schema"]["schema"][
        "properties"
    ]["articles"]["items"]
    assert "text" not in article_schema["properties"]
    assert "source_pages" not in article_schema["properties"]
    assert "non-overlapping" in article_schema["properties"]["transcript_start"][
        "description"
    ]
    assert manifest.status == "quarantined"
    assert manifest.quarantine_reasons == ("semantic_review_required",)
    assert [article.source_pages for article in manifest.articles] == [(1, 2), (2,)]
    assert [article.text for article in manifest.articles] == [
        proposal["text"] for proposal in proposals
    ]


def test_blank_image_page_reaches_article_segmentation() -> None:
    """A passed image-only page may have a zero-length transcript span."""
    transcript = verified_transcript(
        "",
        "SECOND VOICE\nBy Ben South\nA substantive article reaches its conclusion.",
    )
    proposal = proposed_article(
        transcript,
        article_id="second-voice",
        filename="second-voice.txt",
        title="Second Voice",
        author="Ben South",
        source_pages=[2],
        start_text="SECOND VOICE",
        end_text="reaches its conclusion.",
    )
    client = FakeStructuredClient(segmentation_response(transcript, [proposal]))

    manifest = segment_articles(transcript, client)

    assert transcript.pages[0].transcript_start == transcript.pages[0].transcript_end
    assert manifest.articles[0].source_pages == (2,)
    assert client.last_request["pages"][0]["transcript_start"] == client.last_request[
        "pages"
    ][0]["transcript_end"]


def test_model_filename_is_canonicalized_before_storage(verified_issue) -> None:
    proposals = two_proposals(verified_issue)
    response = segmentation_response(verified_issue, proposals)
    response["output"]["articles"][0]["filename"] = "First Light Article.MD"

    manifest = segment_articles(verified_issue, FakeStructuredClient(response))

    assert manifest.articles[0].filename == "first-light-article.txt"


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
    assert request["articles"][0]["filename"] == "first-light.txt"
    assert request["fresh_context"] is True
    assert reviewed.status == "passed"
    assert all(article.verdict for article in reviewed.articles)


def test_mid_thought_ending_quarantines_issue(verified_issue):
    """A missing final paragraph must never survive issue approval."""
    proposal = two_proposals(verified_issue)[:1]
    response = passing_review_response(verified_issue, proposal)
    response["output"]["articles"][0].update(
        end_coherent=False,
        failure_reasons={"end_coherent": "ending_mid_thought"},
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
    assert manifest.articles[0].failure_reasons == {
        "end_coherent": "ending_mid_thought"
    }
    assert manifest.articles[0].verdict is False


def test_issue_coverage_verdict_quarantines_whole_omitted_article(verified_issue):
    """Per-proposal passes cannot hide a second substantive article omitted upstream."""
    proposal = two_proposals(verified_issue)[:1]
    response = passing_review_response(verified_issue, proposal)
    missing_start = verified_issue.text.index("SECOND VOICE")
    response["output"].update(
        issue_coverage_complete=False,
        missing_articles=["Second Voice by Ben South"],
        missing_substantive_spans=[
            {
                "transcript_start": missing_start,
                "transcript_end": len(verified_issue.text),
                "reason": "substantive authored article absent from proposed set",
            }
        ],
    )
    client = FakeStructuredClient(
        segmentation_response(verified_issue, proposal), response
    )

    reviewed = review_articles_against_issue(
        verified_issue, segment_articles(verified_issue, client), client
    )

    assert reviewed.status == "quarantined"
    assert reviewed.issue_coverage_complete is False
    assert reviewed.missing_articles == ("Second Voice by Ben South",)
    assert reviewed.missing_substantive_spans[0][0] == missing_start
    assert "missing_article:Second Voice by Ben South" in reviewed.quarantine_reasons


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda output: output["articles"][0].update(source_pages=[99]),
            "segmentation_article_invalid",
        ),
        (
            lambda output: output["articles"][0].update(source_pages=[2, 1]),
            "segmentation_article_invalid",
        ),
        (lambda output: output["articles"][0].update(transcript_end=10_000), "article_span_invalid"),
        (
            lambda output: output["articles"][0].update(text="fabricated"),
            "segmentation_article_invalid",
        ),
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
    ("review_mutation", "failed_field", "reason"),
    [
        ({"start_coherent": False}, "start_coherent", "opening_missing"),
        ({"end_coherent": False}, "end_coherent", "ending_mid_thought"),
        ({"transitions_ok": False}, "transitions_ok", "continuation_broken"),
        ({"omissions": ["final paragraph"]}, "omissions", "content_omitted"),
        ({"duplications": ["page 2 repeated"]}, "duplications", "page_duplicated"),
        ({"adjacent_bleed": ["advertisement"]}, "adjacent_bleed", "adjacent_bleed"),
        ({"attribution_ok": False}, "attribution_ok", "adjacent_byline"),
    ],
)
def test_any_failed_semantic_verdict_quarantines_the_issue(
    verified_issue, review_mutation, failed_field, reason
):
    """Every completeness axis is binding, rather than advisory metadata."""
    proposals = two_proposals(verified_issue)
    response = passing_review_response(verified_issue, proposals)
    response["output"]["articles"][0].update(review_mutation)
    response["output"]["articles"][0]["failure_reasons"] = {failed_field: reason}
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


@pytest.mark.parametrize(
    "failure_reasons",
    [
        {},
        {"end_coherent": "ending_mid_thought", "transitions_ok": "not_failed"},
        {"unknown_field": "ending_mid_thought"},
    ],
)
def test_review_rejects_missing_or_extra_field_specific_reasons(
    verified_issue, failure_reasons
):
    """A generic reason must not conceal which binding semantic check failed."""
    proposals = two_proposals(verified_issue)
    response = passing_review_response(verified_issue, proposals)
    response["output"]["articles"][0].update(
        end_coherent=False,
        failure_reasons=failure_reasons,
    )
    client = FakeStructuredClient(
        segmentation_response(verified_issue, proposals),
        response,
    )

    with pytest.raises(ArticleReviewError, match="article_failure_reasons_invalid"):
        review_articles_against_issue(
            verified_issue, segment_articles(verified_issue, client), client
        )


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


def test_resume_identity_binds_segmentation_and_review_configuration(verified_issue):
    """Changing review instructions or reasoning must invalidate a resumable stage."""
    proposals = two_proposals(verified_issue)
    segmented = segment_articles(
        verified_issue,
        FakeStructuredClient(segmentation_response(verified_issue, proposals)),
    )
    segmentation_only_identity = replace(
        segmented.identity,
        prompt_fingerprint=segmented.segmentation_prompt_fingerprint,
    )
    stale_manifest = replace(segmented, identity=segmentation_only_identity)
    client = FakeStructuredClient()

    with pytest.raises(ArticleReviewError, match="manifest_identity_mismatch"):
        review_articles_against_issue(verified_issue, stale_manifest, client)
    assert client.requests == []


def test_article_set_lineage_binds_boundary_and_attribution_metadata(verified_issue):
    """A stale review cannot approve a changed title, author, page, span, or filename."""
    proposals = two_proposals(verified_issue)
    segmented = segment_articles(
        verified_issue,
        FakeStructuredClient(segmentation_response(verified_issue, proposals)),
    )
    changed_article = replace(segmented.articles[0], title="Changed Attribution Boundary")
    changed_manifest = replace(
        segmented,
        articles=(changed_article, *segmented.articles[1:]),
    )
    stale_response = passing_review_response(verified_issue, proposals)

    with pytest.raises(ArticleReviewError, match="review_article_set_lineage_mismatch"):
        review_articles_against_issue(
            verified_issue, changed_manifest, FakeStructuredClient(stale_response)
        )


def test_many_page_article_and_complete_proposed_set_reach_fresh_review():
    """A four-page continuation and its neighbor must be reviewed against all pages."""
    issue = verified_transcript(
        "DEEP ROOTS\nBy Miriam Vale\nThe argument begins with patient attention.",
        "The second movement develops the central claim without restarting.",
        "A third movement qualifies the claim and preserves its context.",
        "The final movement reaches a complete conclusion.\n"
        "NEIGHBORING VOICE\nBy Elias Stone\nA separate article begins and ends here.",
    )
    proposals = [
        proposed_article(
            issue,
            article_id="deep-roots",
            filename="deep-roots.txt",
            title="Deep Roots",
            author="Miriam Vale",
            source_pages=[1, 2, 3, 4],
            start_text="DEEP ROOTS",
            end_text="complete conclusion.",
        ),
        proposed_article(
            issue,
            article_id="neighboring-voice",
            filename="neighboring-voice.txt",
            title="Neighboring Voice",
            author="Elias Stone",
            source_pages=[4],
            start_text="NEIGHBORING VOICE",
            end_text="ends here.",
        ),
    ]
    client = FakeStructuredClient(
        segmentation_response(issue, proposals), passing_review_response(issue, proposals)
    )

    reviewed = review_articles_against_issue(issue, segment_articles(issue, client), client)

    request = client.last_request
    assert request["issue_transcript"] == issue.text
    assert request["articles"] == [
        {
            **proposal,
            "text_hash": digest(str(proposal["text"])),
        }
        for proposal in proposals
    ]
    assert reviewed.status == "passed"
    assert reviewed.articles[0].source_pages == (1, 2, 3, 4)


@pytest.mark.parametrize(
    ("case", "page_texts", "end_text", "review_mutation", "failure_reasons"),
    [
        (
            "advertisement_interruption",
            (
                "STEADFAST\nBy Mara Field\nThe article begins its argument.",
                "ADVERTISEMENT\nRetreat registration and subscription details.",
                "The article resumes and reaches its conclusion.",
            ),
            "reaches its conclusion.",
            {"adjacent_bleed": ["page 2 advertisement"]},
            {"adjacent_bleed": "advertisement_interruption"},
        ),
        (
            "missing_final_paragraph",
            (
                "UNFINISHED\nBy Mara Field\nThe article begins its argument.",
                "The final visible sentence stops mid-thought because",
            ),
            "because",
            {"end_coherent": False, "omissions": ["final paragraph"]},
            {
                "end_coherent": "ending_mid_thought",
                "omissions": "missing_final_paragraph",
            },
        ),
        (
            "duplicated_page_content",
            (
                "ECHO\nBy Mara Field\nThis paragraph appears once.",
                "This paragraph appears once.\nThe article then concludes.",
            ),
            "then concludes.",
            {"duplications": ["This paragraph appears once."]},
            {"duplications": "duplicated_page_content"},
        ),
        (
            "adjacent_byline_bleed",
            (
                "BOUNDARIES\nBy Mara Field\nThe article reaches its own conclusion.\n"
                "NEXT VOICE\nBy Other Author",
            ),
            "Other Author",
            {"adjacent_bleed": ["NEXT VOICE"], "attribution_ok": False},
            {
                "adjacent_bleed": "adjacent_byline_bleed",
                "attribution_ok": "adjacent_byline_attribution",
            },
        ),
    ],
)
def test_realistic_issue_failure_quarantines(
    case, page_texts, end_text, review_mutation, failure_reasons
):
    """Named whole-issue boundary failures must remain binding quarantine gates."""
    issue = verified_transcript(*page_texts)
    proposal = proposed_article(
        issue,
        article_id=case,
        filename=f"{case.replace('_', '-')}.txt",
        title=case.replace("_", " ").title(),
        author="Mara Field",
        source_pages=list(range(1, len(page_texts) + 1)),
        start_text=page_texts[0].split("\n", 1)[0],
        end_text=end_text,
    )
    response = passing_review_response(issue, [proposal])
    response["output"]["articles"][0].update(
        review_mutation,
        failure_reasons=failure_reasons,
    )
    client = FakeStructuredClient(
        segmentation_response(issue, [proposal]), response
    )

    reviewed = review_articles_against_issue(
        issue, segment_articles(issue, client), client
    )

    assert client.last_request["issue_transcript"] == issue.text
    assert client.last_request["articles"][0]["text"] == proposal["text"]
    assert reviewed.status == "quarantined"
    assert set(reviewed.articles[0].reasons) == set(failure_reasons.values())
