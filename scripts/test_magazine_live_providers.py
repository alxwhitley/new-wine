import base64
import json
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace

import pytest

from magazine_review.benchmark import BenchmarkCandidate
from magazine_review.ocr import IssuePageOCRFixture, RenderedPage
from magazine_review.live_providers import (
    CostBudget,
    GEMINI_REVIEW_MODEL,
    GROQ_MODEL,
    GeminiLiveOCRProvider,
    GeminiLivePageReviewer,
    GroqStructuredOutputClient,
    _budgeted_proposition_extractor,
    _cost_budget,
    _groq_factory,
    _page_review_json,
    build_live_provider_adapters,
)
from review_magazine_issue import AcceptedBenchmarkDecision


def _decision() -> AcceptedBenchmarkDecision:
    return AcceptedBenchmarkDecision(
        name="accepted-new-wine-ocr",
        issue_filename="issue.pdf",
        issue_pdf_sha256="1" * 64,
        accepted_candidate=BenchmarkCandidate(
            provider="Gemini", model="gemini-3.7-flash"
        ),
        benchmark_report_sha256="2" * 64,
        decision_sha256="3" * 64,
    )


def test_factory_is_lazy_and_preserves_the_accepted_model_split() -> None:
    adapters = build_live_provider_adapters(
        _decision(), environ={"MAGAZINE_REVIEW_COST_CEILING_USD": "1.25"}
    )

    assert adapters.initial_ocr_provider.candidate == BenchmarkCandidate(
        provider="Gemini", model="gemini-3.7-flash"
    )
    assert adapters.page_reviewer.model == GEMINI_REVIEW_MODEL
    assert adapters.repair_ocr_provider.candidate == BenchmarkCandidate(
        provider="Gemini", model=GEMINI_REVIEW_MODEL
    )
    assert adapters.article_client.model == GROQ_MODEL
    assert adapters.proposition_reviewer.model == GROQ_MODEL
    assert callable(adapters.proposition_extractor)
    assert adapters.proposition_extractor_model == GROQ_MODEL


def test_gemini_ocr_sends_the_full_png_at_high_resolution_and_accounts_cost() -> None:
    calls = []

    def post(url, headers, payload):
        calls.append((url, headers, payload))
        return {
            "candidates": [{"content": {"parts": [{"text": "PAGE TEXT"}]}}],
            "usageMetadata": {
                "promptTokenCount": 1200,
                "candidatesTokenCount": 80,
                "totalTokenCount": 1280,
            },
        }

    provider = GeminiLiveOCRProvider(
        "gemini-3.7-flash",
        api_key=lambda: "gemini-key",
        post_json=post,
        budget=CostBudget(1.25),
    )
    fixture = IssuePageOCRFixture(
        pdf_path=Path("issue.pdf"),
        pdf_sha256="a" * 64,
        page_number=1,
        fixture_class="good_control",
        human_scoring={},
        image_bytes=b"png-bytes",
        image_hash="b" * 64,
        instructions="Transcribe everything.",
        target_regions=("footer",),
    )

    response = provider.transcribe(fixture)

    assert response.text == "PAGE TEXT"
    assert response.usage == {
        "input_tokens": 1200,
        "output_tokens": 80,
        "total_tokens": 1280,
    }
    assert response.cost_usd == pytest.approx(0.0012)
    url, headers, payload = calls[0]
    assert url.endswith("/gemini-3.7-flash:generateContent")
    assert headers["x-goog-api-key"] == "gemini-key"
    image_part = payload["contents"][0]["parts"][1]
    assert base64.b64decode(image_part["inlineData"]["data"]) == b"png-bytes"
    assert "mediaResolution" not in image_part
    assert "footer" in payload["contents"][0]["parts"][0]["text"]
    assert (
        payload["generationConfig"]["mediaResolution"]
        == "MEDIA_RESOLUTION_HIGH"
    )
    assert payload["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "LOW"
    }
    assert "temperature" not in payload["generationConfig"]


def test_gemini_page_reviewer_uses_strict_schema_and_parses_verdict() -> None:
    calls = []

    def post(url, headers, payload):
        calls.append(payload)
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "thought": True,
                                "text": "Compare the image region by region.",
                            },
                            {
                                "text": "```json\n"
                                + json.dumps(
                                    {
                                        "complete": False,
                                        "missing_regions": ["bottom paragraph"],
                                        "reading_order_errors": [],
                                        "duplicated_text": [],
                                        "reason": "The last paragraph is absent.",
                                    }
                                )
                                + "\n```"
                            }
                        ]
                    }
                }
            ],
                "usageMetadata": {
                    "promptTokenCount": 1500,
                    "candidatesTokenCount": 100,
                    "thoughtsTokenCount": 10,
                    "totalTokenCount": 1610,
                },
        }

    reviewer = GeminiLivePageReviewer(
        api_key=lambda: "gemini-key",
        post_json=post,
        budget=CostBudget(1.25),
    )
    page = RenderedPage(
        pdf_path=Path("issue.pdf"),
        pdf_hash="a" * 64,
        page_number=1,
        image_bytes=b"page-image",
        image_hash="b" * 64,
        width=100,
        height=200,
    )

    response = reviewer.review(page, "partial OCR", "Compare every region.")

    assert response.review["complete"] is False
    assert response.review["missing_regions"] == ["bottom paragraph"]
    config = calls[0]["generationConfig"]
    assert "temperature" not in config
    assert config["maxOutputTokens"] == 8192
    assert config["mediaResolution"] == "MEDIA_RESOLUTION_HIGH"
    assert config["thinkingConfig"] == {"thinkingLevel": "LOW"}
    assert config["responseMimeType"] == "application/json"
    assert set(config["responseJsonSchema"]["required"]) == {
        "complete",
        "missing_regions",
        "reading_order_errors",
        "duplicated_text",
        "reason",
    }
    prompt = calls[0]["contents"][0]["parts"][0]["text"]
    assert "partial OCR" in prompt
    assert "Compare every region." in prompt


def test_groq_client_forwards_strict_schema_reasoning_and_returns_envelope() -> None:
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                model=GROQ_MODEL,
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=json.dumps({"ok": True}))
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=2000,
                    completion_tokens=500,
                    total_tokens=2500,
                ),
            )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions())
    )
    adapter = GroqStructuredOutputClient(
        client_factory=lambda: client, budget=CostBudget(1.25)
    )
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "test",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        },
    }

    result = adapter.complete(
        {
            "model": GROQ_MODEL,
            "reasoning_effort": "medium",
            "instructions": "Judge only supplied evidence.",
            "article": {"text": "source"},
            "response_format": schema,
        }
    )

    assert result == {
        "output": {"ok": True},
        "usage": {
            "input_tokens": 2000,
            "output_tokens": 500,
            "total_tokens": 2500,
        },
        "cost_usd": pytest.approx(0.0006),
    }
    assert captured["model"] == GROQ_MODEL
    assert captured["reasoning_effort"] == "medium"
    assert captured["max_completion_tokens"] == 65_536
    assert captured["response_format"] == schema
    assert captured["messages"][0] == {
        "role": "system",
        "content": "Judge only supplied evidence.",
    }
    assert "source" in captured["messages"][1]["content"]


def test_gemini_ocr_allows_a_visually_verified_blank_page() -> None:
    provider = GeminiLiveOCRProvider(
        "gemini-3.7-flash",
        api_key=lambda: "gemini-key",
        post_json=lambda *_: {
            "candidates": [{"content": {"parts": [{"text": ""}]}}],
            "usageMetadata": {
                "promptTokenCount": 1120,
                "candidatesTokenCount": 0,
                "totalTokenCount": 1120,
            },
        },
        budget=CostBudget(1.25),
    )
    fixture = IssuePageOCRFixture(
        pdf_path=Path("issue.pdf"),
        pdf_sha256="a" * 64,
        page_number=1,
        fixture_class="good_control",
        human_scoring={},
        image_bytes=b"blank-page",
        image_hash="b" * 64,
        instructions="Transcribe everything.",
        target_regions=(),
    )

    assert provider.transcribe(fixture).text == ""


@pytest.mark.parametrize(
    "usage",
    [
        {"candidatesTokenCount": 10},
        {
            "promptTokenCount": 100,
            "candidatesTokenCount": 10,
            "totalTokenCount": 111,
        },
    ],
)
def test_gemini_rejects_unreconciled_usage_instead_of_recording_zero_cost(
    usage,
) -> None:
    provider = GeminiLiveOCRProvider(
        "gemini-3.7-flash",
        api_key=lambda: "gemini-key",
        post_json=lambda *_: {
            "candidates": [{"content": {"parts": [{"text": "text"}]}}],
            "usageMetadata": usage,
        },
        budget=CostBudget(1.25),
    )
    fixture = IssuePageOCRFixture(
        pdf_path=Path("issue.pdf"),
        pdf_sha256="a" * 64,
        page_number=1,
        fixture_class="good_control",
        human_scoring={},
        image_bytes=b"page",
        image_hash="b" * 64,
        instructions="Transcribe everything.",
        target_regions=(),
    )

    with pytest.raises(RuntimeError, match="provider_usage_invalid"):
        provider.transcribe(fixture)


def test_groq_rejects_unreconciled_usage_instead_of_undercounting_cost() -> None:
    class Completions:
        def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=json.dumps({"ok": True}))
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=100,
                    completion_tokens=10,
                    total_tokens=111,
                ),
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    adapter = GroqStructuredOutputClient(
        client_factory=lambda: client, budget=CostBudget(1.25)
    )

    with pytest.raises(RuntimeError, match="provider_usage_invalid"):
        adapter.complete(
            {
                "model": GROQ_MODEL,
                "reasoning_effort": "low",
                "instructions": "Return JSON.",
                "source": "text",
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "test",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {"ok": {"type": "boolean"}},
                            "required": ["ok"],
                            "additionalProperties": False,
                        },
                    },
                },
            }
        )


def test_budget_refuses_an_unsafe_call_before_contacting_provider() -> None:
    calls = []
    provider = GeminiLiveOCRProvider(
        "gemini-3.7-flash",
        api_key=lambda: "gemini-key",
        post_json=lambda *args: calls.append(args),
        budget=CostBudget(0.01),
    )
    fixture = IssuePageOCRFixture(
        pdf_path=Path("issue.pdf"),
        pdf_sha256="a" * 64,
        page_number=1,
        fixture_class="good_control",
        human_scoring={},
        image_bytes=b"page",
        image_hash="b" * 64,
        instructions="Transcribe everything.",
        target_regions=(),
    )

    with pytest.raises(RuntimeError, match="cost_ceiling_would_be_exceeded"):
        provider.transcribe(fixture)
    assert calls == []


def test_budgeted_extractor_accounts_normalized_legacy_usage(monkeypatch) -> None:
    computation = namedtuple("Computation", "usage cost_usd")(
        {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        None,
    )
    monkeypatch.setattr(
        "propositions.extract_propositions_with_evidence",
        lambda **_kwargs: computation,
    )
    budget = CostBudget(1.25)

    result = _budgeted_proposition_extractor(budget)(text="article")

    assert result.cost_usd == pytest.approx(0.000027)
    assert budget.spent_usd == pytest.approx(0.000027)


@pytest.mark.parametrize("value", [None, "1.26", "not-a-number"])
def test_live_factory_budget_is_required_and_cannot_exceed_approval(value) -> None:
    environ = {}
    if value is not None:
        environ["MAGAZINE_REVIEW_COST_CEILING_USD"] = value

    with pytest.raises(RuntimeError, match="cost_ceiling_(required|invalid)"):
        _cost_budget(environ)


def test_failed_paid_call_keeps_its_reservation_and_blocks_reuse() -> None:
    calls = []
    budget = CostBudget(0.05)

    def fail(*args):
        calls.append(args)
        raise RuntimeError("network failed after contact")

    provider = GeminiLiveOCRProvider(
        "gemini-3.7-flash",
        api_key=lambda: "gemini-key",
        post_json=fail,
        budget=budget,
    )
    fixture = IssuePageOCRFixture(
        pdf_path=Path("issue.pdf"),
        pdf_sha256="a" * 64,
        page_number=1,
        fixture_class="good_control",
        human_scoring={},
        image_bytes=b"page",
        image_hash="b" * 64,
        instructions="Transcribe everything.",
        target_regions=(),
    )

    with pytest.raises(RuntimeError, match="network failed"):
        provider.transcribe(fixture)
    with pytest.raises(RuntimeError, match="cost_ceiling_would_be_exceeded"):
        provider.transcribe(fixture)
    assert len(calls) == 1


def test_groq_client_disables_hidden_sdk_retries(monkeypatch) -> None:
    captured = {}

    def fake_groq(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("groq.Groq", fake_groq)

    first = _groq_factory(lambda: "groq-key")()

    assert first is not None
    assert captured == {"api_key": "groq-key", "max_retries": 0}


def test_invalid_gemini_review_records_bounded_page_diagnostic() -> None:
    invalid_response = "preface\n\u2603" + ("\U0001f642" * 400)

    with pytest.raises(RuntimeError) as raised:
        _page_review_json(invalid_response, page_number=7)

    message = str(raised.value)
    assert message.startswith("gemini_review_json_invalid:page=7:sha256=")
    preview = message.split(":preview=", 1)[1]
    assert preview.startswith(r"preface\n\u2603")
    assert len(preview) <= 400
    assert not preview.endswith(("\\", "\\U", "\\U0", "\\U00", "\\U000"))
