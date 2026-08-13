#!/usr/bin/env python3
"""
test_commentary_answer_exclusion.py -- Settled decision #5: commentaries are
excluded from answers; searchable only (Study Mode unchanged).

Tier A only (deterministic, no DB/network): proves is_commentary_chunk /
exclude_commentary_chunks and that the score-dict filter used at chat Step
2.6 / producer mirror drops every commentary row before collapse/rerank.

Run: python3 scripts/test_commentary_answer_exclusion.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Moved out of app.routers.chat into app.services.answer_toolbox 2026-08-07
# (mirror-unification batch 1); chat.py imports these from the same place.
from app.services.answer_toolbox import (  # noqa: E402
    is_commentary_chunk,
    exclude_commentary_chunks,
    SOURCE_KIND_FUSION_WEIGHTS,
)

failures = []  # type: list


def _check(label, condition):
    # type: (str, bool) -> None
    if condition:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        failures.append(label)


def test_is_commentary_chunk():
    print("\n== is_commentary_chunk ==")
    _check(
        "source_kind=commentary",
        is_commentary_chunk({"source_kind": "commentary", "source_type": "other"}),
    )
    _check(
        "source_type=commentary when kind missing",
        is_commentary_chunk({"source_type": "commentary"}),
    )
    _check(
        "source_kind wins over source_type",
        is_commentary_chunk({"source_kind": "commentary", "source_type": "sermon"}),
    )
    _check(
        "sermon is not commentary",
        not is_commentary_chunk({"source_kind": "sermon_transcript", "source_type": "sermon"}),
    )
    _check(
        "book is not commentary",
        not is_commentary_chunk({"source_kind": "book", "source_type": "book"}),
    )
    _check(
        "empty chunk is not commentary",
        not is_commentary_chunk({}),
    )
    _check(
        "lexicon is not commentary",
        not is_commentary_chunk({"source_kind": "lexicon"}),
    )
    _check(
        "word_study IS commentary-equivalent (Precept Austin leak, found 2026-08-07)",
        is_commentary_chunk({"source_kind": "word_study", "source_type": "background"}),
    )
    _check(
        "word_study excluded even when citation_mode=citable (the leak's exact shape)",
        is_commentary_chunk({"source_kind": "word_study", "citation_mode": "citable"}),
    )


def test_exclude_commentary_chunks():
    print("\n== exclude_commentary_chunks ==")
    chunks = [
        {"id": "1", "source_kind": "sermon_transcript", "content": "a"},
        {"id": "2", "source_kind": "commentary", "content": "b"},
        {"id": "3", "source_type": "commentary", "content": "c"},
        {"id": "4", "source_kind": "book", "content": "d"},
        {"id": "5", "source_kind": "commentary", "content": "e"},
        {"id": "6", "source_kind": "word_study", "source_type": "background", "content": "f"},
    ]
    out = exclude_commentary_chunks(chunks)
    _check("drops all commentary + word_study", len(out) == 2)
    _check("keeps sermon + book ids", [c["id"] for c in out] == ["1", "4"])
    _check("order preserved", out[0]["id"] == "1" and out[1]["id"] == "4")
    _check("idempotent", exclude_commentary_chunks(out) == out)
    _check("empty in → empty out", exclude_commentary_chunks([]) == [])


def test_score_dict_filter_mirrors_step_26():
    """Exact filter shape used at chat.py Step 2.6 / producer mirror."""
    print("\n== score-dict filter (Step 2.6 shape) ==")
    all_scores = {
        "a": (1.0, {"source_kind": "sermon_transcript"}),
        "b": (0.9, {"source_kind": "commentary"}),
        "c": (0.8, {"source_type": "commentary"}),
        "d": (0.7, {"source_kind": "book"}),
        "e": (0.6, {"source_kind": "word_study", "citation_mode": "citable"}),
    }
    filtered = {
        cid: (score, chunk)
        for cid, (score, chunk) in all_scores.items()
        if not is_commentary_chunk(chunk)
    }
    _check("commentary + word_study ids removed", set(filtered.keys()) == {"a", "d"})
    _check("scores preserved", filtered["a"][0] == 1.0 and filtered["d"][0] == 0.7)


def test_fusion_weights_no_soft_commentary_path():
    print("\n== SOURCE_KIND_FUSION_WEIGHTS ==")
    _check(
        "commentary weight removed (hard exclude, not soft deprioritize)",
        "commentary" not in SOURCE_KIND_FUSION_WEIGHTS,
    )
    _check(
        "word_study weight absent too (hard exclude, not soft deprioritize)",
        "word_study" not in SOURCE_KIND_FUSION_WEIGHTS,
    )
    _check("book weight still present", SOURCE_KIND_FUSION_WEIGHTS.get("book") == 0.8)
    _check("lexicon weight still present", SOURCE_KIND_FUSION_WEIGHTS.get("lexicon") == 0.5)


def test_no_cap_constant():
    print("\n== retired COMMENTARY_CONTEXT_CAP ==")
    # Repointed 2026-08-07 (mirror-unification batch 4): chat.py, the
    # original home of this retired constant, is deleted. The commentary-
    # exclusion logic (and this constant's absence) now lives in
    # answer_toolbox.py (moved there 2026-08-07, mirror-unification batch
    # 1) -- the real, current location both the async path and (formerly)
    # chat.py imported from.
    import app.services.answer_toolbox as toolbox_mod
    _check(
        "COMMENTARY_CONTEXT_CAP no longer defined",
        not hasattr(toolbox_mod, "COMMENTARY_CONTEXT_CAP"),
    )


def main():
    print("test_commentary_answer_exclusion.py — decision #5")
    test_is_commentary_chunk()
    test_exclude_commentary_chunks()
    test_score_dict_filter_mirrors_step_26()
    test_fusion_weights_no_soft_commentary_path()
    test_no_cap_constant()
    print()
    if failures:
        print("FAILED %d check(s):" % len(failures))
        for f in failures:
            print("  - %s" % f)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
