"""Search-question topic classification against the closed taxonomy.

Runs AFTER answer completion, in the finalizer (never on the answer path
itself -- CLAUDE.md's standing rule against model judges on served answers
does not apply here: this never touches the answer, only labels an
already-final question for a dashboard). Model output is untrusted: the
returned label is validated against app.constants.VALID_TAGS (the
backend's synced copy of the canonical scripts/taxonomy.py, Task 1) and
forced to "Unclassified" on any unknown label or low confidence -- never
passed through to storage unchecked.

Same model assignment as this codebase's other classification/extraction
work (CLAUDE.md tech stack table): Groq openai/gpt-oss-120b. Same
prompt-then-parse-then-fence-strip convention as scripts/propositions.py's
extract_propositions() -- no native JSON tool-calling exists anywhere else
in this repo to diverge from.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Optional

from groq import Groq

from app.constants import VALID_TAGS

CLASSIFIER_VERSION = "search_topic_v1"
CLASSIFIER_MODEL = "openai/gpt-oss-120b"
CONFIDENCE_THRESHOLD = 0.70
UNCLASSIFIED = "Unclassified"

_PROMPT_TEMPLATE = (
    "Classify the following user question into EXACTLY ONE topic from this "
    "closed list. Respond with ONLY a JSON object of the shape "
    '{{"topic": "<exact topic from the list>", "confidence": <0.0-1.0>}} '
    "and nothing else. If no topic in the list genuinely fits, use the "
    'literal string "Unclassified" as the topic.\n\n'
    "Topics:\n{topics}\n\n"
    "Question: {question}"
)


class ClassificationFailedError(Exception):
    """The model call or its output could not be parsed into a usable
    result -- the finalizer treats this as retryable, never a crash."""


@dataclass(frozen=True)
class ClassificationResult:
    topic: str
    confidence: float
    model: str
    prompt_version: str
    prompt_fingerprint: str


def _prompt_fingerprint() -> str:
    return hashlib.sha256(_PROMPT_TEMPLATE.encode("utf-8")).hexdigest()


_groq_client: Optional[Groq] = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


def _strip_fences(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def classify_topic(question: str) -> ClassificationResult:
    topics_block = "\n".join("- %s" % t for t in sorted(VALID_TAGS))
    prompt = _PROMPT_TEMPLATE.format(topics=topics_block, question=question)

    try:
        client = _get_groq()
        response = client.chat.completions.create(
            model=CLASSIFIER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200,
        )
        raw = _strip_fences(response.choices[0].message.content)
        parsed = json.loads(raw)
        model_used = getattr(response, "model", None) or CLASSIFIER_MODEL
    except Exception as exc:
        raise ClassificationFailedError(str(exc)) from exc

    raw_topic = parsed.get("topic") if isinstance(parsed, dict) else None
    raw_confidence = parsed.get("confidence") if isinstance(parsed, dict) else None
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    # Untrusted output: only a label that exactly matches the closed
    # taxonomy AND clears the confidence floor is ever stored as-is.
    if raw_topic in VALID_TAGS and confidence >= CONFIDENCE_THRESHOLD:
        topic = raw_topic
    else:
        topic = UNCLASSIFIED

    return ClassificationResult(
        topic=topic,
        confidence=confidence,
        model=model_used,
        prompt_version=CLASSIFIER_VERSION,
        prompt_fingerprint=_prompt_fingerprint(),
    )
