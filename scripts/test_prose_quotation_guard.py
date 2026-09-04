#!/usr/bin/env python3
"""
Regression suite for `app.services.prose_quotation_guard`.

Credential-free and offline: every fixture below is REAL text -- the
answer prose comes from `scripts/sp1_answer_quality_baseline.json`, the
evidence comes from live `chunks` rows -- captured during the audit at
`docs/audits/2026-08/scripture_and_quotation_fidelity_2026-08-31.md`. No
database, no model, no network.

Run from project root:  python3.12 scripts/test_prose_quotation_guard.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services import prose_quotation_guard as guard

FAILURES = []
CHECKS = [0]


def check(label, condition, detail=""):
    CHECKS[0] += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"\n          {detail}" if detail else ""))
        FAILURES.append(label)


# --- Real corpus evidence (verbatim, including original curly punctuation) ---

KOLENDA_GRUDEM = (
    'reformed, by the way, called The Gift of Prophecy in the New Testament and '
    'today. And one of the most interesting parts in the book is when he talks '
    'about the way that the word prophecy is used in the Greek. He says, "By the '
    'time of the New Testament, the term prophetes in everyday use often simply '
    'meant one who has supernatural knowledge, or one who predicts the future, or '
    'even just spokesman without any connotations of divine authority."'
)
KOLENDA_WEIRD = (
    "many times. It's not something weird; it's not something unusual in Full "
    "Gospel circles. This kind of prophetic ministry is part of the normal, "
    "ongoing, weekly life of the church that I pastor. When God speaks to you,"
)
PRINCE_LAMPSTAND = (
    "I believe that the function that Don and I have in this conference is to "
    "pipe the fresh oil into the lampstand. If you want to say that’s the "
    "prophetic ministry, I will not say no."
)
# NOTE the curly U+2018 apostrophes -- this is exactly how the corpus stores it.
PRINCE_DECADES = (
    "ing it. But what brought success in the ‘60s brings death in the "
    "‘70s. And what brings life in the ‘70s may we"
)
PRINCE_TIMING = (
    "now. It’s the answer to the question, “What should we do at this "
    "time? Should we build? Should we break down?"
)
BROWN_SIGN = (
    "fts operate through them. However, it is the most common sign of the "
    "baptism of the Spirit."
)

ALL_EVIDENCE = [
    guard.QuotationEvidence(KOLENDA_GRUDEM, "Daniel Kolenda"),
    guard.QuotationEvidence(KOLENDA_WEIRD, "Daniel Kolenda"),
    guard.QuotationEvidence(PRINCE_LAMPSTAND, "Derek Prince"),
    guard.QuotationEvidence(PRINCE_DECADES, "Derek Prince"),
    guard.QuotationEvidence(PRINCE_TIMING, "Derek Prince"),
    guard.QuotationEvidence(BROWN_SIGN, "Michael Brown"),
]
NAMES = ["Daniel Kolenda", "Derek Prince", "Michael Brown"]


def flagged(answer, evidence=None, names=None):
    return guard.ungrounded_prose_quotations(
        answer, evidence if evidence is not None else ALL_EVIDENCE,
        names if names is not None else NAMES,
    )


print("\n=== 1. The measured defects must be caught ===")

FABRICATED = (
    'The biblical word prophetes itself carried a broader meaning than modern '
    'readers assume. As Kolenda points out, it often meant simply "one who has '
    'supernatural knowledge" or "one who declares something not his own" — '
    'not automatically one who speaks with absolute divine authority.'
)
res = flagged(FABRICATED, names=["Kolenda"])
check(
    "fabricated Kolenda quotation is flagged",
    any("declares something not his own" in q.text for q in res),
    f"got {[q.text for q in res]}",
)

ALTERED = (
    'Derek Prince describes the prophetic ministry as "piping fresh oil into the '
    'lampstand" — supplying the church with an absolutely current '
    'understanding of what God is doing now.'
)
res = flagged(ALTERED)
check(
    "altered Prince quotation is flagged (real text is 'to pipe the fresh oil')",
    any("piping fresh oil" in q.text for q in res),
    f"got {[q.text for q in res]}",
)

# Measured live on the real baseline: the answer closed the quotation early
# with a period the source does not have, turning Kolenda's statement about
# "the church that I pastor" into one about the church universal. Settled #16
# names this hazard directly -- a trim can change meaning while passing every
# other check.
TRUNCATED = (
    'According to Daniel Kolenda, this is ordinary church life. In his words, '
    '"It\'s not something weird; it\'s not something unusual in Full Gospel '
    'circles. This kind of prophetic ministry is part of the normal, ongoing, '
    'weekly life of the church."'
)
res = flagged(TRUNCATED)
check(
    "quotation truncated past a real sentence boundary is flagged",
    bool(res),
    "the source reads '...life of the church THAT I PASTOR.'",
)


print("\n=== 2. The measured CLEAN quotations must NOT be flagged ===")

CLEAN_CASES = [
    (
        "Kolenda quotation ending at a real sentence boundary",
        'According to Daniel Kolenda, most prophetic activity does not look like a '
        'spotlight. In his words, "It\'s not something weird; it\'s not something '
        'unusual in Full Gospel circles."',
    ),
    (
        "Prince decades quotation (STRAIGHT ' in answer vs CURLY ‘ in corpus)",
        'Prince warns that "what brought success in the \'60s brings death in the '
        '\'70s" — the church needs continual fresh revelation.',
    ),
    (
        "Prince timing quotation",
        'Derek Prince framed the prophetic as answering the question: "What should '
        'we do at this time?" It is discernment of the present moment.',
    ),
    (
        "Brown quotation",
        'According to Michael Brown, this pattern establishes tongues as "the most '
        'common sign of the baptism of the Spirit", even if not the only one.',
    ),
]
for label, text in CLEAN_CASES:
    res = flagged(text)
    check(f"clean: {label}", not res, f"falsely flagged {[q.text for q in res]}")


print("\n=== 3. Deliberate non-targets must never fire ===")

SCARE = (
    'Derek Prince disagreed sharply, but New Wine never adopts words like '
    '"heretical" or "apostate" in its own voice.'
)
check("short scare quotes are ignored", not flagged(SCARE))

# Both halves of this were live false positives before the negated-
# introduction exclusion existed -- 2 of 5 flags on the real answers.
HYPOTHETICAL = (
    'According to Michael Brown, the pattern is clear. There is no passage that '
    'says, "Tongues will cease with the apostles," or "This gift is for the '
    'founding generation only."'
)
res = flagged(HYPOTHETICAL)
check(
    "negated hypothetical quotations are excluded (both halves of the list)",
    not res,
    f"falsely flagged {[q.text for q in res]}",
)

# The exclusion must not become an evasion: a negation in a PRIOR sentence
# is separated by a terminator and must not excuse a real fabrication.
NEGATION_EVASION = (
    'There is no passage that says otherwise. Derek Prince taught that the '
    'ministry is "piping fresh oil into the lampstand" for the church.'
)
res = flagged(NEGATION_EVASION)
check(
    "a negation in a PRIOR sentence does not excuse a fabrication",
    bool(res),
    "negation scoping leaked across a sentence boundary -- this is an evasion",
)

SCRIPTURE_TRAILING = (
    'According to Daniel Kolenda, Paul closes the instruction with "do not forbid '
    'speaking in tongues" (1 Cor 14:39), which settles the matter.'
)
res = flagged(SCRIPTURE_TRAILING)
check(
    "quoted Scripture with a TRAILING citation is excluded",
    not res,
    f"falsely flagged {[q.text for q in res]}",
)

SCRIPTURE_LEADING = (
    'Derek Prince pointed to this often. Ephesians 5:18 commands believers to '
    '"be continually maintained full of the Holy Spirit" as an ongoing state.'
)
res = flagged(SCRIPTURE_LEADING)
check(
    "quoted Scripture with a LEADING citation is excluded",
    not res,
    f"falsely flagged {[q.text for q in res]}",
)

UNATTRIBUTED = (
    'Some teachers have said "one who declares something not his own" about the '
    'prophetic office, without naming anyone in particular.'
)
check(
    "an unattributed quotation is out of scope (no permitted name nearby)",
    not flagged(UNATTRIBUTED, names=["Derek Prince"]),
)


print("\n=== 4. Fail-closed and boundary behaviour ===")

check(
    "no evidence at all => every attributed quotation is unsupported",
    len(flagged(ALTERED, evidence=[])) == 1,
)
check("empty answer returns nothing", not flagged("", evidence=ALL_EVIDENCE))
check("no permitted names returns nothing", not flagged(ALTERED, names=[]))
check(
    "attribution beyond the window does not qualify",
    not flagged("Derek Prince taught. " + ("x " * 300) + '"piping fresh oil into the lampstand here"'),
)


print("\n=== 5. KNOWN LIMITATION, asserted so it cannot be mistaken for coverage ===")

NESTED = (
    'As Kolenda points out, the term often meant simply "one who has supernatural '
    'knowledge" in ordinary Greek usage of the period.'
)
res = flagged(NESTED, names=["Kolenda"])
check(
    "nested quotation (Grudem's words credited to Kolenda) is NOT caught -- by design",
    not res,
    "if this now FAILS, the guard gained nested-attribution coverage; update the "
    "module docstring and the audit before celebrating",
)


print("\n=== 6. Mutation proofs -- each guard must be load-bearing ===")

# M1: normalization
original_normalize = guard.normalize_for_match
guard.normalize_for_match = lambda t: t  # identity == the near-bug
res = flagged(
    'Prince warns that "what brought success in the \'60s brings death in the '
    '\'70s" today.'
)
guard.normalize_for_match = original_normalize
check(
    "MUTATION: without normalization, a CLEAN curly-quote citation is falsely flagged",
    bool(res),
    "normalization is not load-bearing -- the curly/straight fold did nothing",
)

# M2: minimum length
original_min = guard.MIN_QUOTED_WORDS
guard.MIN_QUOTED_WORDS = 1
res = flagged(SCARE)
guard.MIN_QUOTED_WORDS = original_min
check(
    "MUTATION: with no length floor, scare quotes are falsely flagged",
    bool(res),
    "MIN_QUOTED_WORDS is not load-bearing",
)

# M3: scripture exclusion
original_re = guard._SCRIPTURE_REF_RE
guard._SCRIPTURE_REF_RE = __import__("re").compile(r"(?!x)x")  # never matches
res = flagged(SCRIPTURE_LEADING)
guard._SCRIPTURE_REF_RE = original_re
check(
    "MUTATION: without Scripture exclusion, quoted verses are falsely flagged",
    bool(res),
    "the Scripture exclusion is not load-bearing",
)

# M4: attribution window
original_window = guard.ATTRIBUTION_WINDOW_CHARS
guard.ATTRIBUTION_WINDOW_CHARS = 0
res = flagged(ALTERED)
guard.ATTRIBUTION_WINDOW_CHARS = original_window
check(
    "MUTATION: with a zero attribution window, the real defect is missed",
    not res,
    "the attribution window is not load-bearing",
)


# M5: negated-introduction exclusion
original_neg = guard._NEGATED_INTRODUCTION_RE
guard._NEGATED_INTRODUCTION_RE = __import__("re").compile(r"(?!x)x")
res = flagged(HYPOTHETICAL)
guard._NEGATED_INTRODUCTION_RE = original_neg
check(
    "MUTATION: without the negation exclusion, hypotheticals are falsely flagged",
    bool(res),
    "the negated-introduction exclusion is not load-bearing",
)


print("\n=== 7. Author scope and unpunctuated-transcript fallback ===")

UNPUNCTUATED_BROWN = (
    "the most common sign of the baptism of the Spirit even if it is not the "
    "only sign"
)
NATURALLY_PUNCTUATED = (
    'Michael Brown calls tongues "the most common sign of the baptism of the '
    'Spirit, even if it is not the only sign."'
)
res = flagged(
    NATURALLY_PUNCTUATED,
    evidence=[guard.QuotationEvidence(UNPUNCTUATED_BROWN, "Michael Brown")],
)
check(
    "natural sentence punctuation is tolerated for evidence with no terminator",
    not res,
    f"falsely flagged {[q.text for q in res]}",
)

res = flagged(
    NATURALLY_PUNCTUATED,
    evidence=[guard.QuotationEvidence(UNPUNCTUATED_BROWN + ".", "Michael Brown")],
)
check(
    "punctuation fallback is disabled for normally punctuated evidence",
    bool(res),
    "punctuation-bearing evidence must retain strict comparison",
)


res = guard.ungrounded_prose_quotations(
    'Derek Prince taught that tongues are "the most common sign of the '
    'baptism of the Spirit."',
    [
        guard.QuotationEvidence(
            "Derek Prince discussed spiritual gifts", "Derek Prince"
        ),
        guard.QuotationEvidence(UNPUNCTUATED_BROWN, "Michael Brown"),
    ],
    ["Derek Prince", "Michael Brown"],
)
check(
    "another teacher's chunk cannot ground an attributed quotation",
    bool(res),
    f"got {[q.text for q in res]}",
)

res = guard.ungrounded_prose_quotations(
    'Michael Brown taught that "faith grows through patient endurance."',
    [
        guard.QuotationEvidence("faith grows through", "Michael Brown"),
        guard.QuotationEvidence("patient endurance", "Michael Brown"),
    ],
    ["Michael Brown"],
)
check(
    "a quotation cannot bridge two same-author chunks",
    bool(res),
    f"got {[q.text for q in res]}",
)

nearest = guard.extract_attributed_quotations(
    'Derek Prince introduced the topic. Michael Brown taught, "the most common '
    'sign of the baptism of the Spirit."',
    ["Derek Prince", "Michael Brown"],
)
check(
    "the nearest preceding teacher controls attribution",
    len(nearest) == 1 and nearest[0].attributed_to == "Michael Brown",
    f"got {[q.attributed_to for q in nearest]}",
)

inside_only = guard.extract_attributed_quotations(
    'The answer includes "Derek Prince offered these words to the whole church."',
    ["Derek Prince"],
)
check(
    "a teacher named only inside the quotation is not its attribution",
    not inside_only,
    f"got {[q.attributed_to for q in inside_only]}",
)

STRICT_VARIANTS = [
    (
        "apostrophe changes remain strict",
        'Michael Brown said, "we can\'t treat this sign as the only evidence."',
        "we cant treat this sign as the only evidence",
    ),
    (
        "hyphen changes remain strict",
        'Michael Brown described this as "a Spirit-given sign for every believer."',
        "a Spirit given sign for every believer",
    ),
    (
        "word-order changes remain strict",
        'Michael Brown taught that "patient faith produces endurance in every trial."',
        "faith produces patient endurance in every trial",
    ),
]
for label, answer, evidence in STRICT_VARIANTS:
    check(
        label,
        bool(
            flagged(
                answer,
                evidence=[guard.QuotationEvidence(evidence, "Michael Brown")],
            )
        ),
    )


print(f"\n{'=' * 62}")
if FAILURES:
    print(f"FAILED {len(FAILURES)}/{CHECKS[0]}:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print(f"All {CHECKS[0]} checks passed.")
