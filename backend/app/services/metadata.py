import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def extract_metadata(text: str) -> dict:
    words = text.split()[:1000]
    sample = " ".join(words)

    try:
        message = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
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
        logger.exception("Anthropic metadata extraction call failed")
        raise

    raw = message.content[0].text
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)
