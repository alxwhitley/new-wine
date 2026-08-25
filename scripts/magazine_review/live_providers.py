"""Live, lazy provider adapters for the attended magazine review pipeline."""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .benchmark import BenchmarkCandidate, OCRResponse
from .ocr import IssuePageOCRFixture, PageReviewResponse, RenderedPage


GEMINI_REVIEW_MODEL = "gemini-3.6-flash"
GROQ_MODEL = "openai/gpt-oss-120b"
PRICING_VERIFIED_ON = "2026-08-25"
GEMINI_PRICES_USD_PER_MILLION = {
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.7-flash": (0.75, 3.75),
}
GROQ_PRICES_USD_PER_MILLION = {GROQ_MODEL: (0.15, 0.60)}
_GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
_REPO_ROOT = Path(__file__).resolve().parents[2]

PostJSON = Callable[[str, Mapping[str, str], Mapping[str, object]], Mapping[str, Any]]


class LiveProviderError(RuntimeError):
    """Raised when a live provider cannot return trustworthy evidence."""


def _read_dotenv_value(path: Path, name: str) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        return value.strip().strip('"').strip("'") or None
    return None


def _credential(name: str, environ: Mapping[str, str] | None) -> Callable[[], str]:
    def get() -> str:
        value = (os.environ if environ is None else environ).get(name)
        if not value and environ is None:
            value = _read_dotenv_value(_REPO_ROOT / "backend/app/.env", name)
        if not value:
            raise LiveProviderError(f"{name.lower()}_required")
        return value

    return get


def _post_json(
    url: str, headers: Mapping[str, str], payload: Mapping[str, object]
) -> Mapping[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=dict(headers),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, Mapping):
        raise LiveProviderError("provider_response_invalid")
    return parsed


def _required_token(
    raw: Mapping[str, object], names: tuple[str, ...], *, positive: bool
) -> int:
    for name in names:
        value = raw.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            if positive and value == 0:
                break
            return value
    raise LiveProviderError("provider_usage_invalid")


def _gemini_usage(raw: object) -> dict[str, int]:
    if not isinstance(raw, Mapping):
        raise LiveProviderError("provider_usage_missing")
    input_tokens = _required_token(raw, ("promptTokenCount",), positive=True)
    visible_output = _required_token(
        raw, ("candidatesTokenCount",), positive=False
    )
    raw_thoughts = raw.get("thoughtsTokenCount", 0)
    if (
        not isinstance(raw_thoughts, int)
        or isinstance(raw_thoughts, bool)
        or raw_thoughts < 0
    ):
        raise LiveProviderError("provider_usage_invalid")
    output_tokens = visible_output + raw_thoughts
    total_tokens = _required_token(raw, ("totalTokenCount",), positive=True)
    if total_tokens != input_tokens + output_tokens:
        raise LiveProviderError("provider_usage_invalid")
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _groq_usage(raw: object) -> dict[str, int]:
    if not isinstance(raw, Mapping):
        raise LiveProviderError("provider_usage_missing")
    input_tokens = _required_token(raw, ("prompt_tokens",), positive=True)
    output_tokens = _required_token(raw, ("completion_tokens",), positive=False)
    total_tokens = _required_token(raw, ("total_tokens",), positive=True)
    if total_tokens != input_tokens + output_tokens:
        raise LiveProviderError("provider_usage_invalid")
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _cost(
    usage: Mapping[str, int], input_rate: float, output_rate: float
) -> float:
    return (
        usage["input_tokens"] * input_rate
        + usage["output_tokens"] * output_rate
    ) / 1_000_000


def _gemini_text(response: Mapping[str, Any], *, allow_empty: bool) -> str:
    try:
        parts = response["candidates"][0]["content"]["parts"]
        if not isinstance(parts, list) or any(
            not isinstance(part, Mapping) for part in parts
        ):
            raise TypeError("parts_invalid")
        text = "".join(part.get("text", "") for part in parts).strip()
    except (AttributeError, KeyError, IndexError, TypeError) as exc:
        raise LiveProviderError("gemini_response_invalid") from exc
    if not text and not allow_empty:
        raise LiveProviderError("gemini_text_missing")
    return text


def _image_part(image_bytes: bytes) -> dict[str, object]:
    return {
        "inlineData": {
            "mimeType": "image/png",
            "data": base64.b64encode(image_bytes).decode("ascii"),
        },
    }


class _GeminiBoundary:
    def __init__(
        self,
        model: str,
        *,
        api_key: Callable[[], str],
        post_json: PostJSON = _post_json,
    ) -> None:
        if model not in GEMINI_PRICES_USD_PER_MILLION:
            raise LiveProviderError("gemini_model_unsupported")
        self.model = model
        self._api_key = api_key
        self._post_json = post_json

    def _generate(
        self, payload: Mapping[str, object], *, allow_empty: bool = False
    ) -> tuple[str, dict[str, int], float]:
        response = self._post_json(
            f"{_GEMINI_API_ROOT}/{self.model}:generateContent",
            {
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key(),
            },
            payload,
        )
        usage = _gemini_usage(response.get("usageMetadata"))
        input_rate, output_rate = GEMINI_PRICES_USD_PER_MILLION[self.model]
        return (
            _gemini_text(response, allow_empty=allow_empty),
            usage,
            _cost(usage, input_rate, output_rate),
        )


class GeminiLiveOCRProvider(_GeminiBoundary):
    """Full-page Gemini OCR with high-resolution image processing."""

    def __init__(
        self,
        model: str,
        *,
        api_key: Callable[[], str],
        post_json: PostJSON = _post_json,
    ) -> None:
        super().__init__(model, api_key=api_key, post_json=post_json)
        self.candidate = BenchmarkCandidate(provider="Gemini", model=model)

    def transcribe(self, fixture: IssuePageOCRFixture) -> OCRResponse:
        prompt = fixture.instructions
        if fixture.target_regions:
            prompt += "\nCompleteness-review targets: " + "; ".join(
                fixture.target_regions
            )
        text, usage, cost = self._generate(
            {
                "contents": [
                    {"parts": [{"text": prompt}, _image_part(fixture.image_bytes)]}
                ],
                "generationConfig": {
                    "maxOutputTokens": 8192,
                    "thinkingConfig": {"thinkingLevel": "LOW"},
                    "mediaResolution": "MEDIA_RESOLUTION_HIGH",
                },
            },
            allow_empty=True,
        )
        return OCRResponse(text=text, usage=usage, cost_usd=cost)


_PAGE_REVIEW_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "complete": {"type": "boolean"},
        "missing_regions": {"type": "array", "items": {"type": "string"}},
        "reading_order_errors": {
            "type": "array",
            "items": {"type": "string"},
        },
        "duplicated_text": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": [
        "complete",
        "missing_regions",
        "reading_order_errors",
        "duplicated_text",
        "reason",
    ],
    "additionalProperties": False,
}


class GeminiLivePageReviewer(_GeminiBoundary):
    """Fresh image-to-OCR completeness check for each rendered page."""

    def __init__(
        self,
        *,
        api_key: Callable[[], str],
        post_json: PostJSON = _post_json,
    ) -> None:
        super().__init__(GEMINI_REVIEW_MODEL, api_key=api_key, post_json=post_json)

    def review(
        self, page: RenderedPage, ocr_text: str, instructions: str
    ) -> PageReviewResponse:
        prompt = f"{instructions}\n\nOCR TEXT TO VERIFY:\n{ocr_text}"
        text, usage, cost = self._generate(
            {
                "contents": [
                    {"parts": [{"text": prompt}, _image_part(page.image_bytes)]}
                ],
                "generationConfig": {
                    "maxOutputTokens": 2048,
                    "mediaResolution": "MEDIA_RESOLUTION_HIGH",
                    "responseMimeType": "application/json",
                    "responseJsonSchema": _PAGE_REVIEW_SCHEMA,
                },
            }
        )
        try:
            review = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LiveProviderError("gemini_review_json_invalid") from exc
        if not isinstance(review, dict):
            raise LiveProviderError("gemini_review_shape_invalid")
        return PageReviewResponse(review=review, usage=usage, cost_usd=cost)


class GroqStructuredOutputClient:
    """Stateless strict-JSON client for article and proposition review."""

    model = GROQ_MODEL

    def __init__(self, *, client_factory: Callable[[], object]) -> None:
        self._client_factory = client_factory

    def complete(self, request: dict[str, object]) -> Mapping[str, object]:
        if request.get("model") != self.model:
            raise LiveProviderError("groq_model_mismatch")
        instructions = request.get("instructions")
        response_format = request.get("response_format")
        reasoning_effort = request.get("reasoning_effort")
        if not isinstance(instructions, str) or not isinstance(response_format, dict):
            raise LiveProviderError("groq_request_invalid")
        evidence = {
            key: value
            for key, value in request.items()
            if key
            not in {
                "model",
                "instructions",
                "response_format",
                "reasoning_effort",
                "fresh_context",
            }
        }
        response = self._client_factory().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": json.dumps(
                        evidence, ensure_ascii=False, separators=(",", ":")
                    ),
                },
            ],
            reasoning_effort=reasoning_effort,
            response_format=response_format,
            temperature=0,
        )
        try:
            output = json.loads(response.choices[0].message.content)
        except (AttributeError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LiveProviderError("groq_response_invalid") from exc
        raw_usage = getattr(response, "usage", None)
        usage_mapping = getattr(raw_usage, "__dict__", raw_usage)
        usage = _groq_usage(usage_mapping)
        input_rate, output_rate = GROQ_PRICES_USD_PER_MILLION[self.model]
        return {
            "output": output,
            "usage": usage,
            "cost_usd": _cost(usage, input_rate, output_rate),
        }


def _groq_factory(api_key: Callable[[], str]) -> Callable[[], object]:
    client: object | None = None

    def get() -> object:
        nonlocal client
        if client is None:
            from groq import Groq

            client = Groq(api_key=api_key())
        return client

    return get


def build_live_provider_adapters(
    decision: object, *, environ: Mapping[str, str] | None = None
) -> object:
    """Build the CLI adapter bundle without loading credentials or making calls."""
    from review_magazine_issue import ProviderAdapters

    candidate = getattr(decision, "accepted_candidate", None)
    if candidate != BenchmarkCandidate(provider="Gemini", model="gemini-3.7-flash"):
        raise LiveProviderError("accepted_ocr_candidate_unsupported")
    gemini_key = _credential("GEMINI_API_KEY", environ)
    groq_key = _credential("GROQ_API_KEY", environ)
    groq_factory = _groq_factory(groq_key)
    return ProviderAdapters(
        initial_ocr_provider=GeminiLiveOCRProvider(
            candidate.model, api_key=gemini_key
        ),
        page_reviewer=GeminiLivePageReviewer(api_key=gemini_key),
        repair_ocr_provider=GeminiLiveOCRProvider(
            GEMINI_REVIEW_MODEL, api_key=gemini_key
        ),
        article_client=GroqStructuredOutputClient(client_factory=groq_factory),
        proposition_reviewer=GroqStructuredOutputClient(
            client_factory=groq_factory
        ),
        proposition_extractor=None,
        proposition_extractor_model=GROQ_MODEL,
    )
