#!/usr/bin/env python3
"""
test_serve_position.py -- deterministic (no DB, no LLM) regression tests for
the corpus/serving-path additions (PLAN.md #48 serving-path session,
2026-08-01). Mirrors this repo's ad hoc test_*.py convention (hand-built
_check, a main() runner). The full end-to-end proof (real DB + real LLM) is
scripts/prove_serving_path.py; this file guards the pure functions and the
structural source-blindness contract.

Run: python3 scripts/test_serve_position.py
"""
import inspect
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import positions as pos  # noqa: E402


def _check(label, cond):
    print(f"  {'OK' if cond else 'FAIL'}: {label}")
    assert cond, f"FAILED: {label}"


def test_invariant_12_signatures_source_blind():
    """Structural guard for CLAUDE.md Invariant 12: BOTH generators take only
    topic/proposition-content/teacher-NAME params -- never source_id,
    document_id, chunk, or a db connection. This is the invariant enforced by
    signature, tested by signature."""
    print("\n" + "=" * 78)
    print("Invariant 12: generator signatures are source-blind")
    forbidden = ("source_id", "document_id", "doc_id", "chunk", "chunks", "conn", "params", "cur")

    tp = list(inspect.signature(pos.generate_position_text).parameters)
    _check(f"generate_position_text params == [teacher_name, topic, evidence] (got {tp})",
           tp == ["teacher_name", "topic", "evidence"])
    for bad in forbidden:
        _check(f"generate_position_text has no {bad!r} param", bad not in tp)

    cp = list(inspect.signature(pos.generate_corpus_position_text).parameters)
    _check(f"generate_corpus_position_text params == [topic, attributed_evidence] (got {cp})",
           cp == ["topic", "attributed_evidence"])
    for bad in forbidden:
        _check(f"generate_corpus_position_text has no {bad!r} param", bad not in cp)

    # Streaming siblings (2026-08-04, PLAN.md #48 step 2c) must carry the
    # identical source-blind contract -- additive, never a looser copy.
    tps = list(inspect.signature(pos.generate_position_text_stream).parameters)
    _check(f"generate_position_text_stream params == [teacher_name, topic, evidence] (got {tps})",
           tps == ["teacher_name", "topic", "evidence"])
    for bad in forbidden:
        _check(f"generate_position_text_stream has no {bad!r} param", bad not in tps)

    cps = list(inspect.signature(pos.generate_corpus_position_text_stream).parameters)
    _check(f"generate_corpus_position_text_stream params == [topic, attributed_evidence] (got {cps})",
           cps == ["topic", "attributed_evidence"])
    for bad in forbidden:
        _check(f"generate_corpus_position_text_stream has no {bad!r} param", bad not in cps)


def test_normalize_topic_key():
    print("\n" + "=" * 78)
    print("normalize_topic_key: collapse-then-trim-then-lower")
    cases = {
        "Fasting": "fasting",
        "  How   to  Pray  ": "how to pray",
        "Baptism\tin the\nSpirit": "baptism in the spirit",
        "PREDESTINATION": "predestination",
        "the Holy   Spirit  ": "the holy spirit",
    }
    for raw, expected in cases.items():
        _check(f"{raw!r} -> {expected!r}", pos.normalize_topic_key(raw) == expected)


def test_determine_scope():
    print("\n" + "=" * 78)
    print("determine_scope: dominance boundary at 0.60")
    _check("DOMINANCE_THRESHOLD == 0.60", pos.DOMINANCE_THRESHOLD == 0.60)
    ev = lambda dist: [{"source_id": s} for s, n in dist.items() for _ in range(n)]
    _check("70/30 -> teacher (dominant A)", pos.determine_scope(ev({"A": 7, "B": 3})) == ("teacher", "A"))
    _check("60/40 -> teacher (exactly at floor)", pos.determine_scope(ev({"A": 6, "B": 4})) == ("teacher", "A"))
    _check("59/41 -> corpus (just below)", pos.determine_scope(ev({"A": 59, "B": 41})) == ("corpus", None))
    _check("50/30/20 -> corpus", pos.determine_scope(ev({"A": 5, "B": 3, "C": 2})) == ("corpus", None))
    _check("100/0 -> teacher", pos.determine_scope(ev({"A": 9})) == ("teacher", "A"))
    _check("empty -> corpus,None (caller refuses on floor)", pos.determine_scope([]) == ("corpus", None))


def test_contributor_breakdown():
    print("\n" + "=" * 78)
    print("contributor_breakdown: counts, sorted desc then name")
    ev = (
        [{"source_id": "a", "teacher": "Zeta"}] * 2
        + [{"source_id": "b", "teacher": "Alpha"}] * 5
        + [{"source_id": "c", "teacher": "Mid"}] * 2
    )
    cb = pos.contributor_breakdown(ev)
    _check("top contributor is Alpha (5)", cb[0] == {"source_id": "b", "name": "Alpha", "count": 5})
    _check("ties broken by name (Mid before Zeta)", [c["name"] for c in cb] == ["Alpha", "Mid", "Zeta"])
    _check("counts preserved", [c["count"] for c in cb] == [5, 2, 2])


def test_prompt_and_version_scope_aware():
    print("\n" + "=" * 78)
    print("_prompt_and_version: scope-aware selector")
    _check("corpus -> CORPUS_PROMPT/position_corpus_v1",
           pos._prompt_and_version("anything", "corpus") == (pos.CORPUS_PROMPT, pos.CORPUS_PROMPT_VERSION))
    _check("teacher ordinary -> POSITION_PROMPT/position_v2",
           pos._prompt_and_version("fasting", "teacher") == (pos.POSITION_PROMPT, pos.PROMPT_VERSION))
    _check("teacher predestination -> TENSION_MODE_PROMPT/position_tension_v3",
           pos._prompt_and_version("predestination", "teacher") == (pos.TENSION_MODE_PROMPT, pos.TENSION_MODE_PROMPT_VERSION))
    _check("corpus predestination still CORPUS (divergence subsumes tension)",
           pos._prompt_and_version("predestination", "corpus")[1] == pos.CORPUS_PROMPT_VERSION)


def test_corpus_prompt_drift_guard():
    """The corpus prompt reuses fragments from the teacher BASE_TEMPLATE
    verbatim (four corners, paraphrase discipline, no-preamble, premise
    clause). This guards against one being edited without the other -- the
    book-name-map drift failure shape (CLAUDE.md Landmines)."""
    print("\n" + "=" * 78)
    print("corpus prompt drift guard: shared fragments present in both")
    fc = "THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is stated in the teaching statements you are given."
    para = "Paraphrase. Do not quote the statements verbatim at length"
    nopre = "Output ONLY the position text — no preamble, no headers, no meta-commentary about the statements or the task."
    for label, frag in (("four-corners", fc), ("paraphrase", para), ("no-preamble", nopre)):
        _check(f"{label} in POSITION_PROMPT", frag in pos.POSITION_PROMPT)
        _check(f"{label} in CORPUS_PROMPT", frag in pos.CORPUS_PROMPT)
    _check("PREMISE_CORRECTION_CLAUSE in CORPUS_PROMPT", pos.PREMISE_CORRECTION_CLAUSE in pos.CORPUS_PROMPT)
    _check("CORPUS_PROMPT tells the model to present disagreement", "DISAGREE" in pos.CORPUS_PROMPT)
    _check("CORPUS_PROMPT forbids a manufactured consensus",
           "consensus none of them actually stated" in pos.CORPUS_PROMPT)
    _check("CORPUS_PROMPT forbids a blended middle", "blended middle" in pos.CORPUS_PROMPT)


def test_scope_lock():
    print("\n" + "=" * 78)
    print("_assert_permitted_scope: two-scope application lock")
    pos._assert_permitted_scope("teacher")  # no raise
    pos._assert_permitted_scope("corpus")   # no raise
    for bad in ("stream", "cluster", "family", "", "Teacher"):
        try:
            pos._assert_permitted_scope(bad)
            _check(f"{bad!r} rejected", False)
        except ValueError:
            _check(f"{bad!r} rejected", True)


def test_teacher_prompts_byte_unchanged():
    """The serving-path build must NOT have changed the proven teacher prompts
    (3 live position_v1 rows + the position_v2 fingerprint depend on it)."""
    print("\n" + "=" * 78)
    print("teacher prompts byte-unchanged (built from BASE_TEMPLATE)")
    _check("POSITION_PROMPT == BASE_TEMPLATE.format(ordinary)",
           pos.POSITION_PROMPT == pos.BASE_TEMPLATE.format(
               premise_correction_clause=pos.PREMISE_CORRECTION_CLAUSE,
               resolution_instruction=pos.RESOLUTION_INSTRUCTION_ORDINARY))
    _check("PROMPT_VERSION == position_v2", pos.PROMPT_VERSION == "position_v2")
    _check("CORPUS_PROMPT_VERSION == position_corpus_v1", pos.CORPUS_PROMPT_VERSION == "position_corpus_v1")


def main():
    test_invariant_12_signatures_source_blind()
    test_normalize_topic_key()
    test_determine_scope()
    test_contributor_breakdown()
    test_prompt_and_version_scope_aware()
    test_corpus_prompt_drift_guard()
    test_scope_lock()
    test_teacher_prompts_byte_unchanged()
    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()
