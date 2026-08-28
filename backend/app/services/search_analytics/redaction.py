"""Deterministic, local, versioned redaction for a no_material question
before it is ever persisted (CLAUDE.md Settled decision, this session's
directive -- redaction runs BEFORE the only storage write, never after).

Only strips OBVIOUS direct identifiers: email, phone, street address,
IPv4/IPv6, UUID-shaped account identifiers. Deliberately does NOT touch
capitalized words generally -- teacher names (Derek Prince, Andrew Murray)
and biblical/theological terms must survive, since the whole point of
storing this text is to let an admin diagnose a real content gap. A
blind name-stripper would defeat that purpose for exactly the questions
this exists to preserve.

Never partially redacts on failure: a regex engine exception returns
status="redaction_failed" with text=None, never a half-redacted string.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

REDACTION_VERSION = "v1"

_MAX_STORED_LENGTH = 500

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# US-style phone numbers: optional country code, area code in parens or
# plain, separators of space/dot/dash. Deliberately permissive -- false
# positives here (stripping a non-phone digit run) are an acceptable cost
# against the alternative of leaving a real phone number in stored text.
_PHONE_RE = re.compile(
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# IPv6, including "::" zero-compression -- a lookahead requires at least
# two colons before matching a run of hex digits/colons, so a bare Bible
# reference or ordinary word never matches (those never contain 2+ colons).
_IPV6_RE = re.compile(r"\b(?=(?:[0-9a-fA-F]*:){2,})[0-9a-fA-F:]{2,45}\b")

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# Street address: a leading number followed by 1-4 title-cased/word tokens
# and a common street-suffix word. Conservative on purpose -- a missed
# address is a smaller harm than corrupting ordinary Bible-reference-shaped
# text ("Romans 8 verse 28") by treating any digit-plus-word run as an
# address.
_STREET_SUFFIXES = (
    r"Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|"
    r"Terrace|Way|Place|Pl|Circle|Cir"
)
_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+(?:[A-Z][a-zA-Z]*\s+){1,4}(?:%s)\b\.?" % _STREET_SUFFIXES
)

_REDACTED_TOKEN = "[redacted]"


@dataclass(frozen=True)
class RedactionResult:
    text: Optional[str]
    status: str  # "redacted" | "redaction_failed"


def redact_question(text: str) -> RedactionResult:
    try:
        redacted = text
        for pattern in (_EMAIL_RE, _ADDRESS_RE, _IPV6_RE, _IPV4_RE, _PHONE_RE, _UUID_RE):
            redacted = pattern.sub(_REDACTED_TOKEN, redacted)
        redacted = redacted[:_MAX_STORED_LENGTH]
        return RedactionResult(text=redacted, status="redacted")
    except Exception:
        return RedactionResult(text=None, status="redaction_failed")
