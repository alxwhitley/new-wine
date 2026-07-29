#!/usr/bin/env python3
"""
test_citation_verifier_layers.py — DB-free proof for
citation_verifier_layers.py's three-layer scripture-reference verification
(Steps 1-5 of this build's plan). Mirrors this repo's existing ad hoc
scripts/test_*.py convention -- hand-built fakes/mocks, plain
`if __name__ == "__main__": main()`, no pytest, a `make_call()`-style
scripted-sequence-with-call-counter pattern for mocking the Layer 3 LLM
call (mirrors scripts/test_rewrite_flagged_statement.py's own convention).

Every case here uses in-memory, hand-constructed strings -- no DB
connection is opened anywhere in this file, and no real network call is
ever made (Layer 3's LLM call is always monkeypatched before it can fire).

Run: python3 scripts/test_citation_verifier_layers.py
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import citation_verifier_layers as cvl  # noqa: E402


def _check(label, condition):
    print(f"  {'OK' if condition else 'FAIL'}: {label}")
    assert condition, f"FAILED: {label}"


# ═══════════════════════════════════════════════════════════════════════════
# Step 1 — word_or_digit_to_int()
# ═══════════════════════════════════════════════════════════════════════════

def test_number_converter():
    print("\n" + "=" * 78)
    print("Step 1: word_or_digit_to_int()")
    print("=" * 78)

    cases = [
        ("four", 4),
        ("twenty-eight", 28),
        ("one hundred fifty", 150),
        ("15", 15),
        ("third", 3),
        ("fifty-third", 53),
        ("53rd", 53),
        ("1st", 1),
        ("2nd", 2),
        ("3rd", 3),
        ("21st", 21),
    ]
    for word, expected in cases:
        got = cvl.word_or_digit_to_int(word)
        _check(f"{word!r} -> {expected}", got == expected)

    # Must NOT silently guess a wrong-but-plausible integer for
    # unrecognized input -- returns None.
    for bad in ["banana", "third hundred", "", "   ", None, "twelvish"]:
        got = cvl.word_or_digit_to_int(bad)
        _check(f"unrecognized input {bad!r} -> None (never guesses)", got is None)


# ═══════════════════════════════════════════════════════════════════════════
# Step 2 — Layer 1: widened spoken-form scanner
# ═══════════════════════════════════════════════════════════════════════════

def test_layer1_widened_forms():
    print("\n" + "=" * 78)
    print("Step 2: Layer 1 — widened spoken-form scanner (9 forms + regression)")
    print("=" * 78)

    cases = [
        (
            "1. chapter N verse N (digits)",
            "Turn with me to John chapter 15 verse 5 and let's read together.",
            "John 15:5",
        ),
        (
            "2. chapter N, verses N through N (range)",
            "Paul writes in Philippians chapter 4, verses 11 through 12 about contentment.",
            "Philippians 4:11-12",
        ),
        (
            "3. spelled-out numbers, period tolerated",
            "Let's read from Genesis chapter 1. Verse four says clearly that light was good.",
            "Genesis 1:4",
        ),
        (
            "4a. inverted order — verse N of chapter N ... in BOOK",
            "He was speaking of the verse 34 of chapter 8 here in Romans, a powerful truth.",
            "Romans 8:34",
        ),
        (
            "4b. inverted order — verse N of BOOK N",
            "As it says in verse 7 of Hebrews 5, we ought to listen.",
            "Hebrews 5:7",
        ),
        (
            "5a. ordinal chapter, word-form",
            "Turn now to the third chapter of 2 Timothy, verse 16, a well-known text.",
            "2 Timothy 3:16",
        ),
        (
            "5b. ordinal chapter, digit-suffix form",
            "Consider the 53rd chapter of Isaiah, verse 5, describing the suffering servant.",
            "Isaiah 53:5",
        ),
        (
            "6. book separated from numbers by intervening words",
            "Turn with me now to John, my dear friend, in chapter 15 verse 5.",
            "John 15:5",
        ),
        (
            "7. 'book of X' prefix",
            "Let's turn now to the book of Psalms, Psalm 102:1, a beautiful prayer.",
            "Psalms 102:1",
        ),
        (
            "8. explicit 'and'",
            "John chapter 6 and verse 38 makes this point plainly.",
            "John 6:38",
        ),
        (
            "9. 'chapter N:M' colon form, no 'verse' word at all -- the "
            "documented gap this build's own plan named up front, confirmed "
            "real against live corpus text (Vlad Savchuk, '4 Destructive "
            "Habits That Keep You Weak', a live 'needs fixing' statement's "
            "own failing reference)",
            "Isolating from the godly community, Satan will use that to keep you "
            "weak. Hebrews chapter 10:25 it says do not give up meeting together "
            "as some are in the habit of doing.",
            "Hebrews 10:25",
        ),
        (
            "9b. 'chapter N:M' colon form, second real corpus example (Vlad "
            "Savchuk, 'Will the Rapture Happen This Month?')",
            "It's clear that the son of perdition must be revealed first. "
            "2 Thessalonians chapter 2:3 says clearly Jesus is not returning "
            "until Antichrist is revealed.",
            "2 Thessalonians 2:3",
        ),
    ]

    for label, source_text, reference in cases:
        confirmed = cvl.layer1_confirm(reference, source_text)
        _check(f"{label}: {reference!r} confirms in {source_text!r}", confirmed)

    # ── Regression: existing compact form must still confirm exactly as
    #    before, tested directly against an in-memory string (DB-free). ────
    print("\n  -- Regression: compact form ('Hebrews 10:25') --")
    compact_source = "As it says in Hebrews 10:25, let us not neglect meeting together."
    _check(
        "compact form 'Hebrews 10:25' still confirms via Layer 1",
        cvl.layer1_confirm("Hebrews 10:25", compact_source),
    )

    # ── Candidate re-validation: every LayerCandidate carries a parsed
    #    tuple that round-trips through _parse_verse_or_range (proven by
    #    construction — find_layer1_candidates() only ever appends a
    #    candidate after that validation succeeds). Directly confirm no
    #    candidate has parsed=None and that malformed captures are dropped
    #    silently rather than guessed. ─────────────────────────────────────
    print("\n  -- Candidate re-validation discipline --")
    candidates = cvl.find_layer1_candidates(
        "Turn with me to John chapter 15 verse 5 and let's read together."
    )
    _check("at least one candidate found", len(candidates) >= 1)
    for c in candidates:
        _check(f"candidate {c.raw!r} has a non-None parsed tuple", c.parsed is not None)

    # ── Match rule = exact parsed-tuple equality. No range-containment
    #    credit: source states a RANGE, reference-under-test cites a single
    #    verse INSIDE that range — must NOT confirm. ─────────────────────
    print("\n  -- No range-containment credit (explicitly out of scope) --")
    range_source = "Paul writes in Philippians chapter 4, verses 11 through 12 about contentment."
    _check(
        "single verse 'Philippians 4:11' inside a stated range 11-12 does NOT confirm "
        "(range-containment credit is out of scope)",
        not cvl.layer1_confirm("Philippians 4:11", range_source),
    )

    # ── Wrong-verse near-miss FAILS, tested directly. ───────────────────
    print("\n  -- Wrong-verse near-miss FAILS --")
    near_miss_source = "As it says in Hebrews chapter 10 verse 24, let us consider one another."
    _check(
        "'Hebrews 10:25' does NOT confirm against a source stating 'Hebrews chapter 10 verse 24'",
        not cvl.layer1_confirm("Hebrews 10:25", near_miss_source),
    )

    # ── Wrong-book FAILS, tested directly. ──────────────────────────────
    print("\n  -- Wrong-book FAILS --")
    wrong_book_source = "As it says in John chapter 10 verse 25, the sheep hear his voice."
    _check(
        "'Hebrews 10:25' does NOT confirm against a source stating 'John chapter 10 verse 25' "
        "(same chapter:verse, different book)",
        not cvl.layer1_confirm("Hebrews 10:25", wrong_book_source),
    )

    # ── PATTERN_D ("chapter N:M" colon form) mechanism check + its own
    #    precision negatives -- proving the new form-9 pattern didn't loosen
    #    the exact-match discipline the pre-existing forms already hold to.
    print("\n  -- PATTERN_D mechanism check: candidate actually comes from "
          "pattern_d_chapter_colon_form --")
    hebrews_colon_source = (
        "Isolating from the godly community, Satan will use that to keep you "
        "weak. Hebrews chapter 10:25 it says do not give up meeting together."
    )
    d_candidates = [
        c for c in cvl.find_layer1_candidates(hebrews_colon_source)
        if c.source == "pattern_d_chapter_colon_form"
    ]
    _check(
        "at least one candidate is tagged source='pattern_d_chapter_colon_form'",
        len(d_candidates) >= 1,
    )
    _check(
        "that candidate's parsed tuple matches 'Hebrews 10:25' exactly",
        any(c.parsed == cvl._parse_verse_or_range("Hebrews 10:25") for c in d_candidates),
    )

    print("\n  -- PATTERN_D wrong-verse near-miss FAILS (colon form) --")
    colon_wrong_verse = "Isolating from community is dangerous. Hebrews chapter 10:24 it says do not give up."
    _check(
        "'Hebrews 10:25' does NOT confirm against a source stating colon-form "
        "'Hebrews chapter 10:24' (same chapter, wrong verse)",
        not cvl.layer1_confirm("Hebrews 10:25", colon_wrong_verse),
    )

    print("\n  -- PATTERN_D precision case: right verse NUMBER, wrong chapter "
          "(a 'verse count from a different chapter than cited') --")
    colon_wrong_chapter = (
        "Today we are studying the book of Romans. Romans chapter 9:28, we find "
        "something else entirely, a different teaching."
    )
    _check(
        "'Romans 8:28' does NOT confirm against a source stating colon-form "
        "'Romans chapter 9:28' (verse number 28 coincidentally matches, but "
        "it's chapter 9's verse 28, not chapter 8's)",
        not cvl.layer1_confirm("Romans 8:28", colon_wrong_chapter),
    )

    print("\n  -- PATTERN_D wrong-book FAILS (colon form) --")
    colon_wrong_book = "As it says in John chapter 10:25, the sheep hear his voice."
    _check(
        "'Hebrews 10:25' does NOT confirm against a source stating colon-form "
        "'John chapter 10:25' (same chapter:verse, different book)",
        not cvl.layer1_confirm("Hebrews 10:25", colon_wrong_book),
    )

    # ── Documented non-fix decisions (this build's own report): two shapes
    #    hypothesized up front, confirmed real against corpus text, but
    #    deliberately NOT patched -- tested here so the decision stays
    #    durable/regression-proof, not just a comment. ────────────────────
    print("\n  -- Documented non-fix: 'v.'/'vs.' verse-abbreviation alias "
          "was NOT added (confirmed real corpus-wide, but never in a form "
          "pairing with an explicit 'chapter' keyword) --")
    v_abbrev_source = "Hebrews chapter 10, v. 25 it says do not give up meeting together."
    _check(
        "'Hebrews 10:25' does NOT confirm against 'Hebrews chapter 10, v. 25' "
        "(this build deliberately did not add a v./vs. alias for 'verse(s)')",
        not cvl.layer1_confirm("Hebrews 10:25", v_abbrev_source),
    )

    print("\n  -- Documented non-fix: bare verse-only citation relying on an "
          "earlier, non-adjacent chapter mention was NOT added (modeled on "
          "Ern Baxter, 'Christ's Eternal Lordship' -- 'the prayer recorded "
          "in John 17 ... (vs. 2 NAS)') --")
    bare_verse_source = (
        "Hear Him again in the prayer recorded in John chapter 17. He "
        "acknowledges that the Father had given Him authority over all "
        "mankind (vs. 2 NAS)."
    )
    _check(
        "'John 17:2' does NOT confirm against a bare 'vs. 2' with the chapter "
        "established only by an earlier, non-adjacent 'John chapter 17' "
        "mention -- accepting this would require a pattern with no "
        "structural marker directly attached to the number, which this "
        "module's own precision floor forbids",
        not cvl.layer1_confirm("John 17:2", bare_verse_source),
    )

    # ── Precision floor against adversarial noise: a bare co-occurrence of
    #    a BOOK_MAP word ("job") and two unrelated numbers in ordinary
    #    prose, with NO chapter/verse structural marker anywhere nearby,
    #    must NOT confirm. ────────────────────────────────────────────────
    print("\n  -- Precision floor: adversarial noise, no structural marker --")
    noise_source = (
        "He had a job to do, and by noon he had counted 12 sheep and 8 goats near the barn."
    )
    _check(
        "no candidates at all found in bare 'job ... 12 ... 8' noise (no chapter/verse marker)",
        cvl.find_layer1_candidates(noise_source) == [],
    )
    _check(
        "'Job 12:8' does NOT confirm against the noise string",
        not cvl.layer1_confirm("Job 12:8", noise_source),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Step 2b — Widened book-name forms (commit ee267d4): ordinal/spelled-word +
# Roman-numeral recognition flows through Layer 1 end-to-end
# ═══════════════════════════════════════════════════════════════════════════
# Confirms citation_verifier_layers.py's own layer1_confirm()/
# find_layer1_candidates() -- not just BOOK_MAP's dict membership -- resolve
# the ordinal/spelled-word and Roman-numeral book forms commit ee267d4 added
# to backend/app/constants.BOOK_MAP (34 new keys: 17 spelled-word like
# "first samuel", 17 Roman-numeral like "i samuel"). NOTE: ee267d4's own
# commit title says "ordinal/spelled-word/Roman-numeral" but the actual new
# BOOK_MAP keys fall into exactly two categories -- spelled-word ordinal
# ("first samuel", "second corinthians", "third john") and Roman-numeral
# ("i samuel", "ii corinthians", "iii john") -- there is no separate
# digit-ordinal-suffix book-name form (no "1st samuel"/"2nd corinthians" key
# exists anywhere in the map). The cases below cover both real categories
# across two different books (1 Samuel, 2 Corinthians, and 3 John -- the
# only NT book with a "third"/"iii" form) rather than inventing a third
# category that isn't actually in the map.
#
# Each case was independently confirmed, outside this test file, to resolve
# to False if run against the pre-ee267d4 BOOK_MAP (git ee267d4~1) -- these
# keys are genuinely new, not incidentally already-working forms.

def test_widened_book_name_forms():
    print("\n" + "=" * 78)
    print("Step 2b: widened book-name forms (commit ee267d4) — "
          "spelled-word ordinal + Roman-numeral")
    print("=" * 78)

    cases = [
        (
            "spelled-word ordinal book form — 'First Samuel' (new BOOK_MAP "
            "key, PATTERN_A)",
            "Turn with me to First Samuel chapter 3, verse 16, a well-known call story.",
            "First Samuel 3:16",
            ("1SA", 3, 16, None),
            "pattern_a_forward",
        ),
        (
            "Roman-numeral book form — 'I Samuel' (new BOOK_MAP key, PATTERN_A)",
            "Let us read from I Samuel chapter 3, verse 16 together this morning.",
            "I Samuel 3:16",
            ("1SA", 3, 16, None),
            "pattern_a_forward",
        ),
        (
            "spelled-word ordinal book form — 'Second Corinthians' (new "
            "BOOK_MAP key, PATTERN_B ordinal-chapter-of-book)",
            "Consider the third chapter of Second Corinthians, verse 16, a well-known text.",
            "Second Corinthians 3:16",
            ("2CO", 3, 16, None),
            "pattern_b_ordinal_chapter_of_book",
        ),
        (
            "Roman-numeral book form — 'III John' (new BOOK_MAP key, only "
            "NT book reaching a 'third'/'iii' form, PATTERN_A)",
            "Turn with me to III John chapter 1, verse 4 for a moment.",
            "III John 1:4",
            ("3JN", 1, 4, None),
            "pattern_a_forward",
        ),
    ]

    for label, source_text, reference, expected_parsed, expected_source in cases:
        confirmed = cvl.layer1_confirm(reference, source_text)
        _check(f"{label}: {reference!r} confirms in {source_text!r}", confirmed)

        candidates = cvl.find_layer1_candidates(source_text)
        matching = [c for c in candidates if c.parsed == expected_parsed]
        _check(
            f"{label}: a candidate with parsed tuple {expected_parsed} was found",
            len(matching) >= 1,
        )
        _check(
            f"{label}: that candidate is tagged source={expected_source!r} "
            "(proves it went through the actual pattern, not a coincidental match)",
            any(c.source == expected_source for c in matching),
        )


# ═══════════════════════════════════════════════════════════════════════════
# Step 3 — Layer 2: document-wide book scope
# ═══════════════════════════════════════════════════════════════════════════

def test_layer2_document_wide_scope():
    print("\n" + "=" * 78)
    print("Step 3: Layer 2 — document-wide book scope")
    print("=" * 78)

    # ── Positive: verse-only citation whose book is named once elsewhere
    #    in the document -> Layer 2 confirms. Also: single-book document ->
    #    multi_book_document is False. ────────────────────────────────────
    print("\n  -- Positive: book named elsewhere, chapter/verse found elsewhere --")
    single_book_doc = (
        "Today we are studying the book of Romans. It's a wonderful epistle "
        "full of doctrine. Later in our study, in chapter 8, verse 28, we "
        "find great comfort for those who love God."
    )
    result = cvl.layer2_confirm("Romans 8:28", single_book_doc)
    print(f"    result = {result}")
    _check("Layer 2 confirms 'Romans 8:28' (book + chapter/verse both present, separately)", result.confirmed)
    _check("single-book document -> multi_book_document is False", result.multi_book_document is False)
    _check("single-book document -> distinct_book_count == 1", result.distinct_book_count == 1)

    # Also confirm the top-level Layer1-then-Layer2 composition reaches
    # Layer 2 for this exact case (Layer 1 must NOT confirm it directly,
    # since the book and the chapter/verse never co-occur in one span).
    _check(
        "Layer 1 alone does NOT confirm this (book/chapter/verse never co-occur in one match)",
        not cvl.layer1_confirm("Romans 8:28", single_book_doc),
    )

    # ── Negative: verse-only citation to a book the document never names
    #    at all -> Layer 2 does NOT confirm. ─────────────────────────────
    print("\n  -- Negative: book never named anywhere in the document --")
    book_absent_doc = "In chapter 8, verse 28, we find great comfort for the weary."
    result = cvl.layer2_confirm("Romans 8:28", book_absent_doc)
    print(f"    result = {result}")
    _check("Layer 2 does NOT confirm when the book is never named at all", not result.confirmed)

    # ── Chapter precision: a "verse 25" with no chapter established
    #    anywhere -> does NOT satisfy condition 2. ──────────────────────
    print("\n  -- Chapter precision: verse-only mention, no chapter anywhere --")
    verse_only_doc = "In Romans, verse 28 encourages many believers facing hardship."
    result = cvl.layer2_confirm("Romans 8:28", verse_only_doc)
    print(f"    result = {result}")
    _check(
        "Layer 2 does NOT confirm when only a bare 'verse 28' (no chapter) is found",
        not result.confirmed,
    )

    # ── Chapter precision: the right verse under a DIFFERENT chapter than
    #    cited -> does NOT satisfy condition 2. ─────────────────────────
    print("\n  -- Chapter precision: right verse number, wrong chapter --")
    wrong_chapter_doc = (
        "Today we are studying the book of Romans. In chapter 9, verse 28, "
        "we find something else entirely, a different teaching."
    )
    result = cvl.layer2_confirm("Romans 8:28", wrong_chapter_doc)
    print(f"    result = {result}")
    _check(
        "Layer 2 does NOT confirm 'Romans 8:28' when the document only has "
        "'chapter 9, verse 28' (right verse, wrong chapter)",
        not result.confirmed,
    )

    # ── Multi-book accounting: one Layer-2 confirmation in a multi-book
    #    document -> multi_book_document is True, distinct_book_count > 1. ─
    print("\n  -- Multi-book accounting: confirmation in a multi-book document --")
    multi_book_doc = (
        "We will look at both Romans and Galatians today, two of Paul's greatest "
        "epistles. Paul's argument in chapter 8, verse 28 shows how all things "
        "work together for good."
    )
    result = cvl.layer2_confirm("Romans 8:28", multi_book_doc)
    print(f"    result = {result}")
    _check("Layer 2 confirms in the multi-book document", result.confirmed)
    _check("multi-book document -> multi_book_document is True", result.multi_book_document is True)
    _check("multi-book document -> distinct_book_count >= 2", result.distinct_book_count >= 2)


# ═══════════════════════════════════════════════════════════════════════════
# Step 4 — Layer 3: LLM read (mocked, no real network call)
# ═══════════════════════════════════════════════════════════════════════════

def make_call(sequence):
    """Returns a fake call_layer3_llm(reference, source_text) that pops the
    next scripted verdict off `sequence` on each call, tracking a call
    count -- mirrors test_rewrite_flagged_statement.py's make_call()
    convention exactly."""
    calls = {"n": 0}

    def _fake(reference, source_text):
        verdict = sequence[calls["n"]]
        calls["n"] += 1
        return verdict
    _fake.call_count = lambda: calls["n"]
    return _fake


def test_layer3_llm_gating_and_parsing():
    print("\n" + "=" * 78)
    print("Step 4: Layer 3 — LLM read, mocked (zero real network calls)")
    print("=" * 78)

    already_confirmed_source = "As it says in Hebrews 10:25, let us not neglect meeting together."
    unconfirmed_source = "The teacher spoke generally about faithfulness and prayer that evening."

    # ── Layer 3 is invoked ONLY when Layers 1 AND 2 both fail AND
    #    llm_enabled=True. Case A: Layers 1/2 already confirm -> call count
    #    stays 0. ───────────────────────────────────────────────────────
    print("\n  -- Gating: Layers 1/2 confirm -> Layer 3 never called --")
    fake = make_call([True])  # scripted verdict irrelevant; must never be consumed
    original = cvl.call_layer3_llm
    cvl.call_layer3_llm = fake
    try:
        result = cvl.verify_reference_grounded(
            "Hebrews 10:25", already_confirmed_source, llm_enabled=True,
        )
    finally:
        cvl.call_layer3_llm = original
    print(f"    result = {result}, LLM call count = {fake.call_count()}")
    _check("Layer 1 confirms this case", result.confirmed and result.layer == 1)
    _check("Layer 3 LLM call count is 0 when Layers 1/2 already confirm", fake.call_count() == 0)

    # ── Case B: Layers 1/2 do NOT confirm, llm_enabled=True -> call count
    #    is exactly 1. ────────────────────────────────────────────────────
    print("\n  -- Gating: Layers 1/2 fail, llm_enabled=True -> Layer 3 called once --")
    fake = make_call([True])
    cvl.call_layer3_llm = fake
    try:
        result = cvl.verify_reference_grounded(
            "Hebrews 10:25", unconfirmed_source, llm_enabled=True,
        )
    finally:
        cvl.call_layer3_llm = original
    print(f"    result = {result}, LLM call count = {fake.call_count()}")
    _check("Layer 3 LLM call count is exactly 1 when Layers 1/2 fail and llm_enabled=True", fake.call_count() == 1)
    _check("a mocked 'yes' (True) response -> confirmed via layer 3", result.confirmed and result.layer == 3)

    # ── Case C: Layers 1/2 do NOT confirm, llm_enabled=False (default) ->
    #    Layer 3 never called at all. ────────────────────────────────────
    print("\n  -- Gating: Layers 1/2 fail, llm_enabled=False (default) -> Layer 3 never called --")
    fake = make_call([True])
    cvl.call_layer3_llm = fake
    try:
        result = cvl.verify_reference_grounded("Hebrews 10:25", unconfirmed_source)
    finally:
        cvl.call_layer3_llm = original
    print(f"    result = {result}, LLM call count = {fake.call_count()}")
    _check("llm_enabled defaults to False", not result.confirmed and result.reason == "not_confirmed_llm_disabled")
    _check("Layer 3 LLM call count is 0 when llm_enabled=False", fake.call_count() == 0)

    # ── A mocked 'no' (False) response -> not confirmed. ─────────────────
    print("\n  -- A mocked 'no' response -> not confirmed --")
    fake = make_call([False])
    cvl.call_layer3_llm = fake
    try:
        result = cvl.verify_reference_grounded(
            "Hebrews 10:25", unconfirmed_source, llm_enabled=True,
        )
    finally:
        cvl.call_layer3_llm = original
    print(f"    result = {result}, LLM call count = {fake.call_count()}")
    _check("a mocked 'no' (False) response -> not confirmed", not result.confirmed and result.layer is None)
    _check("reason reports layer3 denial", result.reason == "layer3_llm_denied")
    _check("Layer 3 LLM call count is exactly 1", fake.call_count() == 1)

    # ── call_layer3_llm() itself: JSON parsing, markdown-fence stripping,
    #    and LLMVerificationFailed on malformed responses -- exercised
    #    directly (not through verify_reference_grounded), with a fully
    #    mocked Groq client so zero real network calls happen. ───────────
    print("\n  -- call_layer3_llm(): JSON parsing + fence-stripping, mocked Groq client --")

    class _FakeMessage:
        def __init__(self, content):
            self.content = content

    class _FakeChoice:
        def __init__(self, content):
            self.message = _FakeMessage(content)

    class _FakeResponse:
        def __init__(self, content):
            self.choices = [_FakeChoice(content)]

    class _FakeCompletions:
        def __init__(self, raw):
            self._raw = raw
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            return _FakeResponse(self._raw)

    class _FakeChat:
        def __init__(self, raw):
            self.completions = _FakeCompletions(raw)

    class _FakeGroqClient:
        def __init__(self, raw):
            self.chat = _FakeChat(raw)

    original_get_groq = cvl.pw._get_groq

    # Valid response, wrapped in markdown fences (must be stripped).
    fenced_client = _FakeGroqClient('```json\n{"engaged": true}\n```')
    cvl.pw._get_groq = lambda: fenced_client
    try:
        verdict = cvl.call_layer3_llm("Hebrews 10:25", "some source text")
    finally:
        cvl.pw._get_groq = original_get_groq
    _check("markdown-fenced JSON response parses correctly (engaged=True)", verdict is True)
    _check("exactly one mocked .create() call made", fenced_client.chat.completions.calls == 1)

    # Malformed response (not valid JSON) -> LLMVerificationFailed, never a
    # silently guessed verdict.
    bad_client = _FakeGroqClient("this is not json at all")
    cvl.pw._get_groq = lambda: bad_client
    raised = False
    try:
        cvl.call_layer3_llm("Hebrews 10:25", "some source text")
    except cvl.LLMVerificationFailed:
        raised = True
    finally:
        cvl.pw._get_groq = original_get_groq
    _check("malformed (non-JSON) response raises LLMVerificationFailed, never guesses", raised)

    # Wrong-shape response (missing 'engaged' key) -> LLMVerificationFailed.
    wrong_shape_client = _FakeGroqClient('{"verdict": "yes"}')
    cvl.pw._get_groq = lambda: wrong_shape_client
    raised = False
    try:
        cvl.call_layer3_llm("Hebrews 10:25", "some source text")
    except cvl.LLMVerificationFailed:
        raised = True
    finally:
        cvl.pw._get_groq = original_get_groq
    _check("response missing 'engaged' key raises LLMVerificationFailed", raised)


# ═══════════════════════════════════════════════════════════════════════════
# Step 5 — Composition: verify_reference_grounded()
# ═══════════════════════════════════════════════════════════════════════════

def test_composition():
    print("\n" + "=" * 78)
    print("Step 5: Composition — verify_reference_grounded()")
    print("=" * 78)

    # ── Unparseable reference -> confirmed=False, layer=None, reason names it. ─
    print("\n  -- Unparseable reference-under-test --")
    result = cvl.verify_reference_grounded("that chapter somewhere", "some source text")
    print(f"    result = {result}")
    _check("unparseable reference -> confirmed False", not result.confirmed)
    _check("unparseable reference -> layer None", result.layer is None)
    _check("unparseable reference -> reason names it", result.reason == "unparseable_reference")

    # ── Layer 1 short-circuits before Layer 2/3 ever run. ────────────────
    print("\n  -- Layer 1 confirms, short-circuits --")
    result = cvl.verify_reference_grounded(
        "Hebrews 10:25", "As it says in Hebrews 10:25, let us not neglect meeting together.",
    )
    print(f"    result = {result}")
    _check("Layer 1 confirms", result.confirmed and result.layer == 1)

    # ── Layer 2 confirms when Layer 1 alone cannot (book and chapter/verse
    #    never co-occur in one span). ────────────────────────────────────
    print("\n  -- Layer 2 confirms when Layer 1 cannot --")
    doc = (
        "Today we are studying the book of Romans, a wonderful epistle. "
        "Later in our study, in chapter 8, verse 28, we find great comfort."
    )
    result = cvl.verify_reference_grounded("Romans 8:28", doc)
    print(f"    result = {result}")
    _check("Layer 2 confirms via the full composition", result.confirmed and result.layer == 2)
    _check("Layer 2's multi_book_document/distinct_book_count propagate to the top-level result",
           result.distinct_book_count == 1 and result.multi_book_document is False)

    # ── Neither Layer 1 nor 2 confirms, llm_enabled=False -> not confirmed,
    #    explicit reason, no exception. ──────────────────────────────────
    print("\n  -- Neither layer confirms, llm_enabled=False (default) --")
    result = cvl.verify_reference_grounded(
        "Hebrews 10:25", "The teacher spoke generally about faithfulness that evening.",
    )
    print(f"    result = {result}")
    _check("not confirmed", not result.confirmed)
    _check("reason reports LLM disabled", result.reason == "not_confirmed_llm_disabled")


def test_dot_normalization_regression():
    """Regression proof for the 2026-07-29 fix: this module's OWN three
    reference-under-test parse sites (layer1_confirm(), layer2_confirm(),
    verify_reference_grounded()) previously called
    `_parse_verse_or_range(reference.strip())` directly, with no dot
    normalization -- a SEPARATE copy of the exact defect Step 1 fixed one
    file upstream in reference_grounding.check_reference_grounded(). Found
    live, not hypothetical: a genuine dotted reference (e.g. "1 Cor. 9:27")
    that survives propositions.py's now-fixed primary check and reaches
    arbitration would fail to parse HERE, short-circuit to
    confirmed=False/reason="unparseable_reference" before Layers 1-3 ever
    ran, and get wrongly STRIPPED via propositions.py's
    arbitration_unavailable_unparseable fail-safe branch -- a false strip
    of a genuine reference, exactly the loss class Invariant 11 exists to
    prevent.

    First proves the PRE-FIX defect was real (direct call to the same
    un-normalized parse this module's own call sites used to make), then
    proves the FIX: the same dotted reference now reaches Layer 1 (and,
    separately, Layer 2) instead of short-circuiting."""
    print("\n" + "=" * 78)
    print("Step 6: dot-normalization regression (2026-07-29 fix)")
    print("=" * 78)

    # ── Prove the pre-fix defect was real: the raw, un-normalized parse
    #    this module's three call sites used to make, called directly. ─────
    print("\n  -- Pre-fix defect, proven directly --")
    from app.services.reference_verifier import _parse_verse_or_range
    _check(
        "un-normalized _parse_verse_or_range('1 Cor. 9:27'.strip()) returns "
        "None -- confirms the pre-fix short-circuit was real, not hypothetical",
        _parse_verse_or_range("1 Cor. 9:27".strip()) is None,
    )

    # ── Layer 1: a dotted reference-under-test, checked against a source
    #    that engages it via a WIDENED spoken form (not the compact form) --
    #    proves the fix lives in the reference-under-test's own parse, not
    #    merely in find_reference_spans()'s pre-existing dot handling on the
    #    SOURCE side (which was already correct before this fix). ─────────
    print("\n  -- Layer 1 confirms a dotted reference-under-test --")
    spoken_source = (
        "Paul talks about this in First Corinthians chapter 9 verse 27 "
        "where he disciplines his body."
    )
    _check(
        "layer1_confirm('1 Cor. 9:27', ...) confirms against a widened "
        "spoken-form source (post-fix; pre-fix this returned False)",
        cvl.layer1_confirm("1 Cor. 9:27", spoken_source),
    )

    # ── Layer 2: a dotted reference-under-test, checked against a source
    #    where the book and the chapter/verse are named separately (Layer 1
    #    alone cannot confirm; only reachable if the dotted reference
    #    parses in the first place). ─────────────────────────────────────
    print("\n  -- Layer 2 confirms a dotted reference-under-test --")
    layer2_source = (
        "Today we are studying the book of Romans, a wonderful epistle. "
        "Later in our study, in chapter 8, verse 28, we find great comfort."
    )
    layer2_result = cvl.layer2_confirm("Rom. 8:28", layer2_source)
    print(f"    layer2_confirm('Rom. 8:28', ...) -> {layer2_result}")
    _check(
        "layer2_confirm('Rom. 8:28', ...) confirms (post-fix; pre-fix "
        "the un-normalized parse would have failed before Layer 2's own "
        "book/chapter-verse scan ever ran)",
        layer2_result.confirmed,
    )

    # ── Composition (the exact path propositions.py's arbiter call takes):
    #    verify_reference_grounded() must reach Layer 1 and CONFIRM, not
    #    short-circuit to "unparseable_reference". This is the precise
    #    false-strip path the reviewer traced through propositions.py's
    #    arbitration_unavailable_unparseable branch. ─────────────────────
    print("\n  -- verify_reference_grounded() reaches Layer 1, does NOT "
          "short-circuit to 'unparseable_reference' --")
    result = cvl.verify_reference_grounded("1 Cor. 9:27", spoken_source, llm_enabled=False)
    print(f"    result = {result}")
    _check(
        "dotted '1 Cor. 9:27' confirms via Layer 1 through the FULL "
        "composition function -- the exact call propositions.py's "
        "arbiter makes",
        result.confirmed and result.layer == 1,
    )
    _check(
        "reason is 'layer1_widened_scan_match', NOT 'unparseable_reference' "
        "-- proves Layers 1-3 actually ran instead of short-circuiting",
        result.reason == "layer1_widened_scan_match",
    )

    # ── Second dotted form ("Matt. 5:8"), compact form on the source side,
    #    to prove the fix isn't narrowly tied to one book abbreviation or
    #    one widened pattern. ─────────────────────────────────────────────
    print("\n  -- Second dotted form, compact-form source ('Matt. 5:8') --")
    compact_source_matt = "Jesus said in Matthew 5:8 that the pure in heart will see God."
    result_matt = cvl.verify_reference_grounded("Matt. 5:8", compact_source_matt, llm_enabled=False)
    print(f"    result = {result_matt}")
    _check(
        "dotted 'Matt. 5:8' confirms (via Layer 1's reused compact-form "
        "scanner) instead of short-circuiting to 'unparseable_reference'",
        result_matt.confirmed and result_matt.reason == "layer1_widened_scan_match",
    )


def main():
    print("#" * 78)
    print("test_citation_verifier_layers.py")
    print("#" * 78)

    test_number_converter()
    test_layer1_widened_forms()
    test_widened_book_name_forms()
    test_layer2_document_wide_scope()
    test_layer3_llm_gating_and_parsing()
    test_composition()
    test_dot_normalization_regression()

    print("\n" + "#" * 78)
    print("All assertions passed.")
    print("#" * 78)


if __name__ == "__main__":
    main()
