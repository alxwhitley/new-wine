from __future__ import annotations

import os
from pathlib import Path

import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

_anthropic_client = None
_guardrails_text = None


def get_anthropic_client():
    # type: () -> anthropic.Anthropic
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def get_guardrails_text() -> str:
    """Theological guardrails text, shared by every LLM call in this backend
    that represents a source document's or teacher's views (chat.py's main
    answer stream, study.py's teacher-position synthesis). Loaded once, from
    the same theological_guardrails.txt file the main answer stream has
    always used.
    """
    global _guardrails_text
    if _guardrails_text is None:
        app_dir = Path(__file__).resolve().parent.parent
        _guardrails_text = (app_dir / "theological_guardrails.txt").read_text() + (
            "\n\nRepresent the views of the source documents faithfully and accurately, "
            "even when those views reflect traditional or complementarian theology. "
            "Do not editorialize or add modern qualifications unless they appear in the source material."
        )
    return _guardrails_text
