import json
import logging
import os
from typing import Dict, NamedTuple, Optional

from groq import Groq

logger = logging.getLogger(__name__)

GROQ_MODEL = "openai/gpt-oss-120b"

_client = None


class MetadataComputation(NamedTuple):
    output: dict
    model: str
    usage: Optional[Dict[str, int]]
    cost_usd: Optional[float]


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def _response_usage(response) -> Optional[Dict[str, int]]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    fields = (
        ("input_tokens", "input_tokens", "prompt_tokens"),
        ("output_tokens", "output_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    )
    normalized = {}
    for destination, *candidates in fields:
        for candidate in candidates:
            value = getattr(usage, candidate, None)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                normalized[destination] = value
                break
    return normalized or None


def extract_metadata_with_evidence(text: str) -> MetadataComputation:
    words = text.split()[:1000]
    sample = " ".join(words)

    try:
        response = _get_client().chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract metadata from this text. Return ONLY valid JSON with these fields: "
                        "title, author, source_type, source_name, year, topic_tags. "
                        "source_type should be one of: book, article, sermon, commentary, essay, letter, other. "
                        "topic_tags should be a list of strings. "
                        "Use null for anything you cannot confidently determine.\n\n"
                        f"Text:\n{sample}"
                    ),
                }
            ],
        )
    except Exception:
        logger.exception("Groq metadata extraction call failed")
        raise

    raw = response.choices[0].message.content or ""
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    result = json.loads(raw)
    st = result.get("source_type", "")
    if st == "sermon":
        result["source_kind"] = "sermon_transcript"
        result["citation_mode"] = "citable"
    elif st == "background":
        result["source_kind"] = "background_note"
        result["citation_mode"] = "silent_context"
    else:
        result["source_kind"] = "unknown"
        result["citation_mode"] = "silent_context"
    raw_cost = getattr(response, "cost_usd", None)
    cost_usd = (
        float(raw_cost)
        if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool)
        else None
    )
    return MetadataComputation(
        output=result,
        model=getattr(response, "model", None) or GROQ_MODEL,
        usage=_response_usage(response),
        cost_usd=cost_usd,
    )


def extract_metadata(text: str) -> dict:
    """Legacy metadata API; evidence-aware callers use the companion boundary."""
    return extract_metadata_with_evidence(text).output
