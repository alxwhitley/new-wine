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
table for all six V1 topic_keys. It deliberately avoids snapshotting which
contributors happen to be shown or hidden: visibility is mutable production
state, so a correct result may change between None and non-empty without a
code regression. Instead it verifies the durable contract: never return an
empty list; every surviving chunk has the expected shape; every surviving
chunk's source passes the current live servability predicate; and no
surviving chunk is commentary/word_study content.

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
from app.services.source_resolver import is_source_servable  # noqa: E402

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
    servable_by_source = {}

    for topic_key in ALL_SIX_TOPIC_KEYS:
        result = spe.fetch_stored_position_evidence(db, topic_key)
        _check(
            f"{topic_key!r} returns None or a non-empty list",
            result is None or (isinstance(result, list) and bool(result)),
        )
        if result:
            document_ids = sorted({c.get("document_id") for c in result if c.get("document_id")})
            documents = (
                db.table("documents")
                .select("id, source_id")
                .in_("id", document_ids)
                .execute()
                .data
                or []
            )
            source_id_by_document = {d["id"]: d.get("source_id") for d in documents}
            for c in result:
                source_id = source_id_by_document.get(c.get("document_id"))
                if source_id and source_id not in servable_by_source:
                    servable_by_source[source_id] = is_source_servable(db, source_id)
                _check(
                    f"{topic_key!r} chunk has required shape (id/content/document_id)",
                    all(c.get(k) for k in ("id", "content", "document_id")),
                )
                _check(
                    f"{topic_key!r} chunk source is currently servable",
                    bool(source_id) and servable_by_source.get(source_id, False),
                )
                _check(
                    f"{topic_key!r} chunk is never commentary/word_study",
                    not answer_toolbox.is_commentary_chunk(c),
                )
        else:
            _check(
                f"{topic_key!r} fail-safe None is accepted when no evidence is currently servable",
                result is None,
            )


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
