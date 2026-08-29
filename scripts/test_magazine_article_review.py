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

    model = MODEL

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


@pytest.fixture
def verified_long_issue() -> VerifiedIssueTranscript:
    """Two pages long enough (~700 chars each) to test the coverage-gap
    tolerance boundary -- the small verified_issue fixture above is too
    short for a realistic gap/shrink to stay within a valid span."""
    filler = "This sentence continues the thought with more detail. " * 12
    return verified_transcript(
        f"LONG FIRST\nBy Ada North\n{filler}The opening closes here.\n",
        f"LONG SECOND\nBy Ben South\n{filler}The second closes here.",
    )


def two_long_proposals(transcript: VerifiedIssueTranscript) -> list[dict[str, object]]:
    return [
        proposed_article(
            transcript,
            article_id="long-first",
            filename="long-first.txt",
            title="Long First",
            author="Ada North",
            source_pages=[1],
            start_text="LONG FIRST",
            end_text="The opening closes here.",
        ),
        proposed_article(
            transcript,
            article_id="long-second",
            filename="long-second.txt",
            title="Long Second",
            author="Ben South",
            source_pages=[2],
            start_text="LONG SECOND",
            end_text="The second closes here.",
        ),
    ]


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
    non_article_spans: list[dict[str, object]] | None = None,
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
            "non_article_spans": non_article_spans or [],
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


def test_segmentation_uses_complete_issue_high_reasoning_and_strict_json(verified_issue):
    """A truncated prompt or unconstrained response could silently lose articles.
    Reasoning effort raised low->medium->high, both 2026-08-27 (New Wine A2):
    low reasoning let segmentation stop 54% through a real 32-page issue
    without error; medium reasoning then produced an implausibly-large
    single/few-article segmentation in 3 of 6 consecutive live attempts."""
    proposals = two_proposals(verified_issue)
    client = FakeStructuredClient(segmentation_response(verified_issue, proposals))

    manifest = segment_articles(verified_issue, client)

    request = client.last_request
    assert request["model"] == MODEL
    assert request["reasoning_effort"] == "high"
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


def test_segmentation_tolerates_out_of_order_non_overlapping_articles(verified_issue):
    """A real live segmentation call, 2026-08-27 (New Wine A2, Issue
    02-1973), returned ten genuinely non-overlapping articles with one
    ("Editorial") placed after a later article in list order despite
    starting earlier in the transcript -- the instructions ask for
    ascending order, but nothing enforces it. The overlap check compared
    each article only to the PREVIOUS one in raw list order (not sorted),
    so this out-of-order-but-non-overlapping return raised
    article_spans_overlap three of four times on real live retries against
    the real issue, even though there was no actual overlap. The coverage
    check just below this one already sorts by transcript_start before
    comparing -- this proves the same pattern for the article-only check:
    swapping two genuinely non-overlapping proposals' list order must not
    change the outcome."""
    proposals = two_proposals(verified_issue)
    reordered = [proposals[1], proposals[0]]
    client = FakeStructuredClient(segmentation_response(verified_issue, reordered))

    manifest = segment_articles(verified_issue, client)

    assert [article.article_id for article in manifest.articles] == [
        "first-light",
        "second-voice",
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
    review_response = passing_review_response(verified_issue, proposals)
    for article_review in review_response["output"]["articles"]:
        article_review["failure_reasons"] = {
            field: None
            for field in (
                "start_coherent",
                "end_coherent",
                "transitions_ok",
                "omissions",
                "duplications",
                "adjacent_bleed",
                "attribution_ok",
            )
        }
    client = FakeStructuredClient(
        segmentation_response(verified_issue, proposals),
        review_response,
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
    failure_schema = request["response_format"]["json_schema"]["schema"][
        "properties"
    ]["articles"]["items"]["properties"]["failure_reasons"]
    assert set(failure_schema["required"]) == {
        "start_coherent",
        "end_coherent",
        "transitions_ok",
        "omissions",
        "duplications",
        "adjacent_bleed",
        "attribution_ok",
    }
    omission_types = {
        choice["type"]
        for choice in failure_schema["properties"]["omissions"]["anyOf"]
    }
    assert omission_types == {
        "string",
        "null",
    }
    assert reviewed.status == "passed"
    assert all(article.verdict for article in reviewed.articles)


def test_mid_thought_ending_quarantines_issue(verified_issue):
    """A missing final paragraph must never survive issue approval."""
    # Full coverage (both articles proposed) so this exercises the semantic
    # end_coherent check, not the deterministic coverage-gap gate below.
    proposal = two_proposals(verified_issue)
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


def test_whole_omitted_article_leaves_tail_gap_rejected_deterministically(
    verified_long_issue,
):
    """A second substantive article never proposed leaves a tail gap far past
    ordinary page-break/ad noise -- the deterministic coverage check catches
    this before the paid semantic review call ever runs (New Wine A2, Issue
    02-1973: exactly this shape -- a 55,107-char/13-page dead zone containing
    a whole omitted Derek Prince article -- reached live review and cost real
    money before being caught)."""
    proposal = two_long_proposals(verified_long_issue)[:1]
    client = FakeStructuredClient(
        segmentation_response(verified_long_issue, proposal)
    )

    with pytest.raises(ArticleReviewError, match="article_coverage_incomplete"):
        segment_articles(verified_long_issue, client)


def test_mid_sequence_gap_past_tolerance_rejected_deterministically(
    verified_long_issue,
):
    """A dropped continuation mid-issue, not just a missing tail, must be
    caught too -- mirrors the live page-3 finding: a 5,190-char continuation
    of "Health and Healing ... Part I" dropped between two proposed
    articles."""
    proposals = two_long_proposals(verified_long_issue)
    response = segmentation_response(verified_long_issue, proposals)
    response["output"]["articles"][0]["transcript_end"] -= 550
    client = FakeStructuredClient(response)

    with pytest.raises(ArticleReviewError, match="article_coverage_incomplete"):
        segment_articles(verified_long_issue, client)


def test_small_formatting_gap_within_tolerance_does_not_reject_deterministically(
    verified_long_issue,
):
    """Ordinary inter-span whitespace/running-header noise (observed live to
    top out at 18 chars) must not trip the deterministic pre-filter. Since
    non_article_spans gives real non-article content (ads, subscription
    notices) an explicit home, this tolerance is now narrowly about
    formatting noise, not ad-sized gaps -- see
    test_non_article_span_accounts_for_a_real_gap below for that case."""
    proposals = two_long_proposals(verified_long_issue)
    response = segmentation_response(verified_long_issue, proposals)
    response["output"]["articles"][0]["transcript_end"] -= 20
    client = FakeStructuredClient(response)

    manifest = segment_articles(verified_long_issue, client)

    assert len(manifest.articles) == 2


def test_non_article_span_accounts_for_a_real_gap():
    """A legitimate non-article gap (an ad, a subscription notice -- see
    fixtures/magazine_review/clean_issue.json's 128-char page-2 gap) must be
    expressible via non_article_spans and not rejected, while still being
    recorded for provenance rather than silently disappearing. The article
    body here is sized so the ad stays comfortably under both the per-span
    and total-fraction caps (see test_oversized_*_rejected_deterministically
    and test_oversized_non_article_total_fraction_rejected_deterministically
    for where those caps bite)."""
    filler = "This sentence continues the thought with more detail. " * 30
    transcript = verified_transcript(
        f"LONG FIRST\nBy Ada North\n{filler}The opening closes here.\n",
        "TAPE MINISTRY AD\nOrder Derek Prince's teaching tapes today.",
    )
    proposal = [
        proposed_article(
            transcript,
            article_id="long-first",
            filename="long-first.txt",
            title="Long First",
            author="Ada North",
            source_pages=[1],
            start_text="LONG FIRST",
            end_text="The opening closes here.",
        )
    ]
    non_article_start = proposal[0]["transcript_end"]
    non_article_end = len(transcript.text)
    response = segmentation_response(
        transcript,
        proposal,
        non_article_spans=[
            {
                "category": "advertisement",
                "reason": "full-page ad for tape ministry",
                "transcript_start": non_article_start,
                "transcript_end": non_article_end,
            }
        ],
    )
    client = FakeStructuredClient(response)

    manifest = segment_articles(transcript, client)

    assert len(manifest.articles) == 1
    assert manifest.non_article_spans == (
        (non_article_start, non_article_end, "advertisement", "full-page ad for tape ministry"),
    )


def test_letters_to_editor_is_a_valid_named_category():
    """"letters_to_editor" (added 2026-08-27) must be accepted and treated
    as a named category (the 5,000-char cap, not the tighter
    other_non_article one) -- a real, recurring magazine section (reader
    mail, no single author) confirmed by two independent live runs (New
    Wine A2, Issue 02-1973: retry_13 treated it as its own article, a
    direct 2026-08-27 diagnostic call treated it as non-article) that
    doesn't fit any other named category."""
    filler = "This sentence continues the thought with more detail. " * 30
    transcript = verified_transcript(
        f"LONG FIRST\nBy Ada North\n{filler}The opening closes here.\n",
        "LETTERS TO THE EDITOR\nDear editor, thank you for this magazine.",
    )
    proposal = [
        proposed_article(
            transcript,
            article_id="long-first",
            filename="long-first.txt",
            title="Long First",
            author="Ada North",
            source_pages=[1],
            start_text="LONG FIRST",
            end_text="The opening closes here.",
        )
    ]
    non_article_start = proposal[0]["transcript_end"]
    non_article_end = len(transcript.text)
    response = segmentation_response(
        transcript,
        proposal,
        non_article_spans=[
            {
                "category": "letters_to_editor",
                "reason": "reader mail, no single author",
                "transcript_start": non_article_start,
                "transcript_end": non_article_end,
            }
        ],
    )
    client = FakeStructuredClient(response)

    manifest = segment_articles(transcript, client)

    assert manifest.non_article_spans == (
        (non_article_start, non_article_end, "letters_to_editor", "reader mail, no single author"),
    )


def test_oversized_other_non_article_span_rejected_deterministically():
    """A vague "other_non_article" span past 2,500 chars is rejected before
    the paid semantic review call. Live evidence, same-day validation of the
    coverage-completeness fix (New Wine A2, Issue 02-1973, 2026-08-27): once
    full coverage was required, the model started dumping real articles
    ("The Call of Love", "New Wine Forum") into "other_non_article" spans of
    3,770 and 31,718 chars instead of correctly identifying them -- the
    semantic reviewer caught both, but that's a paid call this check can
    preempt for egregious cases. Named categories get a looser (not zero)
    cap -- see test_oversized_named_non_article_span_rejected_deterministically
    below for why they aren't exempt either."""
    filler = "Unclassified filler text fills this whole page over and over. " * 45
    assert len(filler) > 2500
    transcript = verified_transcript(
        "SHORT ARTICLE\nBy Ada North\nA complete short article.\n",
        filler,
    )
    proposal = [
        proposed_article(
            transcript,
            article_id="short-article",
            filename="short-article.txt",
            title="Short Article",
            author="Ada North",
            source_pages=[1],
            start_text="SHORT ARTICLE",
            end_text="A complete short article.",
        )
    ]
    non_article_start = proposal[0]["transcript_end"]
    non_article_end = len(transcript.text)
    response = segmentation_response(
        transcript,
        proposal,
        non_article_spans=[
            {
                "category": "other_non_article",
                "reason": "unclassified material",
                "transcript_start": non_article_start,
                "transcript_end": non_article_end,
            }
        ],
    )
    client = FakeStructuredClient(response)

    with pytest.raises(
        ArticleReviewError, match="non_article_span_implausibly_large"
    ):
        segment_articles(transcript, client)


def test_oversized_named_non_article_span_rejected_deterministically():
    """A NAMED category (advertisement, masthead, etc.) past 5,000 chars is
    also rejected -- named categories are not exempt. Live evidence, the
    very next attempt after the other_non_article-only cap shipped (New Wine
    A2, Issue 02-1973, 2026-08-27): the model dodged that cap by labeling a
    113,294-char span (93% of the whole 121,011-char issue, containing SIX
    real articles) as "advertisement" instead of "other_non_article". No
    real 32-page magazine issue is 93% ads. The semantic reviewer caught all
    six again, but that's exactly the paid call this deterministic layer
    exists to preempt."""
    filler = "Unclassified filler text fills this whole page over and over. " * 100
    assert len(filler) > 5000
    transcript = verified_transcript(
        "SHORT ARTICLE\nBy Ada North\nA complete short article.\n",
        filler,
    )
    proposal = [
        proposed_article(
            transcript,
            article_id="short-article",
            filename="short-article.txt",
            title="Short Article",
            author="Ada North",
            source_pages=[1],
            start_text="SHORT ARTICLE",
            end_text="A complete short article.",
        )
    ]
    non_article_start = proposal[0]["transcript_end"]
    non_article_end = len(transcript.text)
    response = segmentation_response(
        transcript,
        proposal,
        non_article_spans=[
            {
                "category": "advertisement",
                "reason": "letters, subscription notices, conference ads",
                "transcript_start": non_article_start,
                "transcript_end": non_article_end,
            }
        ],
    )
    client = FakeStructuredClient(response)

    with pytest.raises(
        ArticleReviewError, match="non_article_span_implausibly_large"
    ):
        segment_articles(transcript, client)


def test_oversized_non_article_total_fraction_rejected_deterministically():
    """Many small non_article_spans, each individually under both per-span
    caps, must not add up past 40% of the transcript either -- otherwise the
    model could dodge the per-span caps by simply splitting the same abuse
    into more, smaller pieces instead of one large one."""
    article_body = "This sentence continues the thought with more detail. " * 60
    ad_body = "Order tapes today. " * 35  # ~700 chars, well under both per-span caps
    assert 500 < len(ad_body) < 2000
    parts = [f"LONG FIRST\nBy Ada North\n{article_body}The opening closes here.\n"]
    parts.extend(f"AD {i}\n{ad_body}" for i in range(4))
    transcript = verified_transcript(*parts)
    proposal = [
        proposed_article(
            transcript,
            article_id="long-first",
            filename="long-first.txt",
            title="Long First",
            author="Ada North",
            source_pages=[1],
            start_text="LONG FIRST",
            end_text="The opening closes here.",
        )
    ]
    ad_starts = [transcript.text.index(f"AD {i}") for i in range(4)]
    ad_ends = ad_starts[1:] + [len(transcript.text)]
    non_article_spans = [
        {
            "category": "advertisement",
            "reason": f"tape ad {i}",
            "transcript_start": start,
            "transcript_end": end,
        }
        for i, (start, end) in enumerate(zip(ad_starts, ad_ends))
    ]
    total_non_article = sum(s["transcript_end"] - s["transcript_start"] for s in non_article_spans)
    assert total_non_article / len(transcript.text) > 0.40
    response = segmentation_response(transcript, proposal, non_article_spans=non_article_spans)
    client = FakeStructuredClient(response)

    with pytest.raises(
        ArticleReviewError, match="non_article_total_fraction_implausible"
    ):
        segment_articles(transcript, client)


def test_single_article_spanning_whole_issue_rejected_deterministically():
    """A single article past 30,000 chars is rejected before the paid
    semantic review call -- the inverse of the non-article-abuse cases
    above: too FEW articles by making one absurdly large, rather than too
    much non-article content. Live evidence, the attempt immediately after
    e8ca4a3 shipped (New Wine A2, Issue 02-1973, 2026-08-27): the model
    proposed exactly one "article" -- title "New Wine February 1973 Issue",
    author "Various" -- spanning the entire 121,011-char/32-page transcript.
    100% coverage, 0% non-article, so every prior check passed trivially,
    and for the first time this session the semantic reviewer approved it
    too (verdict=True, status=passed) -- only an unrelated rate-limit error
    on the next stage stopped it from proceeding as a "passed" issue."""
    filler = "This sentence continues the thought with more detail. " * 600
    assert len(filler) > 30000
    transcript = verified_transcript(
        f"WHOLE ISSUE\nBy Various\n{filler}The issue closes here.\n"
    )
    proposal = [
        proposed_article(
            transcript,
            article_id="whole-issue",
            filename="whole-issue.txt",
            title="New Wine February 1973 Issue",
            author="Various",
            source_pages=[1],
            start_text="WHOLE ISSUE",
            end_text="The issue closes here.",
        )
    ]
    response = segmentation_response(transcript, proposal)
    client = FakeStructuredClient(response)

    with pytest.raises(ArticleReviewError, match="article_implausibly_long"):
        segment_articles(transcript, client)


def test_foreign_article_title_bled_into_span_rejected_deterministically():
    """An article whose span opens with a DIFFERENT article's title is
    rejected before the paid semantic review call -- a well-formed span
    (correct length, no overlap, full coverage) can still open with the
    wrong content if a boundary lands one section too late. Live evidence,
    New Wine A2, Issue 02-1973, 2026-08-27: an article labeled
    "spiritual_potpourri" opened at transcript_start+0 with
    "Keeping\nthe\nUnity\n\nReprinted with permission..." -- word-for-word
    the title and reprint credit of the separate "keeping_the_unity"
    article. The semantic reviewer, given this exact input, caught it in
    only 1 of 4 live repeated calls -- not a reliable backstop on its own.
    See _TITLE_BLEED_WINDOW_CHARS above."""
    transcript = verified_transcript(
        "KEEPING THE UNITY\nReprinted with permission.\nThe real body of "
        "this article discusses denominational harmony at length.\n",
        "SPIRITUAL POTPOURRI\nKeeping The Unity\nReprinted with permission.\n"
        "The bled-in title above belongs to the previous article, not this "
        "one -- the real Forum content would follow here.",
    )
    proposal = [
        proposed_article(
            transcript,
            article_id="keeping_the_unity",
            filename="keeping-the-unity.txt",
            title="Keeping The Unity",
            author="Reprinted",
            source_pages=[1],
            start_text="KEEPING THE UNITY",
            end_text="denominational harmony at length.",
        ),
        proposed_article(
            transcript,
            article_id="spiritual_potpourri",
            filename="spiritual-potpourri.txt",
            title="Spiritual Potpourri",
            author="New Wine Forum",
            source_pages=[2],
            start_text="SPIRITUAL POTPOURRI",
            end_text="the real Forum content would follow here.",
        ),
    ]
    response = segmentation_response(transcript, proposal)
    client = FakeStructuredClient(response)

    with pytest.raises(ArticleReviewError, match="foreign_article_title_in_span"):
        segment_articles(transcript, client)


def test_partial_title_word_overlap_does_not_reject_deterministically():
    """Sharing a single word with another article's title is not enough to
    trigger the bleed check -- only the OTHER article's FULL normalized
    title landing inside this span's opening window counts. Guards against
    flagging legitimate coincidental word overlap (e.g. two unrelated
    articles both mentioning "spirit")."""
    transcript = verified_transcript(
        "THE UNITY OF THE SPIRIT\nBy Ada North\nThis article discusses "
        "walking worthy of the calling with which you were called.\n",
        "SPIRITUAL POTPOURRI\nBy New Wine Forum\nFrom time to time we "
        "receive letters from our readers on matters of common concern.",
    )
    proposal = [
        proposed_article(
            transcript,
            article_id="unity-of-the-spirit",
            filename="unity-of-the-spirit.txt",
            title="The Unity of the Spirit",
            author="Ada North",
            source_pages=[1],
            start_text="THE UNITY OF THE SPIRIT",
            end_text="with which you were called.",
        ),
        proposed_article(
            transcript,
            article_id="spiritual-potpourri",
            filename="spiritual-potpourri.txt",
            title="Spiritual Potpourri",
            author="New Wine Forum",
            source_pages=[2],
            start_text="SPIRITUAL POTPOURRI",
            end_text="matters of common concern.",
        ),
    ]
    response = segmentation_response(transcript, proposal)
    client = FakeStructuredClient(response)

    manifest = segment_articles(transcript, client)
    assert [a.article_id for a in manifest.articles] == [
        "unity-of-the-spirit",
        "spiritual-potpourri",
    ]


def test_issue_coverage_verdict_quarantines_content_the_reviewer_flags_missing(
    verified_issue,
):
    """The semantic reviewer's coverage verdict must still be honored even
    when every proposed span is present and contiguous -- a raw offset gap
    is not the only way real content goes missing (e.g. a photo caption or
    sidebar never entered the transcript at all, so there is no gap to
    detect deterministically). Mirrors a real live finding: Issue 02-1973's
    "page 7 continuation" flag sat inside an ordinary ~17-char page-break
    gap, not a detectable span gap, and only the semantic reviewer caught
    it."""
    proposal = two_proposals(verified_issue)
    response = passing_review_response(verified_issue, proposal)
    response["output"].update(
        issue_coverage_complete=False,
        missing_articles=["Sidebar photo caption (untranscribed)"],
        missing_substantive_spans=[
            {
                "transcript_start": proposal[1]["transcript_start"],
                "transcript_end": proposal[1]["transcript_end"],
                "reason": "sidebar caption on this page never entered the transcript",
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
    assert reviewed.missing_articles == ("Sidebar photo caption (untranscribed)",)
    assert (
        "missing_article:Sidebar photo caption (untranscribed)"
        in reviewed.quarantine_reasons
    )


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


def test_segmentation_model_reflects_the_client_that_actually_ran(verified_issue):
    """`segment_articles()` must stamp `segmentation_model` from the client
    that actually performed the call, not the hardcoded ARTICLE_MODEL
    constant -- found live 2026-08-29 when a one-off Claude Opus 5 test's
    resulting manifest falsely claimed gpt-oss-120b had segmented it
    (docs/audits/2026-08/new_wine_opus_segmentation_e2e_test_2026-08-29.md)."""
    proposals = two_proposals(verified_issue)
    client = FakeStructuredClient(segmentation_response(verified_issue, proposals))
    client.model = "claude-opus-5"

    manifest = segment_articles(verified_issue, client)

    assert manifest.segmentation_model == "claude-opus-5"


def test_reviewer_model_reflects_the_client_that_actually_ran(verified_issue):
    """Same defect, review stage: `review_articles_against_issue()` must stamp
    `reviewer_model` from the client that actually ran the review call, not
    the hardcoded ARTICLE_MODEL constant."""
    proposals = two_proposals(verified_issue)
    segmented = segment_articles(
        verified_issue,
        FakeStructuredClient(segmentation_response(verified_issue, proposals)),
    )
    review_response = passing_review_response(verified_issue, proposals)
    for article_review in review_response["output"]["articles"]:
        article_review["failure_reasons"] = {
            field: None
            for field in (
                "start_coherent",
                "end_coherent",
                "transitions_ok",
                "omissions",
                "duplications",
                "adjacent_bleed",
                "attribution_ok",
            )
        }
    review_client = FakeStructuredClient(review_response)
    review_client.model = "claude-opus-5"

    reviewed = review_articles_against_issue(verified_issue, segmented, review_client)

    assert reviewed.reviewer_model == "claude-opus-5"


def test_review_rejects_a_manifest_segmented_by_an_undeclared_model(verified_issue):
    """Once segmentation_model honestly reflects the real client, the
    existing lineage check (`manifest.segmentation_model != ARTICLE_MODEL`)
    stops trivially passing by accident and actually catches a real
    model-mixing mismatch -- the exact gap the Opus test's manifest exposed."""
    proposals = two_proposals(verified_issue)
    mixed_model_client = FakeStructuredClient(
        segmentation_response(verified_issue, proposals)
    )
    mixed_model_client.model = "claude-opus-5"
    segmented = segment_articles(verified_issue, mixed_model_client)

    review_client = FakeStructuredClient()
    with pytest.raises(
        ArticleReviewError, match="manifest_segmentation_model_mismatch"
    ):
        review_articles_against_issue(verified_issue, segmented, review_client)
    assert review_client.requests == []
