#!/usr/bin/env python3
"""
test_stored_position_evidence.py -- regression tests for the Project 2
one-hop evidence-injection module
(backend/app/services/stored_position_evidence.py). This is the second half
of the sequence test_stored_position_topics.py's own docstring named as
"not built" -- match_stored_position() (tested there) resolves a question to
a topic_key; fetch_stored_position_evidence() (tested here) resolves a
topic_key to chunk-compatible evidence, or None.

Mirrors this repo's ad hoc scripts/test_*.py convention -- no pytest, hand-
built `_check(label, condition)` assertions, a `main()` that runs everything
(see test_stored_position_topics.py, whose shape this file was built to
mirror).

Tier A (deterministic, still opens a real read-only connection since
positions is a real table with nothing to fake, but stable regardless of
corpus/source state): a nonexistent topic_key can never match a row -> None.

Tier B (live, read-only DB, ZERO writes; skips cleanly if creds absent):
exercises fetch_stored_position_evidence() against the real live positions
table for all six V1 topic_keys, asserting against the ACTUAL live
contributor data confirmed 2026-08-08 (build session for this file) -- not a
hypothetical:
  - "the divine exchange at the cross" and "holiness and personal purity"
    are both 100% Derek Prince (unlicensed/shown) -> full evidence survives
    the live license gate.
  - "fasting", "deliverance from demons and spiritual warfare", and
    "how to pray effectively" are all 100% Vlad Savchuk, who is currently
    unlicensed/HIDDEN -> every evidence proposition is filtered by the live
    gate -> fetch returns None (fail-safe fall-through to normal RAG, not a
    bug).
  - "can a believer lose their salvation" (corpus scope) mixes Vlad Savchuk,
    Derek Prince, Leonard Ravenhill (hidden), and Doug Kreighbaum -> only
    the Prince + Kreighbaum evidence survives; Savchuk/Ravenhill are
    dropped.
Also checks: every surviving chunk has the expected shape (id, content,
document_id present); no surviving chunk is ever commentary/word_study
kind; no surviving chunk's author is ever a currently-hidden source name.

This test is a snapshot of live corpus/source state at write time (CLAUDE.md
Phase 1.3 will eventually unhide Savchuk/Ravenhill, which will change which
topics show non-None results). If Tier B assertions about WHICH topics
return None start failing, check sources.visibility for Savchuk/Ravenhill
before assuming a code regression -- see is_source_servable().

Run: python3 scripts/test_stored_position_evidence.py
"""
import logging
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent / "backend"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_BACKEND / "app" / ".env")

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

from app.services import stored_position_evidence as spe  # noqa: E402
from app.services import answer_toolbox  # noqa: E402

failures = []


def _check(label, condition):
    status = "OK" if condition else "FAIL"
    print(f"  {status}: {label}")
    if not condition:
        failures.append(label)


def _have_creds():
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- nonexistent topic_key -> None
# ═══════════════════════════════════════════════════════════════════════════

def test_nonexistent_topic_key_returns_none():
    print("\n" + "=" * 78)
    print("Tier A: nonexistent topic_key -> None")
    print("=" * 78)
    if not _have_creds():
        print("  Skipping -- SUPABASE_URL / SUPABASE_SERVICE_KEY not set.")
        return
    from app.db.supabase import get_supabase
    db = get_supabase()
    _check(
        "'nonexistent topic key xyz' -> None",
        spe.fetch_stored_position_evidence(db, "nonexistent topic key xyz") is None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Tier B -- live, read-only, ZERO writes. Against real corpus/source state.
# ═══════════════════════════════════════════════════════════════════════════

# Expected live behavior as of 2026-08-08 (see module docstring). Topics
# whose sole/partial contributor set survives the live license gate ->
# non-empty evidence expected. Topics whose sole contributor is currently
# hidden -> None expected (fail-safe, not a bug).
EXPECTED_NON_NONE = {
    "the divine exchange at the cross",
    "holiness and personal purity",
    "can a believer lose their salvation",
}
EXPECTED_NONE_TODAY = {
    "fasting",
    "deliverance from demons and spiritual warfare",
    "how to pray effectively",
}

# Currently-hidden contributors to these positions (CLAUDE.md Phase 1.3) --
# must NEVER appear as a surviving chunk's author.
HIDDEN_AUTHOR_NAMES = {"Vlad Savchuk", "Leonard Ravenhill"}

ALL_SIX_TOPIC_KEYS = (
    "fasting",
    "deliverance from demons and spiritual warfare",
    "how to pray effectively",
    "the divine exchange at the cross",
    "can a believer lose their salvation",
    "holiness and personal purity",
)


def _run_tier_b():
    print("\n" + "=" * 78)
    print("Tier B: fetch_stored_position_evidence() over the six V1 topics (read-only)")
    print("=" * 78)

    if not _have_creds():
        print("  Skipping Tier B -- SUPABASE_URL / SUPABASE_SERVICE_KEY not set.")
        return

    from app.db.supabase import get_supabase
    db = get_supabase()

    for topic_key in ALL_SIX_TOPIC_KEYS:
        result = spe.fetch_stored_position_evidence(db, topic_key)
        if topic_key in EXPECTED_NON_NONE:
            _check(f"{topic_key!r} -> non-empty evidence", bool(result))
            if result:
                for c in result:
                    _check(
                        f"{topic_key!r} chunk has required shape (id/content/document_id)",
                        all(c.get(k) for k in ("id", "content", "document_id")),
                    )
                    _check(
                        f"{topic_key!r} chunk author {c.get('author')!r} is never a hidden contributor",
                        c.get("author") not in HIDDEN_AUTHOR_NAMES,
                    )
                    _check(
                        f"{topic_key!r} chunk is never commentary/word_study",
                        not answer_toolbox.is_commentary_chunk(c),
                    )
        elif topic_key in EXPECTED_NONE_TODAY:
            _check(
                f"{topic_key!r} -> None today (sole contributor currently hidden, fail-safe)",
                result is None,
            )
        else:
            _check(f"unexpected topic_key in test set: {topic_key!r}", False)


def main():
    print("#" * 78)
    print("test_stored_position_evidence.py")
    print("#" * 78)

    test_nonexistent_topic_key_returns_none()
    _run_tier_b()

    print("\n" + "#" * 78)
    if failures:
        print(f"{len(failures)} FAILURE(S): " + ", ".join(failures))
    else:
        print("All assertions passed.")
    print("#" * 78)

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
