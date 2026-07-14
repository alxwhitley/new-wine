"""
A fixed, manually curated reject list of biblical-figure names. A name on
this list can NEVER resolve as a teacher pointer, independent of whether it
also happens to match a real, servable source in source_aliases — this is a
deliberate second guard (see docs/superpowers/plans/2026-07-14-sp1-reference-pointer-backend.md),
not a substitute for the license/visibility gate.

Matching is EXACT on the normalized string, not substring — "paul" is
rejected, but "paul washer" (a distinct full name) is not, so a real corpus
teacher whose full name happens to start with a biblical first name is
unaffected.

This list is intentionally bounded to major, commonly-referenced figures.
Known limitation: it will not catch every obscure biblical name. Extend it
if a future test case or real usage surfaces a gap — do not treat this as
exhaustive.
"""
from __future__ import annotations

from app.services.source_resolver import normalize_alias_key

_BIBLICAL_FIGURE_NAMES = [
    # Patriarchs / OT narrative
    "adam", "eve", "noah", "abraham", "sarah", "isaac", "rebekah", "jacob",
    "rachel", "leah", "joseph", "moses", "aaron", "miriam", "joshua", "caleb",
    "deborah", "gideon", "samson", "ruth", "naomi", "samuel", "saul", "david",
    "bathsheba", "solomon", "elijah", "elisha", "job", "esther", "mordecai",
    "nehemiah", "ezra",
    # OT prophets
    "isaiah", "jeremiah", "ezekiel", "daniel", "hosea", "joel", "amos",
    "obadiah", "jonah", "micah", "nahum", "habakkuk", "zephaniah", "haggai",
    "zechariah", "malachi",
    # NT — gospels and epistles
    "mary", "elizabeth", "john the baptist", "jesus", "peter", "andrew",
    "james", "john", "philip", "bartholomew", "thomas", "matthew",
    "thaddaeus", "simon", "judas", "paul", "barnabas", "silas", "timothy",
    "titus", "luke", "mark", "stephen", "cornelius", "lydia", "priscilla",
    "aquila", "apollos", "lazarus", "martha", "nicodemus", "zacchaeus",
    "mary magdalene",
]

BIBLICAL_FIGURE_KEYS = frozenset(normalize_alias_key(n) for n in _BIBLICAL_FIGURE_NAMES)


def is_biblical_figure(name: str) -> bool:
    """Exact-match (post-normalization) check against the reject list."""
    return normalize_alias_key(name) in BIBLICAL_FIGURE_KEYS
