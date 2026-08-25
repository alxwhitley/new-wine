#!/usr/bin/env python3
"""Exact-evidence proposition review contracts for New Wine articles."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
import propositions as propositions_module

from magazine_review.proposition_review import (
    PropositionReviewError,
    approved_propositions_for,
    review_issue_propositions,
)
from magazine_review.schemas import (
    ApprovedPropositionSet,
    ArticleManifest,
    ArticleRecord,
    ArtifactValidationError,
    StageIdentity,
)
from propositions import PropositionExtractionComputation, ReferenceGroundingComputation


MODEL = "openai/gpt-oss-120b"
PRICING_SOURCE = "https://console.groq.com/docs/model/openai/gpt-oss-120b"
ARTICLE_TEXT = (
    "Grace is received by faith, not earned by effort. "
    "The author says this gift forms a generous life."
)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def article_manifest() -> ArticleManifest:
    identity = StageIdentity(
        schema_version=1,
        input_hashes={"issue.pdf": digest("issue")},
        model=MODEL,
        prompt_fingerprint=digest("article-review"),
        renderer_settings={"dpi": 300},
    )
    article = ArticleRecord(
        article_id="a1",
        filename="grace.txt",
        title="Grace",
        author="Ada North",
        source_pages=(1,),
        transcript_start=0,
        transcript_end=len(ARTICLE_TEXT),
        text=ARTICLE_TEXT,
        text_hash=digest(ARTICLE_TEXT),
        start_coherent=True,
        end_coherent=True,
        transitions_ok=True,
        omissions=(),
        duplications=(),
        adjacent_bleed=(),
        attribution_ok=True,
        verdict=True,
    )
    return ArticleManifest(
        identity=identity,
        issue_hash=digest("issue"),
        ocr_artifact_hash=digest("ocr-artifact"),
        transcript=ARTICLE_TEXT,
        articles=(article,),
        segmentation_model=MODEL,
        segmentation_prompt_fingerprint=digest("segmentation"),
        segmentation_usage={"input_tokens": 20, "output_tokens": 5},
        segmentation_cost_usd=0.01,
        reviewer_model=MODEL,
        reviewer_prompt_fingerprint=digest("article-review"),
        reviewer_usage={"input_tokens": 30, "output_tokens": 8},
        reviewer_cost_usd=0.02,
    )


class RecordingReviewer:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def complete(self, request: dict[str, object]) -> dict[str, object]:
        self.requests.append(copy.deepcopy(request))
        return copy.deepcopy(self.response)


def extraction(
    *items: dict[str, object],
    model: str = MODEL,
    usage: dict[str, int] | None = None,
    cost_usd: float | None = 0.031,
) -> PropositionExtractionComputation:
    grounding = ReferenceGroundingComputation(
        propositions=[dict(item) for item in items],
        review_records=[],
        n_found=3,
        n_grounded=2,
        n_stripped_fabricated=1,
        n_stripped_uncertain=0,
        n_kept_arbitration=0,
    )
    return PropositionExtractionComputation(
        output=[dict(item) for item in items],
        model=model,
        usage=usage if usage is not None else {
            "input_tokens": 101,
            "output_tokens": 17,
            "total_tokens": 118,
        },
        cost_usd=cost_usd,
        grounding=grounding,
    )


def proposition(index: int = 1, content: str | None = None) -> dict[str, object]:
    return {
        "proposition_index": index,
        "content": content or "Ada North teaches that grace is received by faith, not earned.",
    }


def review_response(
    article_manifest: ArticleManifest,
    *,
    supported: bool = True,
    missing_qualification: bool = False,
    overstatement: bool = False,
    attribution_ok: bool = True,
    evidence_start: int = 0,
    evidence_text: str = "Grace is received by faith, not earned by effort.",
) -> dict[str, object]:
    article = article_manifest.articles[0]
    return {
        "output": {
            "article_id": article.article_id,
            "article_hash": article.article_hash,
            "propositions": [
                {
                    "proposition_index": 1,
                    "content": proposition()["content"],
                    "evidence_text": evidence_text,
                    "evidence_start": evidence_start,
                    "evidence_end": evidence_start + len(evidence_text),
                    "supported": supported,
                    "missing_qualification": missing_qualification,
                    "overstatement": overstatement,
                    "attribution_ok": attribution_ok,
                    "reviewer_reasons": ["The exact passage determines the verdict."],
                }
            ],
        },
        "usage": {"input_tokens": 80, "output_tokens": 20},
        "cost_usd": 0.015,
    }


def test_substantive_article_with_zero_propositions_quarantines(article_manifest):
    """A successful but empty extraction must never make the article eligible."""
    reviewer = RecordingReviewer({})

    result = review_issue_propositions(
        article_manifest,
        extractor=lambda **_: extraction(),
        reviewer=reviewer,
    )

    assert result.status == "quarantined"
    assert result.reasons == ("article:a1:zero_propositions",)
    assert result.propositions == ()
    assert reviewer.requests == []
    result.validate()
    with pytest.raises(ArtifactValidationError, match="proposition_not_supported"):
        approved_propositions_for("a1")


def test_accounting_sink_records_extraction_and_review_before_lineage_failure(
    article_manifest,
) -> None:
    """Validated provider accounting survives semantic response rejection."""
    response = review_response(article_manifest)
    response["output"]["article_id"] = "wrong-article"
    recorded = []
    kwargs = {}
    if "accounting_sink" in inspect.signature(review_issue_propositions).parameters:
        kwargs["accounting_sink"] = (
            lambda stage, usage, cost: recorded.append((stage, dict(usage), cost))
        )

    with pytest.raises(PropositionReviewError, match="proposition_review_lineage_mismatch"):
        review_issue_propositions(
            article_manifest,
            reviewer=RecordingReviewer(response),
            extractor=lambda **_: extraction(proposition()),
            **kwargs,
        )

    assert recorded == [
        (
            "proposition_extraction",
            {"input_tokens": 101, "output_tokens": 17, "total_tokens": 118},
            0.031,
        ),
        (
            "proposition_review",
            {"input_tokens": 80, "output_tokens": 20},
            0.015,
        ),
    ]


@pytest.mark.parametrize("raw", [[], [proposition()]])
def test_raw_list_extraction_is_a_technical_error(article_manifest, raw):
    """No raw list may fabricate model, usage, cost, or grounding provenance."""
    reviewer = RecordingReviewer({})

    with pytest.raises(PropositionReviewError, match="proposition_extraction_result_invalid"):
        review_issue_propositions(
            article_manifest,
            extractor=lambda **_: raw,
            reviewer=reviewer,
        )

    assert reviewer.requests == []


def test_reviewer_usage_rejects_negative_values(article_manifest) -> None:
    response = review_response(article_manifest)
    response["usage"] = {"input_tokens": -1}

    with pytest.raises(
        PropositionReviewError, match="proposition_reviewer_usage_invalid"
    ):
        review_issue_propositions(
            article_manifest,
            extractor=lambda **_: extraction(proposition()),
            reviewer=RecordingReviewer(response),
        )


def test_evidence_must_round_trip(article_manifest):
    """A plausible quote with shifted offsets is not exact review evidence."""
    response = review_response(article_manifest, evidence_start=1)
    reviewer = RecordingReviewer(response)

    result = review_issue_propositions(
        article_manifest,
        extractor=lambda **_: extraction(proposition()),
        reviewer=reviewer,
    )

    assert result.status == "quarantined"
    assert "evidence_offset_mismatch" in result.reasons
    assert result.propositions[0].evidence_offset_exact is False
    relabeled = replace(result, status="passed", reasons=())
    with pytest.raises(ArtifactValidationError, match="evidence_offset_mismatch"):
        ApprovedPropositionSet.from_review(relabeled, digest("review-artifact"))


def test_empty_article_is_rejected_before_extraction(article_manifest):
    """Whitespace cannot be treated as a substantive reviewed article."""
    blank = "   "
    article = replace(
        article_manifest.articles[0],
        transcript_end=len(blank),
        text=blank,
        text_hash=digest(blank),
    )
    manifest = replace(article_manifest, transcript=blank, articles=(article,))

    with pytest.raises(PropositionReviewError, match="article_text_empty"):
        review_issue_propositions(
            manifest,
            extractor=lambda **_: (_ for _ in ()).throw(
                AssertionError("extractor must not run")
            ),
            reviewer=RecordingReviewer({}),
        )


def test_default_adapter_uses_v31_article_identity_and_author(article_manifest, monkeypatch):
    """Changing any extractor argument would bypass the accepted grounded path."""
    calls: list[dict[str, object]] = []

    def fake_default(text, **kwargs):
        calls.append({"text": text, **kwargs})
        return extraction(proposition())

    monkeypatch.setattr(
        "magazine_review.proposition_review.extract_propositions_with_evidence",
        fake_default,
    )
    reviewer = RecordingReviewer(review_response(article_manifest))

    result = review_issue_propositions(article_manifest, reviewer=reviewer)

    assert calls == [
        {
            "text": ARTICLE_TEXT,
            "doc_id": "a1",
            "speaker": "Ada North",
            "prompt_version": "v3.1",
            "grounding_review_sink": None,
        }
    ]
    assert result.status == "passed"


def test_default_adapter_runs_grounding_without_legacy_sink_write(
    article_manifest, monkeypatch
):
    """Preview keeps grounding unconditional while disabling its legacy file sink."""
    raw = [proposition()]
    response = SimpleNamespace(
        model=MODEL,
        cost_usd=0.031,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(raw))
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=101,
            completion_tokens=17,
            total_tokens=118,
        ),
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_: response)
        )
    )
    original_compute = propositions_module.compute_reference_grounding
    grounding_calls: list[tuple[list[dict], str, str]] = []

    def compute_with_observable_review_records(items, text, doc_id):
        grounding_calls.append((copy.deepcopy(items), text, doc_id))
        grounded = original_compute(items, text, doc_id)
        return grounded._replace(review_records=[{"observable": True}])

    monkeypatch.setattr(propositions_module, "_get_groq", lambda: client)
    monkeypatch.setattr(
        propositions_module,
        "compute_reference_grounding",
        compute_with_observable_review_records,
    )
    monkeypatch.setattr(
        propositions_module,
        "_write_grounding_review_records",
        lambda *_: (_ for _ in ()).throw(AssertionError("legacy sink wrote")),
    )

    result = review_issue_propositions(
        article_manifest,
        reviewer=RecordingReviewer(review_response(article_manifest)),
    )

    assert result.status == "passed"
    assert grounding_calls == [(raw, ARTICLE_TEXT, "a1")]


def test_grounding_output_must_match_extraction_output(article_manifest):
    """Grounding totals cannot be attached to a different proposition payload."""
    computation = extraction(proposition())
    mismatched_grounding = computation.grounding._replace(
        propositions=[proposition(content="Different grounded content.")]
    )
    mismatched = computation._replace(grounding=mismatched_grounding)
    reviewer = RecordingReviewer(review_response(article_manifest))

    with pytest.raises(PropositionReviewError, match="proposition_grounding_output_mismatch"):
        review_issue_propositions(
            article_manifest,
            extractor=lambda **_: mismatched,
            reviewer=reviewer,
        )

    assert reviewer.requests == []


def test_review_persists_exact_extraction_and_grounding_provenance(article_manifest):
    """Preview audit data and proposition bytes must survive without rewriting."""
    extracted = proposition(content="Ada North teaches that grace is received by faith, not earned.")
    reviewer = RecordingReviewer(review_response(article_manifest))

    result = review_issue_propositions(
        article_manifest,
        extractor=lambda **_: extraction(extracted),
        reviewer=reviewer,
    )

    assert result.model == MODEL
    assert result.prompt_version == "v3.1"
    assert result.extraction_usage == {
        "input_tokens": 101,
        "output_tokens": 17,
        "total_tokens": 118,
    }
    assert result.extraction_cost_usd == 0.031
    assert result.extraction_cost_basis == {
        "type": "provider_reported",
        "model": MODEL,
        "currency": "USD",
    }
    assert result.grounding_totals == {
        "found": 3,
        "grounded": 2,
        "stripped_fabricated": 1,
        "stripped_uncertain": 0,
        "kept_arbitration": 0,
    }
    assert result.propositions[0].content == extracted["content"]
    assert approved_propositions_for("a1") == [extracted]


def test_missing_provider_cost_uses_auditable_decimal_pricing_snapshot(article_manifest):
    """A missing provider cost is calculated only from pinned rates and usage."""
    result = review_issue_propositions(
        article_manifest,
        extractor=lambda **_: extraction(proposition(), cost_usd=None),
        reviewer=RecordingReviewer(review_response(article_manifest)),
    )

    assert result.extraction_cost_usd == 0.00002535
    assert result.extraction_cost_basis == {
        "type": "pricing_snapshot",
        "model": MODEL,
        "currency": "USD",
        "input_usd_per_million_tokens": "0.15",
        "output_usd_per_million_tokens": "0.60",
        "source_url": PRICING_SOURCE,
        "observed_date": "2026-08-25",
    }


@pytest.mark.parametrize(
    ("computation", "reason"),
    [
        (
            extraction(
                proposition(),
                cost_usd=None,
                usage={"input_tokens": 101, "total_tokens": 118},
            ),
            "proposition_pricing_usage_invalid",
        ),
        (
            extraction(proposition(), cost_usd=None, model="different-model"),
            "proposition_pricing_model_mismatch",
        ),
    ],
)
def test_pricing_fallback_rejects_missing_usage_or_model_mismatch(
    article_manifest, computation, reason
):
    """A snapshot cannot price unknown usage or a model with different rates."""
    reviewer = RecordingReviewer({})

    with pytest.raises(PropositionReviewError, match=reason):
        review_issue_propositions(
            article_manifest,
            extractor=lambda **_: computation,
            reviewer=reviewer,
        )

    assert reviewer.requests == []


def test_reviewer_gets_only_verified_article_and_complete_proposition_set(article_manifest):
    """Semantic support judgment must not inherit unrelated issue or prior context."""
    second = proposition(2, "Ada North teaches that grace forms a generous life.")
    response = review_response(article_manifest)
    second_evidence = "this gift forms a generous life"
    second_start = ARTICLE_TEXT.index(second_evidence)
    response["output"]["propositions"].append(
        {
            "proposition_index": 2,
            "content": second["content"],
            "evidence_text": second_evidence,
            "evidence_start": second_start,
            "evidence_end": second_start + len(second_evidence),
            "supported": True,
            "missing_qualification": False,
            "overstatement": False,
            "attribution_ok": True,
            "reviewer_reasons": ["The second sentence directly supports it."],
        }
    )
    reviewer = RecordingReviewer(response)

    review_issue_propositions(
        article_manifest,
        extractor=lambda **_: extraction(proposition(), second),
        reviewer=reviewer,
    )

    request = reviewer.requests[0]
    assert request["fresh_context"] is True
    assert request["article"] == {
        "article_id": "a1",
        "title": "Grace",
        "author": "Ada North",
        "text": ARTICLE_TEXT,
        "text_hash": digest(ARTICLE_TEXT),
    }
    assert request["propositions"] == [proposition(), second]
    assert "issue_transcript" not in request
    assert request["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda item: item.update(content=""), "proposition_content_required"),
        (lambda item: item.update(proposition_index=2), "proposition_indices_not_contiguous"),
        (lambda item: item.update(extra="unexpected"), "proposition_extraction_schema_invalid"),
    ],
)
def test_malformed_extraction_is_rejected_before_semantic_review(
    article_manifest, mutation, reason
):
    """Malformed extraction cannot consume a semantic call or become evidence."""
    item = proposition()
    mutation(item)
    reviewer = RecordingReviewer({})

    with pytest.raises(PropositionReviewError, match=reason):
        review_issue_propositions(
            article_manifest,
            extractor=lambda **_: extraction(item),
            reviewer=reviewer,
        )

    assert reviewer.requests == []


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        ({"supported": False}, "unsupported"),
        ({"missing_qualification": True}, "missing_qualification"),
        ({"overstatement": True}, "overstatement"),
        ({"attribution_ok": False}, "attribution_mismatch"),
    ],
)
def test_any_semantic_failure_quarantines_and_revokes_approval(
    article_manifest, flags, reason
):
    """No partially passing issue may expose a previously approved proposition."""
    passing = RecordingReviewer(review_response(article_manifest))
    review_issue_propositions(
        article_manifest,
        extractor=lambda **_: extraction(proposition()),
        reviewer=passing,
    )
    failing_response = review_response(article_manifest, **flags)
    failing = RecordingReviewer(failing_response)

    result = review_issue_propositions(
        article_manifest,
        extractor=lambda **_: extraction(proposition()),
        reviewer=failing,
    )

    assert result.status == "quarantined"
    assert f"article:a1:proposition:1:{reason}" in result.reasons
    with pytest.raises(ArtifactValidationError, match="proposition_not_supported"):
        approved_propositions_for("a1")


def test_reviewer_must_return_exact_proposition_text(article_manifest):
    """A reviewer cannot silently edit extraction output into an approval."""
    response = review_response(article_manifest)
    response["output"]["propositions"][0]["content"] = "A cleaner rewrite."

    with pytest.raises(PropositionReviewError, match="review_proposition_mismatch"):
        review_issue_propositions(
            article_manifest,
            extractor=lambda **_: extraction(proposition()),
            reviewer=RecordingReviewer(response),
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
