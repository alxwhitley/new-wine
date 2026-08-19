"""
SP1 reference-pointer verifier. Takes what the writer PROPOSED (parsed from
the model's <reference_mentions> block) and what the model ACTUALLY WROTE
(the final <answer> text), and returns only the subset that survives every
independent guard below. Anything that fails any guard is dropped silently
— this module never raises past its own top-level try/except, and never
partially-credits a mention.

Guard order (all four required, in this order for efficiency — a mention
must survive all of them):
  1. Presence  — the proposed string must literally appear in answer_text.
     Also the SOLE source of occurrence positions (verses: every match;
     teachers: first match only) — the model's own claims are never
     trusted for position.
  2. Resolution — verses: parse_ref (single or range) + a real verses-table
     row for every endpoint. Teachers: alias-key lookup against
     source_aliases, must not be the sentinel/MISS, must pass the license/
     visibility gate (is_source_servable).
  3. Biblical-figure backstop — independent of #2's result. Runs regardless
     of what source_aliases says.

After all four guards, one more pass runs over the surviving, already-
verified list: overlap de-duplication (see _deduplicate_overlapping_spans).
The writer is instructed to list every verse it names, including repeats,
so it never deduplicates a range against its own start verse (e.g. it
proposes "Romans 8:26-28" AND "Romans 8:26" as separate lines, because it
did name 8:26 — as the front half of the range). Both proposals are
individually true and both survive guards 1-3 independently; the result is
two verified references anchored at the same textual span. This pass fixes
that by keeping the longer of any two overlapping spans and dropping the
shorter — it is not a fifth validity guard (it never makes a resolvable
reference unresolvable), just a precedence rule for spans two already-
verified references both claim.

See docs/superpowers/plans/2026-07-14-sp1-reference-pointer-backend.md for
the full design rationale.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.constants import resolve_book_abbrev
from app.services.biblical_figures import is_biblical_figure
from app.services.source_resolver import is_source_servable, normalize_alias_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievalGrounding:
    """The set of teachers whose material was actually retrieved for THIS
    question, in the two forms a named teacher can match against it (Phase 2
    teacher-name guard, validated by the 2026-08-01 Phase 0 pass, §4a):

      - `source_ids`: the `documents.source_id` of every retrieved chunk.
      - `author_keys`: the `normalize_alias_key`-normalized `author` of every
        retrieved chunk.

    A teacher is grounded if EITHER its alias-resolved source_id is in
    `source_ids` OR its normalized name is in `author_keys`. The author-key
    arm is the hard design constraint from Phase 0 (requirement 1): it keys
    on retrieved IDENTITY, not alias resolution, so a legitimately-retrieved
    teacher with NO `source_aliases` row (Andrew Murray — the alias-gap
    Landmine) is not false-flagged.

    `established` is False when the set could not be built (a DB failure while
    mapping document_id -> source_id). In that state EVERY teacher is treated
    as ungrounded, so the guard fails CLOSED — it denies all teacher links
    rather than passing them (the fail-open shape that bit the 01ca912
    session must not recur here).
    """
    source_ids: frozenset = frozenset()
    author_keys: frozenset = frozenset()
    established: bool = True


def build_retrieval_grounding(chunks: List[dict], db) -> "RetrievalGrounding":
    """Build a `RetrievalGrounding` from the exact chunk list the model was
    given as context. Fails CLOSED: any exception mapping document_id ->
    source_id yields `established=False` (all teachers ungrounded).

    Partial results are NOT a failure — a retrieved document whose row is
    absent from the `documents` lookup simply contributes no source_id; its
    author is still captured from the chunk, so a teacher retrieved through
    it is still grounded via the author-key arm. Only a raised exception
    (the whole lookup failing) trips the fail-closed path.
    """
    try:
        author_keys = set()  # type: set
        doc_ids = set()      # type: set
        for c in chunks:
            author = c.get("author")
            if author:
                k = normalize_alias_key(author)
                if k:
                    author_keys.add(k)
            did = c.get("document_id")
            if did:
                doc_ids.add(did)

        source_ids = set()  # type: set
        if doc_ids:
            resp = (
                db.table("documents").select("id, source_id").in_("id", sorted(doc_ids)).execute()
            )
            for row in (resp.data or []):
                sid = row.get("source_id")
                if sid:
                    source_ids.add(sid)

        return RetrievalGrounding(
            source_ids=frozenset(source_ids),
            author_keys=frozenset(author_keys),
            established=True,
        )
    except Exception:
        logger.exception(
            "build_retrieval_grounding failed — failing CLOSED (no teacher links this answer)"
        )
        return RetrievalGrounding(established=False)


def _is_retrieval_grounded(
    name: str, source_id: Optional[str], grounding: "RetrievalGrounding"
) -> bool:
    """DETECTION predicate: was a teacher with this name/source retrieved for
    this question at all? Both arms — source-id OR author-name — because the
    author-name arm is what stops a legitimately-retrieved teacher with no
    alias row (Andrew Murray) from being mis-classified as a fabrication. Used
    for measurement/reporting, NOT for the verified-link decision (see
    `_link_source_retrieved` for why the link decision is stricter). Fails
    CLOSED when the grounding set could not be established.
    """
    if not grounding.established:
        return False  # fail closed — set unavailable, trust nothing
    if source_id is not None and source_id in grounding.source_ids:
        return True
    if normalize_alias_key(name) in grounding.author_keys:
        return True
    return False


def _link_source_retrieved(source_id: str, grounding: "RetrievalGrounding") -> bool:
    """LINK-grant gate: a verified teacher link points at `source_id` (the
    alias-resolved source), so the link is allowed only when THAT source was
    actually retrieved — the source-id arm ALONE, deliberately NOT the
    author-name arm.

    Why the author-name arm is excluded here (but kept in the detection
    predicate above): the author arm matches a name against the retrieved
    authors regardless of which source_id it resolved to. If a name resolves to
    a servable-but-not-retrieved source B, and a DIFFERENT retrieved source A
    happens to carry an author with the same normalized name (a homonym across
    the corpus), the author arm would grant a verified link to B on material
    that actually came from A — a verified link to unretrieved material, the
    exact misattribution this guard exists to prevent. The author arm's
    legitimate purpose (the Andrew-Murray alias-gap) is the no-source_id case,
    which never earns a link anyway (verify_teacher_mention returns None at the
    no-alias check before this gate). So restricting the link to the source-id
    arm loses no legitimate link and closes the homonym hole.

    Fails CLOSED when the grounding set could not be established.
    """
    if not grounding.established:
        return False  # fail closed
    return source_id in grounding.source_ids

_MENTIONS_BLOCK_RE = re.compile(
    r"<reference_mentions>(.*?)</reference_mentions>", re.DOTALL
)
_MENTION_LINE_RE = re.compile(r"^(VERSE|TEACHER):\s*(.+)$")

_SENTINEL_SOURCE_ID = "267a09ac-76f3-43fb-901f-3015aef88e22"


def parse_reference_mentions(raw_output: str) -> List[Dict]:
    """Extract and parse the <reference_mentions> block from the model's
    full raw output. Malformed or missing lines are skipped individually —
    never fatal, never drops the whole block for one bad line.
    """
    block_match = _MENTIONS_BLOCK_RE.search(raw_output)
    if not block_match:
        return []

    proposals = []  # type: List[Dict]
    for line in block_match.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        m = _MENTION_LINE_RE.match(line)
        if not m:
            continue  # malformed line — skip silently, per-line fail-quiet
        kind, raw = m.group(1), m.group(2).strip()
        if not raw:
            continue
        proposals.append({"type": "verse" if kind == "VERSE" else "teacher", "raw": raw})
    return proposals


def find_occurrences(answer_text: str, raw: str) -> List[int]:
    """Literal, case-sensitive substring search. Returns every match start
    index, or [] if the string never appears — this IS the presence check.
    """
    if not raw:
        return []
    positions = []
    start = 0
    while True:
        idx = answer_text.find(raw, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def _parse_verse_or_range(ref: str) -> Optional[Tuple[str, int, int, Optional[int]]]:
    r"""Parse 'Romans 8:28' or 'Romans 8:26-28' / 'Romans 8:26–28' /
    'Romans 8:26—28' (em-dash — confirmed the model reaches for these
    constantly in its own prose) into (abbrev, chapter, verse_start,
    verse_end_or_None). Reuses the same
    book-name resolution app.routers.study.parse_ref also uses (both call
    the shared app.constants.resolve_book_abbrev()) — this is an extension
    to support ranges, not a fork of book matching.
    Returns None if the book, chapter, or verse can't be parsed at all
    (e.g. a vague reference like "verse 26" or "that chapter" has no book
    match and always returns None here).

    `ref` originates from the model's own text and is untrusted — capped
    at 80 chars before it ever reaches the regex below. No real verse
    reference or teacher name is anywhere close to that length, and the
    lazy `[A-Za-z ]+?` group immediately followed by `\s+` (both match a
    space) can backtrack in an O(n^2)-shaped way on adversarial input with
    letters/spaces and no colon.
    """
    ref = ref.strip()
    if len(ref) > 80:
        return None
    m = re.match(r'^(\d?\s*[A-Za-z ]+?)\s+(\d+):(\d+)(?:[-–—](\d+))?$', ref)
    if not m:
        return None

    book_raw = m.group(1).strip().lower()
    chapter = int(m.group(2))
    verse_start = int(m.group(3))
    verse_end = int(m.group(4)) if m.group(4) else None

    abbrev = resolve_book_abbrev(book_raw)
    if not abbrev:
        return None

    return abbrev, chapter, verse_start, verse_end


def _resolve_verse_row(db, abbrev: str, chapter: int, verse: int) -> bool:
    verse_id = f"{abbrev}.{chapter}.{verse}"
    result = db.table("verses").select("verse_id").eq("verse_id", verse_id).limit(1).execute()
    return bool(result.data)


def verify_verse_mention(db, raw: str) -> bool:
    """True only if the whole reference (single verse or full range)
    resolves to real rows. A range fails whole if either endpoint is bad —
    no partial credit.
    """
    parsed = _parse_verse_or_range(raw)
    if not parsed:
        return False
    abbrev, chapter, verse_start, verse_end = parsed

    if not _resolve_verse_row(db, abbrev, chapter, verse_start):
        return False
    if verse_end is not None:
        if not _resolve_verse_row(db, abbrev, chapter, verse_end):
            return False
    return True


def verify_teacher_mention(db, raw: str, grounding: "RetrievalGrounding") -> Optional[str]:
    """Returns the resolved source_id if this name passes every teacher
    guard, else None. Biblical-figure check runs first and short-circuits
    — a hit here means the alias table is never even consulted.

    `grounding` is REQUIRED (no default) so a caller cannot silently skip the
    Phase 2 retrieval-grounding gate — omitting it is a TypeError before any
    DB call, the same structural fail-closed discipline as Invariant 10's
    `store_propositions`. The grounding gate runs LAST, after the existing
    resolve + sentinel + license guards: a name that resolves to a real
    servable source is still denied a verified link unless that teacher's
    material was actually retrieved for this question (the A.W. Tozer
    verified-link-on-unretrieved-material symptom — Phase 0 §1(c)).
    """
    if is_biblical_figure(raw):
        return None

    key = normalize_alias_key(raw)
    if not key:
        return None

    alias_result = (
        db.table("source_aliases").select("source_id").eq("alias_key", key).limit(1).execute()
    )
    if not alias_result.data:
        return None

    source_id = alias_result.data[0]["source_id"]
    if source_id == _SENTINEL_SOURCE_ID:
        return None

    if not is_source_servable(db, source_id):
        return None

    # Phase 2 teacher-name guard: retrieval-grounded naming. A verified link
    # points at `source_id`, so it is granted only when THAT source was actually
    # retrieved — source-id arm only (see _link_source_retrieved for why the
    # author-name arm is excluded from the LINK decision). Runs after servable
    # so we never leak a name the license gate would have blocked anyway. Fails
    # closed via grounding.established.
    if not _link_source_retrieved(source_id, grounding):
        return None

    return source_id


# ── Phase 2 residual: prose-attribution scan (2026-08-02) ─────────────────────
# The declared-block guard above (verify_teacher_mention + chat.py's resolution
# loop) keys on the model's own <reference_mentions> self-report. A teacher
# CREDITED IN THE ANSWER PROSE but omitted from that block is invisible to it,
# and its false credit would stand (the disclosed residual, reviewer finding #3
# on ee3cff4/9e5fe94). This block closes that path for FULL PERSONAL NAMES ONLY
# (Alex's scope, 2026-08-02) via two arms that share ONE grounding notion
# (_is_retrieval_grounded — requirement 1) and fail CLOSED (requirement 3):
#
#   Arm 1 — corpus full-name scan: the answer prose is scanned for the finite,
#   precomputed set of corpus "first + last" teacher names (build_name_universe).
#   Position-agnostic, near-zero false-positive (only known corpus names match).
#   Catches the dangerous in_corpus_not_retrieved class credited in prose
#   (the A.W. Tozer verified-link-on-unretrieved-material symptom, Phase 0 §1c).
#
#   Arm 2 — attribution-context extraction: first + last names in explicit
#   attribution constructions ("According to X", "X taught", "X's commentary")
#   are extracted and grounding-checked. This is what catches OUT-OF-CORPUS
#   inventions and nested-quote re-attributions (Warren Wiersbe, Ray Stedman,
#   Douglas Wilson, Philip Jenkins, Ralph Martin, Vance Havner — none in the
#   corpus, so no allowlist could see them). Person-filtered against biblical
#   figures and divine/theological/organizational tokens to protect Alex's
#   req-9 zero-false-denial bar: a trigger-happy scan that regenerates/refuses
#   legitimate answers would wreck the product. (This is a tuning constraint on
#   THIS guard, not a claim that a blocked answer outranks a false credit —
#   CLAUDE.md's ranked failure modes correctly put misrepresenting a teacher
#   ABOVE a generic/blocked answer; the filters below exclude only genuine
#   non-persons, so no real credit is ever suppressed.)
#
# Bare surnames are DELIBERATELY out of scope: Arm 1's filter and Arm 2's pattern
# both require >= 2 capitalized name tokens. Phase 0 documented that short forms
# ("Prince" = Derek Prince) occur in ordinary prose and a surname scan would risk
# false denials. Do not extend to surnames without the sizing evidence.

_NAME_TOKEN_RE = re.compile(r"^[A-Z][A-Za-z.'’\-]*$")

# Organizational / media / title / article tokens. A display or extracted string
# containing any of these (case-insensitive, punctuation-stripped, length >= 2 so
# a single-letter initial "A"/"W" is never mistaken for the article "a") is a
# ministry, venue, publication, or connective phrase — NOT a personal
# "first + last" teacher name.
_ORG_TITLE_TOKENS = frozenset({
    "the", "an", "of", "for", "and", "with", "to", "at", "on", "by",
    "ministries", "ministry", "church", "churches", "fellowship", "mission", "missions",
    "magazine", "library", "commentary", "commentaries", "database", "tv", "telecasting",
    "network", "media", "podcast", "pdcst", "press", "publishing", "publications",
    "college", "university", "seminary", "seminaries", "institute", "foundation",
    "awakening", "equipping", "nations", "image", "crossroads", "heights", "school",
})

# Divine names and common theological/biblical nouns. Any extracted "first + last"
# candidate containing one of these tokens is a theological phrase, not a personal
# teacher name — the primary false-positive guard for Arm 2 (is_biblical_figure is
# EXACT-match and does NOT cover "Jesus Christ", "Holy Spirit", "New Testament",
# etc.). Token-level rather than whole-phrase so it is robust as new phrasings
# appear; extend as real usage surfaces a gap (same philosophy as biblical_figures).
_RELIGIOUS_NONPERSON_TOKENS = frozenset({
    "holy", "spirit", "ghost", "god", "jesus", "christ", "lord", "jehovah", "yahweh",
    "messiah", "trinity", "almighty", "testament", "scripture", "scriptures", "bible",
    "gospel", "gospels", "psalm", "psalms", "covenant", "kingdom", "sabbath", "passover",
    "pentecost", "heaven", "hell", "satan", "devil", "angel", "angels", "apostle",
    "apostles", "prophet", "prophets", "disciple", "disciples", "commandment",
    "commandments", "israel", "jerusalem", "zion", "calvary", "sinai", "savior",
    "saviour", "redeemer", "creator", "pharisees", "sadducees", "gentiles",
})

# Sentence-lead / function words. A capitalized sentence-initial "As", "Given",
# "Need", or a pronoun can be mis-grabbed as the FIRST token of a two-token name
# ("As Prince taught" -> "As Prince"). Disqualifying these as name tokens is the
# fix (found by the 2026-08-02 live smoke). Extend as real usage surfaces a gap.
_FUNCTION_WORDS = frozenset({
    "as", "according", "given", "need", "but", "so", "yet", "now", "then", "thus",
    "here", "there", "this", "that", "these", "those", "when", "while", "since",
    "because", "although", "however", "therefore", "moreover", "indeed", "also",
    "both", "either", "neither", "he", "she", "they", "we", "you", "it", "his",
    "her", "their", "our", "your", "its", "him", "them", "us", "who", "whom",
    "which", "what", "why", "how", "where", "some", "many", "most", "such", "like",
    "unlike", "before", "after", "during", "through", "within", "unless", "whereas",
})

_NON_PERSON_TOKENS = _ORG_TITLE_TOKENS | _RELIGIOUS_NONPERSON_TOKENS | _FUNCTION_WORDS

# Display strings that pass the token filter but are English phrases / anonymous-
# author sentinels, not personal teacher names. Kept tiny and explicit; err toward
# exclusion (fail-safe for req 9). "Unknown Christian" is the deliberately
# silent_context pen-name (Invariant 7) — never a citable credit anyway.
_NON_PERSONAL_ALIASES = frozenset({"Drawing Near", "Unknown Christian"})


def _looks_like_personal_full_name(display: Optional[str]) -> bool:
    """True iff `display` is a personal "first + last" (2–3 token) name: every
    token capitalized and name-shaped (initials "A.W." and hyphens
    "Austin-Sparks" allowed), none an organizational / theological / article
    word, and not on the explicit non-personal exclusion list. A single bare
    token (a surname or given name alone) never qualifies — FULL NAMES ONLY."""
    if not display:
        return False
    display = display.strip()
    if display in _NON_PERSONAL_ALIASES:
        return False
    tokens = display.split()
    if not (2 <= len(tokens) <= 3):
        return False
    for t in tokens:
        if not _NAME_TOKEN_RE.match(t):
            return False
        stripped = t.strip(".'’-").lower()
        if len(stripped) >= 2 and stripped in _NON_PERSON_TOKENS:
            return False
    return True


def build_name_universe(db) -> frozenset:
    """The finite set of proper-case personal "first + last" teacher names known
    to the corpus — what Arm 1 of the prose scan searches for. Assembled from
    every source's canonical `name` and every non-blank `alias_display`, filtered
    to personal full names (`_looks_like_personal_full_name`). Bare-surname
    aliases ("Bosworth", "Muller") are excluded by that filter, matching the
    FULL-NAMES-ONLY scope. Building from `sources.name` too (not aliases alone)
    keeps a teacher whose alias_display is blank — Michael Brown, Jack Deere —
    in the universe.

    Does NOT swallow query errors: it raises, so the caller's guard (which wraps
    this in the same try/except that refuses on failure) fails CLOSED. Returning
    an empty universe instead would fail OPEN (silently scan for nothing) — the
    exact posture build_retrieval_grounding avoids."""
    names = set()  # type: set
    for row in (db.table("sources").select("name").execute().data or []):
        nm = (row.get("name") or "").strip()
        if _looks_like_personal_full_name(nm):
            names.add(nm)
    for row in (db.table("source_aliases").select("alias_display").execute().data or []):
        disp = (row.get("alias_display") or "").strip()
        if _looks_like_personal_full_name(disp):
            names.add(disp)
    return frozenset(names)


def resolve_alias_source_id(db, name: str) -> Optional[str]:
    """Resolve a name to its source_id via the SHARED alias path (normalize +
    source_aliases lookup; the sentinel counts as unresolved). Returns None when
    unresolved or on a lookup error — leaning toward "ungrounded", the fail-safe
    direction for the prose guard, and correct regardless because
    _is_retrieval_grounded still applies its author-name arm to a None sid (so a
    retrieved teacher with no alias row is grounded, never false-flagged). This
    is the one resolution both the declared-block guard and the prose scan use —
    a single notion of name->source_id, never a fork (requirement 1)."""
    key = normalize_alias_key(name)
    if not key:
        return None
    try:
        r = db.table("source_aliases").select("source_id").eq("alias_key", key).limit(1).execute()
    except Exception:
        return None
    if r.data and r.data[0].get("source_id") != _SENTINEL_SOURCE_ID:
        return r.data[0]["source_id"]
    return None


def _prose_name_present(answer_text: str, name: str) -> bool:
    """Literal, case-sensitive presence of `name` in prose, word-bounded so a
    name is never matched inside a larger word (the study-reference.ts free-prose
    substring class). Reuses find_occurrences — the same presence mechanism the
    declared guards use — then rejects a match whose immediately adjacent
    character is a letter. A trailing apostrophe (possessive "Derek Prince's") or
    period is a valid mention and passes."""
    for idx in find_occurrences(answer_text, name):
        before = answer_text[idx - 1] if idx > 0 else ""
        after = answer_text[idx + len(name)] if idx + len(name) < len(answer_text) else ""
        if not (before.isalpha() or after.isalpha()):
            return True
    return False


# Arm 2 — attribution-context extraction. A "first + last" name (2–3 tokens)
# appearing in an explicit attribution construction. The attribution anchor is
# the false-positive control: an incidental capitalized phrase rarely sits inside
# "According to __" or "__ taught".
#
# The token grammar is deliberately STRICT (hardened 2026-08-02 after the live
# smoke found four false-positive classes: a trailing possessive "'s" captured
# into the name -> "Derek Prince's" failed to resolve; tokens joined across a
# line/heading break -> "Battlefield\n\nAccording"; a sentence-boundary span ->
# "Prince. He"; and a leading function word -> "As Prince"). A token is a
# capitalized WORD (internal capitals "MacArthur" and a trailing hyphenated part
# "Austin-Sparks" allowed, but NO trailing apostrophe or period) or an INITIAL
# run ("A.", "A.W.", "E.M."). Tokens join on HORIZONTAL whitespace only, so a
# name never spans a newline. Extend the verb/noun sets as real usage surfaces
# gaps (same posture as biblical_figures).
_H = r"[^\S\r\n]+"  # one-or-more horizontal whitespace, never a line break
_ATTR_WORD = r"[A-Z][a-z]+(?:[A-Z][a-z]+)*(?:-[A-Za-z]+)*"
_ATTR_INITIAL = r"[A-Z](?:\.[A-Z])*\.?"
_ATTR_TOKEN = r"(?:" + _ATTR_WORD + r"|" + _ATTR_INITIAL + r")"
_ATTR_NAME = _ATTR_TOKEN + r"(?:" + _H + _ATTR_TOKEN + r"){1,2}"
_ATTR_VERB = (
    r"(?:teaches|taught|writes|wrote|argues|argued|notes|noted|reminds|reminded|"
    r"says|said|observes|observed|explains|explained|describes|described|"
    r"emphasizes|emphasized|emphasises|emphasised|warns|warned|maintains|maintained|"
    r"insists|insisted|declares|declared|comments|commented|suggests|suggested|"
    r"contends|contended|holds|held|calls|called|"
    # Speech/teaching verbs a person-subject attribution reaches for (added
    # 2026-08-02, reviewer finding #2 — an out-of-corpus invention credited with
    # any of these would otherwise slip Arm 2; the name filter still gates, so a
    # theological subject like "the Bible reasons" is dropped, not flagged):
    r"preaches|preached|believes|believed|affirms|affirmed|states|stated|claims|"
    r"claimed|asserts|asserted|proclaims|proclaimed|urges|urged|exhorts|exhorted|"
    r"stresses|stressed|concludes|concluded|reasons|reasoned|speaks|spoke|"
    r"points" + _H + r"out|pointed" + _H + r"out|puts" + _H + r"it)"
)
_ATTR_NOUN = (
    r"(?:commentary|teaching|teachings|book|sermon|point|view|words|writing|writings|"
    r"exposition|study|message|ministry|observation|insight|position|argument|work)"
)
_ATTRIBUTION_RE = re.compile(
    r"(?:According" + _H + r"to|As|as)" + _H + r"(" + _ATTR_NAME + r")"   # preposition-led
    r"|(" + _ATTR_NAME + r")(?:['’]s)?" + _H + _ATTR_VERB + r"\b"          # verb / possessive-verb led
    r"|(" + _ATTR_NAME + r")['’]s" + _H + _ATTR_NOUN + r"\b"               # possessive + teaching-noun
)


def _extract_prose_attribution_names(answer_text: str) -> set:
    """Personal "first + last" names credited in explicit attribution context.
    A trailing possessive is stripped, then each candidate is filtered through
    `_looks_like_personal_full_name`, so divine/theological phrases ("Jesus
    Christ", "Holy Spirit", "New Testament"), organizational names, and
    sentence-lead function words ("As Prince") are all dropped before the
    grounding check."""
    names = set()  # type: set
    for m in _ATTRIBUTION_RE.finditer(answer_text):
        nm = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        nm = re.sub(r"['’]s?$", "", nm).strip()  # belt-and-suspenders possessive strip
        if nm and _looks_like_personal_full_name(nm):
            names.add(nm)
    return names


def ungrounded_prose_teachers(answer_text: str, name_universe: frozenset, grounding, db) -> List[str]:
    """Full personal teacher names credited in the ANSWER PROSE whose material was
    not retrieved for this question — the Phase 2 residual. EXTENDS the
    declared-block guard's coverage (it does not replace it): this scan is
    independent of the <reference_mentions> block, so it catches a prose credit
    the model never self-reported.

    Union of Arm 1 (corpus full-name variants present anywhere in prose) and Arm 2
    (attribution-context extraction, for out-of-corpus names). Grounding is
    decided by the SHARED _is_retrieval_grounded predicate keyed on retrieved
    IDENTITY (requirement 2: the Andrew-Murray alias-gap is grounded via the
    author-name arm and never false-flagged). Fails CLOSED through
    grounding.established (unavailable grounding -> every present name ungrounded
    -> caller refuses)."""
    candidates = set()  # type: set
    for name in name_universe:                       # Arm 1
        if _prose_name_present(answer_text, name):
            candidates.add(name)
    for name in _extract_prose_attribution_names(answer_text):  # Arm 2
        candidates.add(name)

    out = []  # type: List[str]
    for name in candidates:
        if is_biblical_figure(name):
            continue
        sid = resolve_alias_source_id(db, name)
        if not _is_retrieval_grounded(name, sid, grounding):
            out.append(name)
    return sorted(set(out))


def _deduplicate_overlapping_spans(verified: List[Dict]) -> List[Dict]:
    """When two DIFFERENT verified references occupy overlapping character
    spans in answer_text, keep the longer span and drop the shorter's
    overlapping occurrence. Generic over cause — a verse range vs. its own
    start verse (e.g. "Romans 8:26-28" vs "Romans 8:26" both at position 0)
    is the case this was built for, but the same rule also covers a shorter
    reference nested inside an unrelated longer one (e.g. "John 3:16" as a
    literal substring of "1 John 3:16"), and applies identically to teacher
    mentions since they share the same presence-check mechanism.

    Never compares an entry's own repeated occurrences against each other —
    only overlaps ACROSS different entries are redundant; the same
    reference legitimately mentioned twice in different places (SP1's
    anchor-every-occurrence design) must survive untouched.

    Fail-quiet: an exact-length tie between two overlapping spans from
    different entries is ambiguous (nothing here can judge which one the
    model meant) — both are dropped rather than guessed.

    A verse entry that loses all its positions to this pass is dropped
    entirely; one that keeps a subset keeps only the survivors. Same for a
    teacher entry's single position.
    """
    occurrences = []  # each: (entry_idx, pos, start, end, raw_len)
    for entry_idx, entry in enumerate(verified):
        raw_len = len(entry["raw"])
        positions = entry["positions"] if entry["type"] == "verse" else [entry["position"]]
        for pos in positions:
            occurrences.append((entry_idx, pos, pos, pos + raw_len, raw_len))

    dropped = set()  # {(entry_idx, pos), ...}
    for i in range(len(occurrences)):
        i_entry, i_pos, i_start, i_end, i_len = occurrences[i]
        for j in range(i + 1, len(occurrences)):
            j_entry, j_pos, j_start, j_end, j_len = occurrences[j]
            if i_entry == j_entry:
                continue  # same reference's own repeats never conflict with themselves
            if i_start < j_end and j_start < i_end:  # spans overlap
                if i_len > j_len:
                    dropped.add((j_entry, j_pos))
                elif j_len > i_len:
                    dropped.add((i_entry, i_pos))
                else:
                    dropped.add((i_entry, i_pos))
                    dropped.add((j_entry, j_pos))

    result = []
    for entry_idx, entry in enumerate(verified):
        if entry["type"] == "verse":
            surviving = [p for p in entry["positions"] if (entry_idx, p) not in dropped]
            if surviving:
                result.append({**entry, "positions": surviving})
        else:
            if (entry_idx, entry["position"]) not in dropped:
                result.append(entry)
    return result


def verify_references(
    answer_text: str, raw_output: str, db, retrieved_grounding: "RetrievalGrounding"
) -> List[Dict]:
    """Top-level entry point. Never raises — any unexpected failure
    anywhere in this function results in an empty list, never a broken
    request. Returns a list of verified references, each:
        {"type": "verse", "raw": str, "positions": [int, ...]}
        {"type": "teacher", "raw": str, "position": int, "source_id": str}

    `retrieved_grounding` is REQUIRED — it carries which teachers were
    actually retrieved for this question (Phase 2 teacher-name guard). Build
    it with `build_retrieval_grounding(chunks, db)`; a caller with no
    retrieval context that passes `RetrievalGrounding(established=False)`
    (or any grounding whose sets are empty) gets zero teacher links, which
    is the fail-closed default. Verse verification is unaffected — Scripture
    is permitted from the model's own knowledge and does not depend on
    retrieval.
    """
    try:
        proposals = parse_reference_mentions(raw_output)
        verified = []  # type: List[Dict]

        for proposal in proposals:
            # Scoped to this one proposal: an exception here (e.g. a
            # transient DB error) drops only this mention. Mentions already
            # appended to `verified` earlier in the loop are unaffected —
            # a single bad proposal must never wipe out the whole batch.
            try:
                raw = proposal["raw"]
                positions = find_occurrences(answer_text, raw)
                if not positions:
                    continue  # presence check failed — model reported something not actually there

                if proposal["type"] == "verse":
                    if not verify_verse_mention(db, raw):
                        continue
                    verified.append({"type": "verse", "raw": raw, "positions": positions})
                else:
                    source_id = verify_teacher_mention(db, raw, retrieved_grounding)
                    if not source_id:
                        continue
                    verified.append({
                        "type": "teacher",
                        "raw": raw,
                        "position": positions[0],
                        "source_id": source_id,
                    })
            except Exception:
                logger.exception("Reference verification failed for one proposal — dropping it")
                continue

        return _deduplicate_overlapping_spans(verified)
    except Exception:
        # Outer safety net: catastrophic failures outside any single
        # proposal's verification (e.g. parse_reference_mentions itself
        # throwing) still result in an empty list, never a broken request.
        logger.exception("Reference verification failed — returning no pointers")
        return []
