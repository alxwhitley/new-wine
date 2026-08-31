#!/usr/bin/env python3
"""
test_position_paper_fence.py -- regression tests for the position-papers-as-
fence architecture (Alex's ruling, 2026-08-06, resolving CLAUDE.md Settled
decision #8's flagged 2026-08-01 conflict): a position paper is constraining
silent context, never a served answer. Covers:

  - backend/app/services/position_papers.py's DISCLAIMER_TEXT /
    render_paper_voice_with_disclaimer() (the sanctioned fallback)
  - backend/app/services/position_paper_exclusion.py's
    exclude_contradicting_teachers() (grouping/citability filtering; the
    live classification call itself is exercised in Tier B, not mocked)
  - backend/app/services/async_answers/producer.py's wiring (the sole
    surviving answer path -- backend/app/routers/chat.py was deleted
    2026-08-07, mirror-unification batch 4): retrieval now runs on a
    position-paper match, exclusion fires before generation, the
    everyone-excluded fallback fires only in that specific case

Mirrors this repo's ad hoc scripts/test_*.py convention -- no pytest,
hand-built `_check(label, condition)` assertions.

Tier A (deterministic, no live LLM call): the grouping/citability filter in
position_paper_exclusion.py, and DISCLAIMER_TEXT's exact wording.

Tier B (live, real DB + embeddings + Anthropic calls, real cost): for both
live papers (baptism_holy_spirit, speaking_in_tongues), a generic real
question through producer.produce() -- confirms retrieval now runs (real,
multi-author citations), the paper's own wording is not reproduced
verbatim, and reports whether exclusion fired (a real corpus-dependent
outcome, not asserted either way, since which teachers genuinely contradict
is a live corpus fact, not a fixed expectation). Also constructs the
everyone-excluded case (via a narrow, documented monkeypatch of
position_paper_exclusion.exclude_contradicting_teachers, restored
immediately after) and confirms the fallback fires with the exact
disclaimer, uncited.

Run: python3 scripts/test_position_paper_fence.py
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_BACKEND / "app" / ".env")

from app.services import position_papers as pp  # noqa: E402
from app.services.position_paper_exclusion import _group_chunks_by_author  # noqa: E402

failures = []


def _check(label, condition):
    status = "OK" if condition else "FAIL"
    print(f"  {status}: {label}")
    if not condition:
        failures.append(label)


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- disclaimer text + citable/lexicon filtering
# ═══════════════════════════════════════════════════════════════════════════

def test_disclaimer_text():
    print("\n" + "=" * 78)
    print("Tier A: position_papers.DISCLAIMER_TEXT")
    print("=" * 78)
    _check(
        "exact required wording",
        pp.DISCLAIMER_TEXT == "New Wine can make mistakes. Please let us know if you see any.",
    )


def test_grouping_excludes_noncitable_and_lexicon():
    print("\n" + "=" * 78)
    print("Tier A: _group_chunks_by_author() filters out non-citable / lexicon chunks")
    print("=" * 78)
    chunks = [
        {"author": "Derek Prince", "citation_mode": "citable", "content": "a"},
        {"author": "Derek Prince", "citation_mode": "citable", "content": "b"},
        {"author": "Adam Clarke", "citation_mode": "silent_context", "content": "commentary"},
        {"author": "STEPBible / Tyndale House", "citation_mode": "silent_context", "_lexicon": True, "content": "lex"},
        {"author": "", "citation_mode": "citable", "content": "no author"},
        {"author": "Zac Poonen", "source_type": "sermon", "content": "no citation_mode field, falls back to source_type"},
    ]
    groups = _group_chunks_by_author(chunks)
    _check("Derek Prince present with 2 chunks", groups.get("Derek Prince") and len(groups["Derek Prince"]) == 2)
    _check("Adam Clarke (silent_context commentary) excluded", "Adam Clarke" not in groups)
    _check("lexicon entry excluded regardless of citation_mode", "STEPBible / Tyndale House" not in groups)
    _check("empty-author chunk excluded", "" not in groups)
    _check("source_type=sermon fallback still counts as citable", "Zac Poonen" in groups)


# ═══════════════════════════════════════════════════════════════════════════
# Tier B -- live, real corpus
# ═══════════════════════════════════════════════════════════════════════════

def _run_paper_case(db, label, question):
    from app.services.async_answers import producer

    print(f"\n  -- {label}: {question!r} --")
    pillar = pp.match_position_paper(question)
    _check(f"[{label}] matches a live position paper", pillar is not None)
    if not pillar:
        return

    result = producer.produce(db, question, messages=[])
    _check(f"[{label}] outcome is 'answered' (retrieval ran, not the old direct-serve)", result.outcome == "answered")
    _check(f"[{label}] real citations present", len(result.citations) > 0)

    authors = sorted({c.get("author") for c in result.citations if c.get("author")})
    print(f"     citation authors: {authors}")

    body = pp.get_paper_body(pillar) or ""
    words = body.split()
    mid = len(words) // 2
    distinctive_phrase = " ".join(words[mid:mid + 8])
    _check(
        f"[{label}] paper's own wording not reproduced verbatim",
        distinctive_phrase not in result.answer,
    )
    print(f"     answer (first 200 chars): {result.answer[:200]!r}")


def _run_fallback_case(db):
    """Constructs the everyone-excluded case via a narrow, documented
    monkeypatch of position_paper_exclusion.exclude_contradicting_teachers --
    the exact symbol producer._retrieve() reaches via
    position_paper_exclusion.exclude_contradicting_teachers (retargeted
    2026-08-07, mirror-unification batch 4, off the now-deleted
    app.routers.chat module) -- restored immediately in a finally block.
    Confirms the real control flow in producer.py, not just the standalone
    disclaimer helper."""
    from app.services import position_paper_exclusion
    from app.services.async_answers import producer

    print("\n  -- constructed case: exclusion empties the answer -> fallback --")
    question = "What is the baptism of the Holy Spirit?"
    _real = position_paper_exclusion.exclude_contradicting_teachers

    def _fake_exclude_all(pillar_key, house_position_text, q, chunks):
        authors = sorted({(c.get("author") or "").strip() for c in chunks if c.get("author")})
        return [], authors

    position_paper_exclusion.exclude_contradicting_teachers = _fake_exclude_all
    try:
        result = producer.produce(db, question, messages=[])
    finally:
        position_paper_exclusion.exclude_contradicting_teachers = _real

    _check("fallback outcome is 'position_paper'", result.outcome == "position_paper")
    _check("fallback carries zero citations", result.citations == [])
    _check("fallback carries zero verified_references", result.verified_references == [])
    _check(
        "fallback answer ends with the exact disclaimer",
        result.answer.strip().endswith(pp.DISCLAIMER_TEXT),
    )
    print(f"     answer (first 200 chars): {result.answer[:200]!r}")
    print(f"     answer ends with: {result.answer.strip()[-len(pp.DISCLAIMER_TEXT) - 5:]!r}")


def _run_tier_b():
    print("\n" + "=" * 78)
    print("Tier B: live papers, real corpus (real Anthropic/embedding cost)")
    print("=" * 78)

    from app.db.supabase import get_supabase
    db = get_supabase()

    _run_paper_case(db, "baptism (live)", "What is the baptism of the Holy Spirit?")
    _run_paper_case(db, "tongues (live)", "What does it mean to speak in tongues?")
    _run_fallback_case(db)


def main():
    print("#" * 78)
    print("test_position_paper_fence.py")
    print("#" * 78)

    test_disclaimer_text()
    test_grouping_excludes_noncitable_and_lexicon()

    print("\n" + "#" * 78)
    if failures:
        print(f"Tier A: {len(failures)} FAILURE(S): " + ", ".join(failures))
    else:
        print("Tier A: all assertions passed.")
    print("#" * 78)

    print(
        "\nTier B below makes live Anthropic/embedding/Cohere calls against the "
        "real corpus (real, small cost). See scripts/test_debate_topics.py for "
        "the same disclosure pattern."
    )
    _run_tier_b()

    print("\n" + "#" * 78)
    if failures:
        print(f"{len(failures)} FAILURE(S) TOTAL: " + ", ".join(failures))
    else:
        print("All assertions passed (Tier A + Tier B).")
    print("#" * 78)

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
