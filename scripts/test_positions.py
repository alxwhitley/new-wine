#!/usr/bin/env python3
"""
test_positions.py -- regression tests for scripts/positions.py's Repair 1
(shared BASE_TEMPLATE dedup, zero behavior change) and Repair 2 (tension-
mode "verbatim" -> "explicitly states" wording fix, TENSION_MODE_PROMPT_
VERSION v2 -> v3), both 2026-07-30.

Mirrors this repo's ad hoc scripts/test_*.py convention -- no pytest,
hand-built `_check(label, condition)` assertions (see
test_citation_verifier_layers.py), a `main()` that runs everything,
`if __name__ == "__main__": main()`.

Tier A (deterministic, no live calls): imports scripts/positions.py
directly and asserts against its real, already-loaded module-level
constants and pure functions. No DB connection, no network call.

Tier B (2 behaviors, run twice each below): live calls to
generate_position_text(), which calls the real Anthropic API
(claude-sonnet-4-5, ~500 max output tokens/call, small real cost -- see
this build's own session report for the exact count/estimate across the
whole build). Unlike Tier A, Tier B also opens a REAL, read-only DB
connection (via positions.db_params()) to fetch the same real evidence
used in position_calibration_review/batch_results.json's num:7 (Derek
Prince / predestination) and num:6 (Vlad Savchuk / intermittent fasting)
cases -- requires SUPABASE_DB_URL to be set, same as positions.py itself.
Both Tier B checks run against a live, non-deterministic model and CAN
reasonably fail on genuinely-correct model output due to ordinary wording
variance -- this is disclosed, not hidden, in each test function's own
docstring below, not smoothed over.

Run: python3 scripts/test_positions.py
"""
import json
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import positions as pos  # noqa: E402

_BATCH_RESULTS_PATH = _SCRIPTS.parent / "position_calibration_review" / "batch_results.json"


def _check(label, condition):
    print(f"  {'OK' if condition else 'FAIL'}: {label}")
    assert condition, f"FAILED: {label}"


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- is_calvinism_predestination_topic()
# ═══════════════════════════════════════════════════════════════════════════

def test_calvinism_topic_matcher():
    print("\n" + "=" * 78)
    print("Tier A: is_calvinism_predestination_topic()")
    print("=" * 78)

    # The real topic this exception exists for (position_calibration_
    # review's num:7, source_id 17be391b-d025-4178-8543-3e84da675c5d) plus
    # other realistic Calvinism/predestination phrasings that should
    # trigger tension mode.
    should_match = [
        "predestination and unconditional election in the Calvinist sense",
        "Calvinism and predestination",
        "double predestination",
        "unconditional election",
        "the Calvinistic doctrine of election",
    ]
    for topic in should_match:
        _check(f"{topic!r} -> True", pos.is_calvinism_predestination_topic(topic) is True)

    # The matcher's own documented exclusions (is_calvinism_predestination_
    # topic()'s own docstring: deliberately NOT bare "election" -- would
    # over-trigger on generic "chosen by God" questions unrelated to the
    # specific Calvinist doctrine). Asserting CURRENT documented behavior,
    # not inventing new scope.
    should_not_match = [
        "election",
        "predestined",
        "predestinate",
        "Calvin on election",
        "unconditional-election",
    ]
    for topic in should_not_match:
        _check(f"{topic!r} -> False", pos.is_calvinism_predestination_topic(topic) is False)


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- _prompt_and_version_for_topic()
# ═══════════════════════════════════════════════════════════════════════════

def test_prompt_selector():
    print("\n" + "=" * 78)
    print("Tier A: _prompt_and_version_for_topic()")
    print("=" * 78)

    prompt, version = pos._prompt_and_version_for_topic(
        "predestination and unconditional election in the Calvinist sense"
    )
    _check("matching topic -> TENSION_MODE_PROMPT", prompt == pos.TENSION_MODE_PROMPT)
    _check(
        "matching topic -> TENSION_MODE_PROMPT_VERSION",
        version == pos.TENSION_MODE_PROMPT_VERSION,
    )

    prompt2, version2 = pos._prompt_and_version_for_topic(
        "Is intermittent fasting for weight loss a good health practice?"
    )
    _check("non-matching topic -> POSITION_PROMPT", prompt2 == pos.POSITION_PROMPT)
    _check("non-matching topic -> PROMPT_VERSION", version2 == pos.PROMPT_VERSION)

    _check(
        'TENSION_MODE_PROMPT_VERSION == "position_tension_v3"',
        pos.TENSION_MODE_PROMPT_VERSION == "position_tension_v3",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- shared-paragraph identity (Repair 1's own regression guard)
# ═══════════════════════════════════════════════════════════════════════════

# The six paragraphs BASE_TEMPLATE is supposed to hold ONCE and share
# between POSITION_PROMPT and TENSION_MODE_PROMPT -- hardcoded here
# (rather than sliced back out of BASE_TEMPLATE itself) so a future
# incomplete edit that bypasses BASE_TEMPLATE for one of the two final
# prompts is actually caught, instead of trivially matching itself.
_SHARED_PARAGRAPHS = [
    "You are writing a stored position: a summary of what a named teacher teaches on one topic, for a Bible-study research tool used by curious lay believers in the Spirit-filled tradition.",
    "You will be given the teacher's name, a topic, and a set of already-paraphrased teaching statements extracted from that teacher's own material. These statements are your ONLY source of information about this teacher's teaching on this topic. You have no other knowledge of what this teacher has said, and you must not add anything beyond what the statements say.",
    "THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is stated in the teaching statements you are given. Do not add scripture references, examples, or claims that are not in them. Do not draw on general theological knowledge to fill a gap. If the statements do not cover some angle of the topic, leave it out rather than infer it.",
    "Paraphrase. Do not quote the statements verbatim at length — restate them in connected prose, the same way the statements themselves already paraphrase their own source. A short (under roughly five word) precise phrase is fine only where it is genuinely how the teacher put a point in the evidence given to you.",
    "This position represents the one named teacher only. Do not hedge as though other viewpoints exist unless the statements themselves show this teacher addressing a counter-view.",
    "Output ONLY the position text — no preamble, no headers, no meta-commentary about the statements or the task.",
]


def test_shared_paragraphs_identical():
    print("\n" + "=" * 78)
    print("Tier A: shared paragraphs identical in both final prompts")
    print("=" * 78)

    for i, para in enumerate(_SHARED_PARAGRAPHS, 1):
        _check(f"shared paragraph {i} present in POSITION_PROMPT", para in pos.POSITION_PROMPT)
        _check(f"shared paragraph {i} present in TENSION_MODE_PROMPT", para in pos.TENSION_MODE_PROMPT)

    _check(
        "PREMISE_CORRECTION_CLAUSE present in POSITION_PROMPT",
        pos.PREMISE_CORRECTION_CLAUSE in pos.POSITION_PROMPT,
    )
    _check(
        "PREMISE_CORRECTION_CLAUSE present in TENSION_MODE_PROMPT",
        pos.PREMISE_CORRECTION_CLAUSE in pos.TENSION_MODE_PROMPT,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- "verbatim" -> "explicitly states" wording fix (Repair 2)
# ═══════════════════════════════════════════════════════════════════════════

# Hardcoded historical (pre-Repair-2, "position_tension_v2") wording --
# NOT re-imported from an old module/commit (an import of superseded code
# is not how this repo pins a historical string, and re-importing old
# positions.py would drag in its whole module-load side effects for no
# reason). This is the exact RESOLUTION_INSTRUCTION_TENSION-equivalent
# text that shipped before this repair.
_OLD_TENSION_RESOLUTION_INSTRUCTION_v2 = (
    "Write ONE position: a single coherent passage, roughly 100-200 words, "
    "stating what this teacher teaches about the given topic. Present what "
    "the teacher actually said, including any real tension between "
    "sovereignty/foreknowledge and free will, without resolving it into a "
    "side the teacher didn't take — unless the teacher has verbatim stated "
    "an explicit position, in which case state that position. Do not just "
    "restate a single statement. Name the teacher at least once, "
    "naturally. Where the statements show a specific, memorable framing or "
    "a real qualification the teacher attaches, keep it — do not flatten a "
    "distinctive position into generic Christian consensus."
)


def _tension_clause_requires_verbatim(resolution_instruction_text: str) -> bool:
    """True if this resolution-instruction paragraph still requires a
    'verbatim' statement for the narrow tension-mode exception (the
    pre-Repair-2 wording this test guards against reintroducing).

    Deliberately checked against the RESOLUTION_INSTRUCTION_TENSION-shaped
    text itself, NOT the whole TENSION_MODE_PROMPT string: the shared
    paraphrase-discipline paragraph ("Paraphrase. Do not quote the
    statements verbatim at length...") also contains the literal word
    "verbatim" and is correctly present, unchanged, in BOTH final prompt
    strings (see test_shared_paragraphs_identical() above) -- a naive
    whole-string "'verbatim' not in TENSION_MODE_PROMPT" assertion would
    incorrectly flag that unrelated, correctly-untouched paragraph as a
    failure on the real, correct, shipped code. This repo's own build
    report for this session found and flagged that exact contradiction in
    this test's original brief; this function is the corrected version."""
    return "verbatim" in resolution_instruction_text


def test_verbatim_wording_fix_regression():
    print("\n" + "=" * 78)
    print('Tier A: "verbatim" -> "explicitly states" wording fix (Repair 2)')
    print("=" * 78)

    # Fail-then-pass: the OLD wording must fail this check (proves the
    # check itself actually discriminates, not just that new code happens
    # to pass); the NEW (shipped) wording must pass it.
    _check(
        "OLD (pre-Repair-2, v2) wording requires 'verbatim' -- check correctly flags it",
        _tension_clause_requires_verbatim(_OLD_TENSION_RESOLUTION_INSTRUCTION_v2) is True,
    )
    _check(
        "NEW (shipped, v3) RESOLUTION_INSTRUCTION_TENSION no longer requires 'verbatim'",
        _tension_clause_requires_verbatim(pos.RESOLUTION_INSTRUCTION_TENSION) is False,
    )
    _check(
        "NEW RESOLUTION_INSTRUCTION_TENSION contains the honest replacement phrase",
        "explicitly state" in pos.RESOLUTION_INSTRUCTION_TENSION,
    )

    # Separately: the ONLY remaining "verbatim" occurrence in either final
    # prompt string is the shared, correctly-untouched paraphrase-
    # discipline paragraph -- present identically in BOTH POSITION_PROMPT
    # and TENSION_MODE_PROMPT, never something Repair 2 was supposed to
    # touch.
    shared_paraphrase_line = "Paraphrase. Do not quote the statements verbatim at length"
    _check(
        "TENSION_MODE_PROMPT's only 'verbatim' occurrence is the shared paraphrase-discipline paragraph",
        pos.TENSION_MODE_PROMPT.count("verbatim") == 1
        and shared_paraphrase_line in pos.TENSION_MODE_PROMPT,
    )
    _check(
        "POSITION_PROMPT has that same single 'verbatim' occurrence (same shared paragraph, correctly untouched)",
        pos.POSITION_PROMPT.count("verbatim") == 1
        and shared_paraphrase_line in pos.POSITION_PROMPT,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Tier B -- live generation, real evidence (real cost -- see report)
# ═══════════════════════════════════════════════════════════════════════════

def _fetch_evidence(source_num: int):
    """Read-only: loads the real evidence_ids for `num` from
    position_calibration_review/batch_results.json, then a read-only
    SELECT (positions.db_params()) against `propositions`, reordered to
    match the stored evidence_ids order -- same method this build's own
    Commit 2 real-data check used. Requires SUPABASE_DB_URL."""
    import psycopg2

    with open(_BATCH_RESULTS_PATH) as f:
        data = json.load(f)
    item = next(i for i in data if i.get("num") == source_num)
    evidence_ids = item["evidence_ids"]

    params = pos.db_params()
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id::text, content FROM propositions WHERE id = ANY(%s::uuid[])",
            (evidence_ids,),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    by_id = {pid: content for pid, content in rows}
    missing = [eid for eid in evidence_ids if eid not in by_id]
    if missing:
        raise AssertionError(f"_fetch_evidence(num={source_num}): missing proposition ids {missing}")
    return item["topic"], item["teacher"], [
        {"id": eid, "content": by_id[eid]} for eid in evidence_ids
    ]


def test_tension_mode_live_generation():
    """Live call x2: Derek Prince / real num:7 topic+evidence
    (position_calibration_review/batch_results.json, source_id
    17be391b-d025-4178-8543-3e84da675c5d).

    DESIGN NOTE -- read before changing this assertion, and read the
    revision history below before reintroducing a phrase-based check:

    This build's own Commit 2 real-data comparison (see this session's
    report) ran the OLD ("verbatim") and NEW ("explicitly states") tension
    wording 3x each against this exact real evidence set and found NO
    reliable difference in whether the model uses confident "resolves the
    tension... by [X]"-style language -- it appeared in 2 of 3 runs on
    BOTH wordings. The wording fix is real and worth shipping (Repair 2:
    "verbatim" could never actually be satisfied, since generate_
    position_text() only ever sees already-paraphrased propositions.
    content, never the teacher's original wording) but it is NOT shown to
    change surface over-resolution language on this real case, and this
    test does not claim otherwise.

    REVISION (found live, during this build's own second test-file run):
    this test's first version also asserted the exact historically-
    confirmed Draft-15 fabrication phrase ("resolves the tension... by
    appealing to") never recurs. It failed on a run that produced:
    "Prince resolves the tension between predestination and free will not
    by denying either, but by appealing to God's measureless, unlimited
    knowledge." Reading this num:7 evidence set directly (position_
    calibration_review/batch_results.json) shows why this is NOT a
    repeat of the Draft-15 fabrication: one of the ten real evidence
    items IS "Derek Prince thinks that the resolution to the tension
    between predestination and free will comes through understanding the
    extent of God's knowledge, which is measureless and unlimited..." --
    i.e. this specific evidence set genuinely contains a stated
    resolution, so a model faithfully paraphrasing it into "resolves...
    by appealing to God's measureless, unlimited knowledge" is CORRECT
    behavior, not fabrication. The literal phrase is evidence-dependent,
    not itself diagnostic -- the same surface phrase would be fabrication
    against evidence that contains no stated resolution (Draft-15's case)
    and faithful paraphrase against evidence that does (this case). This
    matches CLAUDE.md's own standing finding (Landmines: "No cheap check
    exists for the demonstrated fabrication class...") that no surface/
    phrase-level check reliably distinguishes grounded from fabricated
    content here. The phrase-recurrence assertion was therefore REMOVED,
    not loosened -- it was testing the wrong thing, not merely testing it
    too strictly. Only the substantive engagement check below remains.

    FLAKY, DISCLOSED: still a live, non-deterministic model call, and even
    the remaining check is a weak floor (it only confirms the output
    doesn't silently drop one side of the tension, not that any given
    resolution claim is actually grounded) -- rerun/re-read before
    treating a failure as a confirmed regression.
    """
    print("\n" + "=" * 78)
    print("Tier B (LIVE): tension-mode generation -- Derek Prince / predestination")
    print("=" * 78)

    topic, teacher, evidence = _fetch_evidence(7)
    for i in range(2):
        out = pos.generate_position_text(teacher, topic, evidence)
        print(f"\n  -- run {i + 1} --\n{out}\n")
        mentions_both_sides = (
            ("free will" in out.lower() or "response" in out.lower())
            and (
                "foreknowledge" in out.lower()
                or "sovereign" in out.lower()
                or "predestin" in out.lower()
            )
        )
        _check(
            f"run {i + 1}: engages both sides of the tension (doesn't silently drop one)",
            mentions_both_sides,
        )


def _names_premise_gap(text: str) -> bool:
    """True if any single sentence contains both a negation ("not") and a
    diet/weight-loss term -- i.e. the position states, in one place, that
    the practice is NOT a diet/weight-loss thing. Sentence-scoped (not a
    single fixed phrase) precisely because this check's first version (a
    narrow regex requiring "not a diet"/"not weight-loss" adjacency)
    FAILED live during this build's own first test run against a real,
    genuinely correct model output phrased as "...not to diet or lose
    weight" -- a true false-negative on correct behavior, not a real
    regression. This looser, same-sentence co-occurrence check is the
    revised version; see this session's report for the exact run that
    exposed the original version's brittleness."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        s = sentence.lower()
        if "not" in s and ("diet" in s or "weight" in s):
            return True
    return False


def test_premise_correction_live_generation():
    """Live call x2: Vlad Savchuk / real num:6 topic+evidence
    (position_calibration_review/batch_results.json, source_id
    74ed5fa1-9aac-4997-87ec-4be6724b49bd).

    Asserts the generated position names the premise gap -- distinguishes
    the ASKED-AS framing ("is fasting for weight loss a good practice?")
    from what the gathered evidence actually shows (fasting as a biblical/
    spiritual discipline, not a weight-loss method) -- rather than silently
    answering the loaded framing as if it were true. Checked via same-
    sentence co-occurrence of a negation and a diet/weight term (see
    _names_premise_gap()) rather than one exact string, since the model's
    exact phrasing varies.

    FLAKY, DISCLOSED: like the tension-mode check above, this runs against
    a live, non-deterministic model. This exact check's first, narrower
    version already produced one confirmed false failure on genuinely
    correct output during this build's own development (documented in
    _names_premise_gap()'s docstring and this session's report) -- a
    genuinely correct answer phrased in some other unanticipated way could
    still fail this looser version too. Re-run/re-read before treating a
    failure here as a confirmed regression rather than a phrasing miss.
    """
    print("\n" + "=" * 78)
    print("Tier B (LIVE): premise-correction generation -- Vlad Savchuk / fasting")
    print("=" * 78)

    topic, teacher, evidence = _fetch_evidence(6)
    for i in range(2):
        out = pos.generate_position_text(teacher, topic, evidence)
        print(f"\n  -- run {i + 1} --\n{out}\n")
        _check(
            f"run {i + 1}: names the premise gap (practice vs. weight-loss framing)",
            _names_premise_gap(out),
        )


def main():
    print("#" * 78)
    print("test_positions.py")
    print("#" * 78)

    test_calvinism_topic_matcher()
    test_prompt_selector()
    test_shared_paragraphs_identical()
    test_verbatim_wording_fix_regression()

    print("\n" + "#" * 78)
    print("Tier A: all assertions passed.")
    print("#" * 78)

    print(
        "\nTier B below makes live Anthropic API calls (real, small cost) and "
        "opens a real read-only DB connection. See this file's own docstrings "
        "and this build's session report for the flakiness disclosure on both."
    )
    test_tension_mode_live_generation()
    test_premise_correction_live_generation()

    print("\n" + "#" * 78)
    print("All assertions passed (Tier A + Tier B).")
    print("#" * 78)


if __name__ == "__main__":
    main()
