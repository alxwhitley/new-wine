import json
import logging
import os

from groq import Groq

logger = logging.getLogger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def extract_metadata(text: str) -> dict:
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
    return result
