#!/usr/bin/env python3
"""
closeness_check.py — Phase 1 paraphrase-wording closeness metric (PLAN.md #45).

NOT WIRED INTO ANY INGEST PATH. Nothing in the repo imports this module as of
this commit. It exists to be reviewed and unit-tested before the (separate,
later) step that wires it into the ingest path, and before the (separate,
later) step that runs it corpus-scale to derive real floor/cutoff values.

--------------------------------------------------------------------------
Why this exists
--------------------------------------------------------------------------
A proposition has no retrievable per-statement source span. store_propositions()
(scripts/propositions.py) inserts only (id, document_id, content, embedding,
proposition_index, prompt_version, prompt_fingerprint, model) — no chunk_id,
no offsets. process_document() feeds the extractor the ENTIRE document text.
So "the source passage a proposition claims to paraphrase" is, in practice,
the full source text of its document — reconstructed as that document's
chunks.content concatenated in chunk_index order (verified live against
production; chunks.content is verbatim source text and exists for every
document; chunks.rewritten_content, when present, is a separate copyright
paraphrase field that never overwrites chunks.content — see
scripts/rewrite_sermons.py — so chunks.content stays verbatim regardless of
rewrite status). Because we can't know which span of that document a given
proposition actually paraphrases, this metric is deliberately
POSITION-INDEPENDENT: a containment/matching-blocks measure over trigram
SETS, never a whole-string diff ratio, and never assumes alignment.

--------------------------------------------------------------------------
Primary metric — word-level trigram containment
--------------------------------------------------------------------------
For paraphrase text P and source document text S (both run through the
exemption pipeline below first):

    containment = |trigrams(P) ∩ trigrams(S)| / |trigrams(P)|

trigrams = contiguous 3-token windows over the residual word stream, as SETS
(each distinct trigram counted once, not as a multiset). Normalized by the
PARAPHRASE's own trigram count, not the source's — this measures "what
fraction of the paraphrase's own wording is lifted verbatim," the correct
asymmetric direction for a quote gate, and stays well-behaved against large
source documents (a long source doesn't shrink the denominator).

n=3 was chosen to mirror the extraction prompt's own rule, quoted verbatim
from scripts/propositions.py's EXTRACTION_PROMPT (the v3 prompt,
DEFAULT_PROMPT_VERSION — EXTRACTION_PROMPT_V4 carries the same rule in
near-identical wording):

    "Never reproduce three or more consecutive words from the source
    (quoted scripture excepted — scripture wording may stand)."

i.e. the model's own instruction defines the violation as a run of 3+
copied words. A trigram-containment metric with n=3 measures exactly that
threshold, not an arbitrary window size.

--------------------------------------------------------------------------
Secondary signal — longest contiguous verbatim run, in words
--------------------------------------------------------------------------
difflib.SequenceMatcher over residual WORD token sequences (never character
sequences). See longest_common_run(). Trigram containment stays the
PRIMARY/first-checked signal (per prior direction); as of Phase 4 (PLAN.md
#45), this run-length signal is a SECOND, INDEPENDENT trip condition in
classify()'s verdict — not a replacement, and not merely informational
anymore. It exists because containment alone provably misses a real
adversarial class: a short (~12-14 word) verbatim splice grafted onto an
otherwise-genuinely-reworded paraphrase barely moves trigram containment
(confirmed corpus-scale, Step 2 re-run: 5/5 R-run adversarial items stayed
at containment 0.20-0.29, comfortably under CONTAINMENT_FLOOR, even after
splicing) while longest_common_run jumps from a clean pair's 2-3 words to
12-13 — exactly the kind of miss a single scalar threshold on a set-based
metric (trigram containment doesn't care WHERE matches fall, only how
many) cannot catch by construction. See classify()'s verdict logic and
LONGEST_RUN_WORD_THRESHOLD below for the OR-wiring and its derivation.
To keep this signal honest, exempt spans are masked with PER-OCCURRENCE-
UNIQUE sentinel tokens here (as opposed to the primary metric's per-
CATEGORY sentinel, see below) so two different scripture references, or
two different teacher names, can never be judged "the same run" by
SequenceMatcher purely because they were both masked to the same
placeholder.

--------------------------------------------------------------------------
Exemption pipeline (applied identically to P and S, in this order)
--------------------------------------------------------------------------
1. Scripture references, via a free-text scanner (no free-text scanner
   existed before this file — confirmed by grep of reference_verifier.py
   and constants.py; the existing _parse_verse_or_range() only accepts
   pre-isolated "Book Chap:Verse[-Verse]" strings anchored with ^...$, it
   cannot scan running text). This module's scanner:
     - builds a regex alternation directly from BOOK_MAP's own keys
       (imported, never forked, never re-derived) to locate candidate
       "<book-form> <chapter>:<verse>(-<verse>)?" spans in running text;
     - then re-validates and parses every candidate through
       app.services.reference_verifier._parse_verse_or_range() itself
       (imported, not reimplemented) to get the canonical parse and to
       reject any span that only superficially matched the alternation
       shape. A candidate that fails re-validation is left unmasked rather
       than guessed at.
     - the CITATION ITSELF ("Romans 8:28") is always masked, exactly as
       before. Separately, IF a verse_lookup dict is supplied (built once
       via build_verse_lookup(), a live SELECT of the whole `verses` table
       — see reference_verifier._resolve_verse_row for the same verse_id
       key format reused here), the QUOTED VERSE WORDING that sits near a
       validated citation is masked too — this is the 2026-07-26 fix. See
       "Scripture-wording exemption fix" below for the full design; without
       it a fully rule-compliant scripture quote (the extraction prompt
       explicitly permits scripture wording "may stand") inflated
       containment as if it were copied teacher wording, because only the
       citation string was ever masked, never the verse text that followed
       it.

--------------------------------------------------------------------------
Scripture-wording exemption fix (2026-07-26, PLAN.md #45 Phase 4)
--------------------------------------------------------------------------
Ground truth: the live `verses` table (verse_id -> text), the same table
reference_verifier._resolve_verse_row queries for existence. Confirmed live
on this table before designing the fix: 31,098/31,098 rows carry
translation='WEB' — ONLY the World English Bible is stored. No KJV, NIV,
NASB, ESV, etc. rows exist. Teachers in this corpus (Ravenhill in
particular, an older-generation KJV-era preacher) can plausibly quote any
of those other translations, whose wording differs from WEB's — sometimes
substantially (e.g. Psalm 23:1 KJV "The LORD is my shepherd; I shall not
want" vs. WEB "Yahweh is my shepherd: I shall lack nothing" — under half
the words match). An exact/substring match against the stored WEB text
alone would therefore under-mask most real scripture quotes in this corpus.
The fix is deliberately a NORMALIZED, ORDER-PRESERVING FUZZY MATCH:

  1. For every citation that survives _parse_verse_or_range re-validation,
     look up the referenced verse's (or, for a range, every verse's,
     concatenated) actual WEB text from verse_lookup. A missing endpoint
     (citation is syntactically valid but doesn't resolve to a real row —
     e.g. a bad chapter number) means no ground truth exists; the citation
     itself still gets masked as before, but no quote-wording search runs.
  2. Search a BOUNDED, CITATION-ANCHORED window of raw text on each side of
     the citation (600 chars ≈ 80-120 words before, and separately after —
     quotes appear on either side of their citation in real sermon prose,
     e.g. "Romans 8:28 says..." vs. "...as Romans 8:28 tells us"). This
     window is the ONLY over-exemption guard's first layer: nothing outside
     it is ever considered, so a coincidentally verse-like turn of phrase
     elsewhere in a long document, with no citation anywhere nearby, is
     never a candidate for masking.
  3. Within that window, run difflib.SequenceMatcher (word tokens, ORDER-
     preserving LCS-style matching blocks — not a bag-of-words/Jaccard
     count) between the window's tokens and the verse's own tokens. This is
     the second guard layer: scattered coincidental word overlap in the
     wrong order does not count, only a run of the verse's OWN words in
     something resembling the verse's own sequence does — which is what a
     real quote (even reworded by translation) produces, and generic
     teacher commentary that merely shares a few common words with a verse
     does not.
  4. ANCHOR + GAP-TOLERANT EXTEND + SPAN-DENSITY (revised TWICE same day,
     both revisions triggered by hand-verification catching real failures
     against live corpus text, not hypothetical — see _find_quote_span's
     own docstring for the full before/after of both). The anchor is the
     SINGLE LONGEST matching block; it alone must clear
     VERSE_QUOTE_ANCHOR_MIN_WORDS (>=4 words) — this guard layer exists so
     a 1-2 word verse (e.g. John 11:35 "Jesus wept.") cannot trip on
     coincidence, and so a scatter of short common-word matches (a lone
     "in", "a", "the" aligned by chance) can never substitute for one real
     contiguous run. The span then extends outward from the anchor,
     absorbing adjacent matching blocks only while BOTH: the gap to the
     next block is <= VERSE_QUOTE_GAP_TOLERANCE window-tokens (bridges real
     translation variance inside a quote, e.g. KJV "only begotten Son" vs
     WEB "one and only Son"), AND that block is itself >=
     VERSE_QUOTE_MIN_EXTEND_BLOCK_WORDS (>=2 words — added in the SECOND
     same-day revision, after the first, gap-only version was itself caught
     live still missing a real quote: a chain of isolated single-word
     coincidental matches on common words, within gap tolerance but well
     before the real anchor, diluted density below the floor for an
     otherwise clean quote). Finally, density = matched-words / span-
     length-in-window-tokens must clear VERSE_QUOTE_DENSITY_FLOOR (0.7) —
     this measures "how much of THIS candidate span is verse wording," not
     "how much of the WHOLE verse is here." The ORIGINAL (first) version of
     this fix used the latter (matched / len(whole verse)) and was WRONG:
     it silently failed on any quote of only PART of a longer verse,
     because a real, cleanly-matching partial quote can still be well under
     55% of the full verse's word count. Confirmed live across both
     revisions: John 3:16 (full KJV quote, caught by every version, density
     0.87 in the final version); 2 Peter 1:19 (quoting only the verse's
     second clause — MISSED by the original recall-based version at 35% of
     full-verse length; STILL MISSED by the first density version, density
     diluted to 0.62 by distant common-word singletons; CAUGHT by the final
     version, density 1.0); Hebrews 11:25 (a reordered clause, "with the
     people of God" vs. WEB's "with God's people" — MISSED by the first
     density version at 0.6875, just under the 0.70 floor; CAUGHT by the
     final version, density 1.0); an unrelated-commentary negative control,
     a short-verse-coincidence negative control (John 11:35), a copied-
     teacher-wording-near-unrelated-citation negative control, and two
     independently confirmed translation-mismatch negatives (Isaiah 10:27,
     Proverbs 4:23 NIV-vs-WEB) all correctly return no match under every
     version.
  5. If masked, the span masked is the TIGHT bounding range produced by
     step 4 — not the whole window, and never text outside the window.

  Known, disclosed limitations (not a claim of full coverage) — THREE,
  confirmed live during Step 2's re-run, not merely hypothesized (a fourth,
  word-reordering fragmentation, was found live but then CLOSED by the
  second same-day revision above rather than left open):
    a) Translation mismatch: a verse whose non-WEB translation diverges
       heavily enough from WEB's wording that even the anchor block can't
       reach VERSE_QUOTE_ANCHOR_MIN_WORDS (confirmed live: Isaiah 10:27
       quoted as "the yoke of oppression will be lifted from Judah" vs.
       WEB's completely different "...the yoke shall be destroyed because
       of the anointing oil"; Proverbs 4:23 quoted in NIV wording vs. WEB's
       "Keep your heart with all diligence...") will not be caught and
       still inflates containment as an unmasked "false" match. Real,
       bounded gap inherent to only WEB text being available as ground
       truth.
    b) No citation anchor: this fix only searches near a citation that
       matches the free-text scanner's "<book> <chapter>:<verse>" shape.
       Scripture quoted without ANY nearby chapter:verse citation
       (confirmed live: "as Jesus said, we don't live by bread alone, but
       by every word that proceeds from the mouth of God" — Matthew 4:4 /
       Deuteronomy 8:3, quoted with no citation string anywhere nearby), or
       cited by book+chapter only with no verse number (confirmed live:
       "as seen in Hebrews 11, which says that faith is the substance of
       things hoped for" — no ":verse" for the regex to match), has no
       anchor point to search a window from at all, and is never a
       candidate for masking.
    c) Range citations spanning many verses: _verse_range_text requires
       EVERY verse in the cited range to resolve, and concatenates the
       full range's text as the match target — a real quote of a short
       excerpt from a large cited range could, in principle, fall under
       the density floor the same way a partial single-verse quote almost
       did before the step-4 fix; not independently confirmed against a
       live case this run (no should-pass item sampled cited a wide range),
       flagged as a plausible residual gap rather than a confirmed one.

  Symmetric residual risk, stated rather than hand-waved: could a genuine
  COPIED-TEACHER quote (not scripture) sitting near an unrelated citation
  ever get wrongly masked as a "verse quote"? Only if that teacher wording
  itself happens to reproduce a single contiguous run of >=4 of a SPECIFIC
  real verse's own words, at >=70% span density — teacher commentary
  register is nothing like compact translated-verse prose, so this is very
  unlikely, and even in the freak case the span masked is still only the
  tightly-bounded matched extent, never more.
2. Proper names — teacher name tokens masked from a LIVE SELECT of
   sources.name + source_aliases.alias_display (see build_name_set()).
   Deduplication of near-identical raw strings uses
   app.services.source_resolver.normalize_alias_key — imported, never
   forked (Invariant 6).
3. Fixed theological vocabulary — a small explicit in-code stoplist
   (THEOLOGY_TERMS below, 38 terms/phrases). For a trigram metric a single
   shared theological word rarely produces a spurious matching trigram
   unless the surrounding words also match (in which case it's real copied
   phrasing) — so this stoplist is a minor correction, not load-bearing.
3b. Common religious vocabulary (PLAN.md #45 Phase 6, 2026-07-28) — a
   corpus-derived list of 1,210 cross-teacher stock phrases (6-13 words
   each; see scripts/data/common_religious_vocab.json for full derivation
   provenance), fuzzy/span-matched via build_vocab_matcher() +
   VocabMatcher, OPTIONAL and OFF by default (vocab_matcher=None
   everywhere). Reuses _find_quote_span's own anchor + gap-tolerant-extend
   + span-density-floor algorithm and constants verbatim (via the shared
   _anchor_extend_density_span helper) rather than a second, independently
   tuned matcher. MASKING ORDER matters here specifically: this pass runs
   BEFORE the theology/name word-level masking passes below, not after —
   see exempt_for_containment()'s own docstring for the fragmentation risk
   this order avoids (a theology-masked "god" can no longer match as part
   of a vocab phrase's own anchor wording).
4. Masking mechanism: every exempt span is replaced with a sentinel token
   that (a) cannot itself contribute a match — for the primary metric, any
   trigram containing ANY sentinel token is dropped from BOTH sets before
   intersection, never compared; and (b) cannot create a false adjacency
   match — the whole matched span (e.g. all of "Romans 8:28", all of
   "Leonard Ravenhill") collapses to ONE sentinel token, not one per
   original word, so it can't manufacture extra 3-token windows out of a
   name or reference that happens to be exactly 3 words long.
5. Residual token count (non-sentinel tokens remaining in the paraphrase)
   falls out of this pipeline for free and feeds the too-little check.

--------------------------------------------------------------------------
Three-verdict output contract — this module classifies, it does not act
--------------------------------------------------------------------------
  PASS             containment below CONTAINMENT_FLOOR AND longest_run
                   below LONGEST_RUN_WORD_THRESHOLD AND residual token
                   count at/above RESIDUAL_TOO_LITTLE_CUTOFF.
  QUOTE_CANDIDATE  containment at/above CONTAINMENT_FLOOR OR longest_run
                   at/above LONGEST_RUN_WORD_THRESHOLD (Phase 4, PLAN.md
                   #45 — two independent trip conditions, OR'd; see
                   classify()'s own comment for why an OR, not an AND, is
                   what the R-run adversarial evidence calls for). This
                   module does not build the verified-quotes routing
                   destination.
  HOLD_TOO_LITTLE  residual token count below RESIDUAL_TOO_LITTLE_CUTOFF.
                   Checked FIRST, unconditionally — a too-short residual
                   makes containment statistically unreliable (a single
                   fluky trigram can swing it to 0 or 1), so this verdict
                   pre-empts QUOTE_CANDIDATE too, not only PASS. Never
                   auto-passes (PLAN.md #45's exemption companion rule).

CONTAINMENT_FLOOR, RESIDUAL_TOO_LITTLE_CUTOFF, and LONGEST_RUN_WORD_
THRESHOLD are FINALIZED (Phase 4) from validate_closeness_check.py's
corrected-exemption corpus-scale re-run — see that script's output and
this module's own top-of-file constant comments for the derivation of
each. "Finalized for this build" and "PRE-CALIBRATION PROVISIONAL per
PLAN.md #46" hold at the same time: grounded in real numbers, not yet
reviewed by a human, so not the last word.

--------------------------------------------------------------------------
Constraints honored
--------------------------------------------------------------------------
stdlib only (difflib, re, unicodedata) — no new dependency. Python 3.9
syntax throughout (Optional[str], never str | None — Invariant 1; this
module will eventually be imported by the ingest path). No module-level
client construction or env-var reads — callers pass their own db_params
(psycopg2 DSN dict), matching the existing convention in
scripts/source_resolver.py and scripts/shared_ingest.py.
"""

import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Set, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent / "backend"
for _p in (str(_THIS_DIR), str(_BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.constants import BOOK_MAP  # noqa: E402
from app.services.reference_verifier import _parse_verse_or_range  # noqa: E402
# _parse_verse_or_range is name-prefixed private in its home module; imported
# anyway per explicit direction to reuse it rather than reforking book/verse
# parsing logic for the free-text scanner below.
from source_resolver import normalize_alias_key  # noqa: E402


# ── Decision constants -- FINALIZED (Phase 4, PLAN.md #45) from the
#    corrected-exemption corpus-scale re-run (validate_closeness_check.py,
#    65 should-pass pairs + 15 R0/R1/R2 rungs + 5 R-run items, SEED
#    20260726). "Finalized for this build" and "PRE-CALIBRATION PROVISIONAL
#    per PLAN.md #46" are BOTH true at once, not a contradiction: finalized
#    means every value below is grounded in real corpus numbers, not a
#    guess; provisional means no human review of the resulting
#    classifications has happened yet, so none of this is the last word. ──

CONTAINMENT_FLOOR = 0.40             # FINALIZED (Phase 4) / PRE-CALIBRATION PROVISIONAL
# Derivation: at floor=0.40, should-flag R0 (verbatim, n=15) and R1 (~15%
# word-edit splice, n=15) are BOTH caught 15/15 (R1's own minimum this run
# was 0.412, comfortably above 0.40). Should-pass trip rate at this floor
# is 6/65 (9.2%) -- every one of those 6 was hand-read against its full
# source text and confirmed a GENUINE near-verbatim reproduction of real
# source wording (teacher's own recurring definitional lines, a verbatim
# third-party quote embedded in the source, etc.), not a coincidental false
# positive -- zero false positives observed in the hand-reviewed high-end
# sample (16 items, containment >=0.30) at this or any floor tested.
# R2 (~35% word-edit splice) is NOT reliably caught by containment at any
# reasonable floor (median 0.012) -- expected and accepted: at that edit
# rate trigram containment cannot distinguish the splice from a genuine
# paraphrase by construction; not this signal's job.

RESIDUAL_TOO_LITTLE_CUTOFF = 8       # FINALIZED (Phase 4) / PRE-CALIBRATION PROVISIONAL, in residual tokens
# Re-grounded against the finalized floor (was a free-standing guess
# before): a residual of R tokens yields k = R-2 trigrams (contiguous
# 3-token windows). A single COINCIDENTAL matching trigram then gives
# containment = 1/k. At R=8, k=6, so one coincidental match = 1/6 = 0.167 --
# comfortably under CONTAINMENT_FLOOR (0.40), not a bare-minimum fit: it
# would take 3 of the residual's 6 trigrams (half) coincidentally matching
# to cross 0.40 at all, a low-probability event for genuinely unrelated
# text. (For contrast, the bare-minimum value where even ONE coincidental
# match still stays under 0.40 is R=5, k=3, 1/3=0.333 -- technically
# sufficient but with almost no safety margin; R=8 was kept for the wider
# margin, not moved down to the bare minimum.)

LONGEST_RUN_WORD_THRESHOLD = 9       # FINALIZED (Phase 4) / PRE-CALIBRATION PROVISIONAL, in words
# Derivation: R-run adversarial splices (5/5, this run) measured
# longest_run 12-13 words after splicing (vs. 2-3 words for the same items'
# genuine pre-splice content). Should-pass items NOT already caught by
# CONTAINMENT_FLOOR span longest_run up to 16 -- but every should-pass item
# with longest_run >=9 in that below-floor set was hand-confirmed as
# already-flaggable content in its own right (an uncaught scripture
# confound, or a genuine near-quote of source wording), not a clean
# coincidental paraphrase -- so 9 introduces no new false positive in the
# hand-reviewed sample while sitting with a full 3+ word margin below the
# R-run splice floor (12) and a 6+ word margin above the undisputed-clean
# ceiling (R-run's own pre-splice baseline, max 3 words).

# ── Scripture-wording exemption fix constants (2026-07-26, revised same day
#    after a partial-verse-quote miss was caught by hand-verification -- see
#    module docstring "Scripture-wording exemption fix" and _find_quote_span
#    for the full derivation and the live cases that grounded each value) ──

VERSE_QUOTE_WINDOW_CHARS = 600         # searched on EACH side of a validated citation
VERSE_QUOTE_ANCHOR_MIN_WORDS = 4       # the single longest matching block must clear
                                        # this alone -- guards short verses (e.g.
                                        # "Jesus wept.") against coincidental trip
VERSE_QUOTE_GAP_TOLERANCE = 3          # max non-matching window tokens bridged when
                                        # extending outward from the anchor block
VERSE_QUOTE_MIN_EXTEND_BLOCK_WORDS = 2 # a block being merged INTO the anchor's span
                                        # during extension must itself be >=2 words --
                                        # added same day as a second fix, after the
                                        # first density-floor version was caught still
                                        # missing a real quote live: isolated common-
                                        # word singletons ("a", "in", "that") sitting
                                        # within gap tolerance but far from the anchor
                                        # were diluting density below the floor even
                                        # for a clean, tight, obviously-real quote.
                                        # Confirmed live this fixed it without
                                        # reopening any negative control (see
                                        # _find_quote_span's docstring).
VERSE_QUOTE_DENSITY_FLOOR = 0.7        # matched words / span length, within the final
                                        # (anchor-extended) span -- NOT matched/whole-
                                        # verse-length (that recall-style measure was
                                        # the original, wrong version; see
                                        # _find_quote_span's docstring)

PASS = "PASS"
QUOTE_CANDIDATE = "QUOTE_CANDIDATE"
HOLD_TOO_LITTLE = "HOLD_TOO_LITTLE"

# ── Sentinel tokens (must tokenize as a single lowercase-letters run) ─────────

SENTINEL_SCRIPTURE = "zzzexemptscripturezzz"
SENTINEL_NAME = "zzzexemptnamezzz"
SENTINEL_THEOLOGY = "zzzexempttheologyzzz"
SENTINEL_VOCAB = "zzzexemptvocabzzz"
_SENTINELS = {SENTINEL_SCRIPTURE, SENTINEL_NAME, SENTINEL_THEOLOGY, SENTINEL_VOCAB}

# ── Fixed theological vocabulary stoplist (38 terms/phrases) ──────────────────
# Small and explicit by design (see module docstring #3). Latitude on exact
# list; kept deliberately short.

THEOLOGY_TERMS = [
    "Holy Spirit", "Holy Ghost", "Jesus Christ", "Kingdom of God", "Word of God",
    "God", "Jesus", "Christ", "Lord", "Gospel", "Grace", "Faith", "Sin",
    "Salvation", "Cross", "Scripture", "Scriptures", "Church", "Heaven",
    "Prayer", "Worship", "Repentance", "Baptism", "Anointing", "Glory",
    "Truth", "Mercy", "Bible", "Amen", "Disciple", "Apostle", "Prophet",
    "Spirit", "Trinity", "Redemption", "Atonement", "Resurrection", "Holiness",
]
_THEOLOGY_PATTERN = "|".join(
    re.escape(t) for t in sorted(THEOLOGY_TERMS, key=len, reverse=True)
)
_THEOLOGY_RE = re.compile(r"\b(?:" + _THEOLOGY_PATTERN + r")\b", re.IGNORECASE)

# ── Free-text scripture scanner ────────────────────────────────────────────────
# BOOK_MAP keys used directly as regex alternatives (imported from
# app.constants, never forked/re-derived). Sorted longest-first so e.g.
# "song of solomon" is preferred over "song" at the same position.

_BOOK_KEYS_BY_LENGTH = sorted(BOOK_MAP.keys(), key=len, reverse=True)
_BOOK_PATTERN = "|".join(re.escape(k) for k in _BOOK_KEYS_BY_LENGTH)
_FREE_TEXT_SCRIPTURE_RE = re.compile(
    r"\b(?:" + _BOOK_PATTERN + r")\.?\s+\d{1,3}:\d{1,3}(?:[-–—]\d{1,3})?\b",
    re.IGNORECASE,
)


# ── Common religious vocabulary exemption (PLAN.md #45 Phase 6) ───────────────
# A corpus-derived list of 1,210 common cross-teacher religious/theological
# phrases (see scripts/data/common_religious_vocab.json for full provenance:
# derivation corpus of 1,419 in-scope documents / 48 teachers, Precept Austin
# excluded; thresholds >=8 docs / >=5 teachers with a <=50% single-teacher
# dominance guard; a scripture-exclusion pass removing identifiable Bible
# text; derived 2026-07-28). These are stock phrasings shared across many
# unrelated teachers (definitional lines, common exhortations, standard
# theological turns of phrase) -- wording no single teacher owns, so a
# paraphrase reproducing one of these phrases verbatim should not, on its
# own, drive a false paraphrase-closeness flag any more than a shared
# scripture citation or a shared teacher name should (categories 1 and 2
# above).
#
# Matching is FUZZY and SPAN-BASED (like scripture, unlike the plain
# word/regex-substitution masking used for names and the theology stoplist)
# because these are multi-word phrases that can appear with minor real-world
# variance (a dropped filler word, a different tense) the same way a
# scripture quote can. It deliberately reuses _find_quote_span's own anchor +
# gap-tolerant-extend + span-density-floor algorithm and its EXACT constants
# (VERSE_QUOTE_ANCHOR_MIN_WORDS, VERSE_QUOTE_GAP_TOLERANCE,
# VERSE_QUOTE_MIN_EXTEND_BLOCK_WORDS, VERSE_QUOTE_DENSITY_FLOOR) rather than
# introducing a second, independently-tuned set of thresholds -- see
# _anchor_extend_density_span() below, factored out of _find_quote_span
# without changing that function's behavior (proved by the existing
# scripture unit tests passing unchanged; see this module's test suite).

DEFAULT_VOCAB_PATH = _THIS_DIR / "data" / "common_religious_vocab.json"

# The inverted index below keys on 4-word runs (tuples of 4 tokens) drawn
# from each listed phrase's own tokenize() output. 4 is not a new, separately
# tuned constant -- it is VERSE_QUOTE_ANCHOR_MIN_WORDS itself, reused
# directly: any span that could ever qualify as a match (its anchor block
# must be >= VERSE_QUOTE_ANCHOR_MIN_WORDS words on its own) necessarily
# contains at least one contiguous 4-word run from the phrase, so a 4-gram
# index is a lossless (no false-negative-at-this-stage) precondition filter
# for "could this location in the text contain a qualifying anchor for
# phrase P" -- mirroring Dispatch A2's own scripture-matcher design note
# ("a 4-gram inverted index over all verse texts locates candidate verses
# sharing >=1 four-word run with each of the 6528 phrases -- necessary
# precondition for an anchor >=4").
_VOCAB_INDEX_GRAM_LEN = VERSE_QUOTE_ANCHOR_MIN_WORDS


class VocabMatcher(NamedTuple):
    """Compiled, reusable matcher structure -- built ONCE via
    build_vocab_matcher() and reused across every classify() call in a run,
    exactly like build_verse_lookup()'s dict or build_name_pattern()'s
    compiled regex. phrase_token_lists[i] is phrase i's own tokenize()
    output (a tuple, for hashability); inverted_index maps a 4-token tuple
    to the set of phrase indices whose own tokens contain that exact 4-gram
    somewhere."""
    phrase_token_lists: Tuple[Tuple[str, ...], ...]
    inverted_index: Dict[Tuple[str, ...], Set[int]]


def build_vocab_matcher(path: Path = DEFAULT_VOCAB_PATH) -> Optional[VocabMatcher]:
    """Reads scripts/data/common_religious_vocab.json (B-1's committed data
    file) and compiles the fuzzy-matcher structure ONCE. Returns None if the
    file has no phrases (masking becomes a no-op), mirroring
    build_name_pattern()'s empty-set convention. Never reads the DB -- this
    is a pure local-file read, unlike build_name_set()/build_verse_lookup().

    NOTE: this is only the builder's own default arg. It is NOT auto-injected
    into classify() -- classify()'s own vocab_matcher parameter defaults to
    None, so a caller must explicitly build and pass a matcher to opt in,
    exactly like name_pattern and verse_lookup today.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    phrase_token_lists: List[Tuple[str, ...]] = []
    inverted_index: Dict[Tuple[str, ...], Set[int]] = {}
    for entry in data.get("phrases", []):
        phrase_text = entry["phrase"] if isinstance(entry, dict) else entry
        tokens = tuple(tokenize(phrase_text))
        if len(tokens) < _VOCAB_INDEX_GRAM_LEN:
            continue  # can never clear the anchor floor on its own -- skip
        idx = len(phrase_token_lists)
        phrase_token_lists.append(tokens)
        for j in range(len(tokens) - _VOCAB_INDEX_GRAM_LEN + 1):
            gram = tokens[j : j + _VOCAB_INDEX_GRAM_LEN]
            inverted_index.setdefault(gram, set()).add(idx)

    if not phrase_token_lists:
        return None
    return VocabMatcher(
        phrase_token_lists=tuple(phrase_token_lists), inverted_index=inverted_index,
    )


# ── DB read: live name set (Proper-names exemption, step 2) ───────────────────

def build_name_set(db_params: dict) -> Set[str]:
    """Live, read-only SELECT of sources.name + source_aliases.alias_display.

    Deduplicates near-identical raw strings via normalize_alias_key (imported
    from source_resolver — Invariant 6, never reimplemented here). Caller
    supplies db_params; this function does no module-level client
    construction or env-var reads (matches shared_ingest.py's convention).
    """
    import psycopg2

    conn = psycopg2.connect(**db_params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sources WHERE name IS NOT NULL")
        raw = [r[0] for r in cur.fetchall()]
        cur.execute(
            "SELECT alias_display FROM source_aliases WHERE alias_display IS NOT NULL"
        )
        raw += [r[0] for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()

    deduped: Dict[str, str] = {}
    for raw_name in raw:
        key = normalize_alias_key(raw_name)
        if not key:
            continue
        deduped.setdefault(key, raw_name.strip())
    return set(deduped.values())


# ── DB read: live verse-text lookup (scripture-wording exemption fix) ─────────

def build_verse_lookup(db_params: dict) -> Dict[str, str]:
    """Live, read-only SELECT of the ENTIRE `verses` table (verse_id ->
    text). ~31,098 rows as of the 2026-07-26 confirmation run, all
    translation='WEB' -- no other translation exists in this table (see
    module docstring "Scripture-wording exemption fix"). Loaded once and
    reused for every classify() call in a run, mirroring build_name_set's
    bulk-once convention, so per-citation lookups never issue a fresh query
    (avoiding N+1 across a corpus-scale validation run).

    This is the same table reference_verifier._resolve_verse_row queries
    (via a Supabase client, existence-only). Read here directly via
    psycopg2 instead of calling that function, because _resolve_verse_row
    takes a `db` Supabase client object (not a psycopg2 DSN dict, this
    module's own convention) and only returns a boolean -- it has no
    text-returning form to reuse. The verse_id KEY FORMAT
    ("{abbrev}.{chapter}.{verse}") is reproduced EXACTLY as
    _resolve_verse_row builds it (reference_verifier.py line 138), so every
    key in the returned dict lines up with what that function would resolve
    -- same ground truth, read a different way for a different return shape.
    """
    import psycopg2

    conn = psycopg2.connect(**db_params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT verse_id, text FROM verses")
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    return {verse_id: text for verse_id, text in rows}


def _verse_range_text(
    verse_lookup: Dict[str, str], abbrev: str, chapter: int, verse_start: int, verse_end: Optional[int],
) -> Optional[str]:
    """Concatenates verse text for a single verse or a full range, using the
    SAME verse_id key format _resolve_verse_row builds. Returns None if ANY
    endpoint is missing from verse_lookup (citation parsed fine but doesn't
    resolve to a real row, e.g. a bad chapter/verse number) -- no partial
    ground truth, no guessing at partial ranges."""
    end = verse_end if verse_end is not None else verse_start
    if end < verse_start:
        return None
    texts: List[str] = []
    for v in range(verse_start, end + 1):
        verse_id = "{0}.{1}.{2}".format(abbrev, chapter, v)
        t = verse_lookup.get(verse_id)
        if t is None:
            return None
        texts.append(t)
    return " ".join(texts)


def build_name_pattern(name_set: Set[str]) -> Optional[re.Pattern]:
    """Compile a case-insensitive, longest-match-first alternation over a
    name set. Returns None for an empty set (masking becomes a no-op)."""
    names = sorted({n for n in name_set if n and n.strip()}, key=len, reverse=True)
    if not names:
        return None
    alt = "|".join(re.escape(n) for n in names)
    return re.compile(r"\b(?:" + alt + r")\b", re.IGNORECASE)


# ── Masking (parameterized by a token_factory so the same masking logic
#    serves both the primary metric's per-category sentinels and the
#    secondary signal's per-occurrence-unique sentinels) ──────────────────────

def _constant_factory(sentinel: str) -> Callable[[], str]:
    return lambda: sentinel


def _unique_factory(sentinel: str, side: str) -> Callable[[], str]:
    """Per-occurrence-unique token, deliberately built with NO separator
    characters (no underscore, no hyphen). tokenize()'s word regex is
    [a-z0-9]+ -- it does not include underscore, so an earlier version of
    this factory that used "sentinel_side_N" got silently split back into
    three tokens ("sentinel", side, "N") by tokenize(), which threw away
    the uniqueness and let two DIFFERENT masked spans (e.g. two different
    scripture references) collapse back to the same bare sentinel word --
    exactly the spurious sentinel-to-sentinel match this factory exists to
    prevent. Concatenating letters and digits directly (side is a letter,
    the counter is digits) stays within [a-z0-9]+ and survives tokenize()
    as a single, genuinely unique token."""
    counter = {"n": 0}

    def factory() -> str:
        counter["n"] += 1
        return "{0}{1}{2}".format(sentinel, side, counter["n"])

    return factory


def _tokenize_with_spans(sub_text: str, char_offset: int) -> List[Tuple[str, int, int]]:
    """Word-tokenizes sub_text (same [a-z0-9]+ shape as tokenize()'s
    _WORD_RE, applied to sub_text.lower()) while tracking each token's
    character span in the ORIGINAL (not sub_text-local) coordinate system --
    char_offset is where sub_text starts within that original string. Needed
    because the primary tokenize() pipeline throws offsets away (it collapses
    whitespace before matching), but the verse-quote-span finder below has to
    map a matched WORD range back to an exact character span to mask via
    string slicing. str.lower() does not change length for the plain-ASCII
    English text this module processes, so offsets computed on the lowered
    string stay valid against the original."""
    out: List[Tuple[str, int, int]] = []
    for m in _WORD_RE.finditer(sub_text.lower()):
        out.append((m.group(0), m.start() + char_offset, m.end() + char_offset))
    return out


def _anchor_extend_density_span(
    words: List[str], reference_tokens: List[str],
) -> Optional[Tuple[int, int, int]]:
    """Shared core of the anchor + gap-tolerant-extend + span-density-floor
    algorithm (see _find_quote_span's own docstring immediately below for
    the full derivation, revision history, and the live cases that grounded
    each constant -- this function is that algorithm's body, factored out
    unchanged so it can be reused verbatim by both the scripture-wording
    matcher (_find_quote_span) and the common-religious-vocabulary matcher
    (_find_vocab_span, PLAN.md #45 Phase 6) without copy-paste drift between
    the two. This factoring changes NOTHING about the algorithm itself --
    every line below is moved, not edited, from _find_quote_span's own
    per-window loop body; proved byte-identical by the existing scripture
    unit tests (test_closeness_check_unit_proof.py Case 3,
    validate_closeness_check.py's scripture-wording measurements) passing
    unchanged after this refactor.

    `words` is the CANDIDATE window's own ordered word-token list (order
    preserved, no offsets); `reference_tokens` is the verse's (or vocab
    phrase's) own ordered word-token list being searched for within it.

    Returns (first_a, last_a, matched) -- the INCLUSIVE index range in
    `words` bounding the matched span, and the total matched word count
    within that span -- if a qualifying span is found (the single longest
    matching block, i.e. the anchor, is >= VERSE_QUOTE_ANCHOR_MIN_WORDS on
    its own, AND the final gap-tolerant-extended span's density is >=
    VERSE_QUOTE_DENSITY_FLOOR), else None. Callers convert (first_a, last_a)
    back to a character span using their own token-to-char mapping (see
    _find_quote_span and _find_vocab_span)."""
    sm = difflib.SequenceMatcher(None, words, reference_tokens, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
    if not blocks:
        return None

    anchor_idx = max(range(len(blocks)), key=lambda i: blocks[i].size)
    if blocks[anchor_idx].size < VERSE_QUOTE_ANCHOR_MIN_WORDS:
        return None

    included = {anchor_idx}
    cur_start = blocks[anchor_idx].a
    i = anchor_idx - 1
    while i >= 0:
        gap = cur_start - (blocks[i].a + blocks[i].size)
        if gap <= VERSE_QUOTE_GAP_TOLERANCE and blocks[i].size >= VERSE_QUOTE_MIN_EXTEND_BLOCK_WORDS:
            included.add(i)
            cur_start = blocks[i].a
            i -= 1
        else:
            break
    cur_end = blocks[anchor_idx].a + blocks[anchor_idx].size
    i = anchor_idx + 1
    while i < len(blocks):
        gap = blocks[i].a - cur_end
        if gap <= VERSE_QUOTE_GAP_TOLERANCE and blocks[i].size >= VERSE_QUOTE_MIN_EXTEND_BLOCK_WORDS:
            included.add(i)
            cur_end = blocks[i].a + blocks[i].size
            i += 1
        else:
            break

    inc_blocks = [blocks[j] for j in sorted(included)]
    matched = sum(b.size for b in inc_blocks)
    first_a = inc_blocks[0].a
    last_a = inc_blocks[-1].a + inc_blocks[-1].size - 1
    span_len = last_a - first_a + 1
    density = matched / span_len

    if density >= VERSE_QUOTE_DENSITY_FLOOR:
        return first_a, last_a, matched
    return None


def _find_quote_span(text: str, citation_start: int, citation_end: int, verse_text: str) -> Optional[Tuple[int, int]]:
    """Searches VERSE_QUOTE_WINDOW_CHARS on each side of a validated
    citation's own span for a run of the verse's own words (order-preserving,
    via difflib.SequenceMatcher matching blocks -- never a bag-of-words
    count). Returns the TIGHT (start, end) char span in `text` bounding the
    matched region if found on either side (before/after searched
    independently; if both clear the bar, the side with more matched words
    wins), else None. Never returns a span outside the searched window, and
    never a span covering the citation's own characters (before/after
    windows are built from text[..citation_start] and text[citation_end..],
    excluding the citation itself).

    ALGORITHM (anchor + gap-tolerant extend + span-density floor -- revised
    2026-07-26 after a partial-verse-quote failure was caught by hand-
    verification during Step 2's re-run; see module docstring "Scripture-
    wording exemption fix" for why the first version, matched/len(whole
    verse), was wrong and what replaced it):
      1. anchor = the SINGLE LONGEST matching block between window and
         verse tokens. Must be >= VERSE_QUOTE_ANCHOR_MIN_WORDS on its own --
         this is the primary "is there really a solid run of the verse's
         own words here" gate, and it alone (a single contiguous block, not
         an accumulation of scattered singletons) is what a real quote
         reliably produces.
      2. Greedily extend the span outward from the anchor, absorbing
         adjacent matching blocks only while BOTH: the GAP to the next
         block (in window-token space) is <= VERSE_QUOTE_GAP_TOLERANCE, AND
         that block itself is >= VERSE_QUOTE_MIN_EXTEND_BLOCK_WORDS. The
         size-2-minimum on the SECOND check was added same-day as a second
         fix, after the gap-only version (size >= 1 admitted) was itself
         caught live still missing a real quote: isolated single-word
         coincidental matches on common words ("a", "that", "in") sitting
         within gap tolerance but well before the real anchor got absorbed
         into the span, diluting density below the floor for an otherwise
         clean, tight, obviously-real quote (2 Peter 1:19's "until the day
         dawns and the morning star", originally computed at density 0.62
         with those singletons dragged in, at density 1.0 without them).
         The combined rule lets a handful of translation-varying CONNECTOR
         PHRASES (2+ words) inside a real quote get bridged (e.g. KJV "only
         begotten Son" vs WEB "one and only Son" straddling an otherwise-
         matching run), while refusing to chase a stray SINGLE common word
         sitting far from the anchor purely by coincidence — confirmed live
         this stops extension (a "break", not a "skip and keep looking")
         the first time either condition fails, so it never reaches past a
         weak/distant point to grab a stronger block beyond it.
      3. density = matched_words_in_final_span / span_length_in_window_
         tokens. Must be >= VERSE_QUOTE_DENSITY_FLOOR. This replaces the
         original design's matched/len(verse_tokens) recall measure, which
         silently failed whenever a teacher quoted only PART of a longer
         verse (confirmed live: 2 Peter 1:19's second clause, quoted alone,
         is 37% of the full verse's word count -- under the original 55%
         recall floor despite the quoted words matching almost perfectly).
         Density measures "how much of THIS candidate span is verse
         wording" instead of "how much of the WHOLE verse is here" --
         correct for both full and partial quotes, and confirmed live to
         still separate real quotes (John 3:16 KJV: density 0.84; the
         2 Peter 1:19 partial quote: density 0.91) from both an unrelated-
         commentary negative control and two independently confirmed
         translation-mismatch negatives (Isaiah 10:27, Proverbs 4:23 NIV)
         that correctly still return no match.
    """
    verse_tokens = tokenize(verse_text)
    if not verse_tokens:
        return None

    windows = []
    before_start = max(0, citation_start - VERSE_QUOTE_WINDOW_CHARS)
    if before_start < citation_start:
        windows.append(_tokenize_with_spans(text[before_start:citation_start], before_start))
    after_end = min(len(text), citation_end + VERSE_QUOTE_WINDOW_CHARS)
    if citation_end < after_end:
        windows.append(_tokenize_with_spans(text[citation_end:after_end], citation_end))

    best_matched = 0
    best_span: Optional[Tuple[int, int]] = None
    for window_tokens in windows:
        if not window_tokens:
            continue
        words = [t for t, _s, _e in window_tokens]
        found = _anchor_extend_density_span(words, verse_tokens)
        if found is None:
            continue
        first_a, last_a, matched = found

        if matched > best_matched:
            span_start = window_tokens[first_a][1]
            span_end = window_tokens[last_a][2]
            best_matched = matched
            best_span = (span_start, span_end)

    return best_span


def _apply_masked_spans(text: str, spans: List[Tuple[int, int]], token_factory: Callable[[], str]) -> str:
    """Given a list of (start, end) char spans to mask (possibly overlapping
    or adjacent -- e.g. a citation-window quote-span from one citation
    overlapping a neighboring citation's own span in dense text), merges any
    overlapping/touching spans into one contiguous span first, then rebuilds
    the string left-to-right, replacing each MERGED span with exactly ONE
    sentinel token -- never one token per original word, matching the same
    per-category-single-token rule the rest of this module's masking
    already follows (module docstring #4)."""
    if not spans:
        return text
    ordered = sorted(spans)
    merged: List[List[int]] = [list(ordered[0])]
    for s, e in ordered[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    out: List[str] = []
    last = 0
    for s, e in merged:
        out.append(text[last:s])
        out.append(" " + token_factory() + " ")
        last = e
    out.append(text[last:])
    return "".join(out)


def _mask_scripture(
    text: str, token_factory: Callable[[], str], verse_lookup: Optional[Dict[str, str]] = None,
) -> str:
    """Masks (1) every citation that survives _parse_verse_or_range
    re-validation, exactly as before, and (2) -- new, 2026-07-26, only when
    verse_lookup is supplied -- the QUOTED VERSE WORDING found near that
    citation via _find_quote_span. verse_lookup defaults to None so any
    existing call site that hasn't been updated to build/pass one keeps its
    prior citation-only behavior unchanged (backward compatible, not a
    silent behavior change for callers that don't opt in)."""
    spans_to_mask: List[Tuple[int, int]] = []
    validated_citations: List[Tuple[int, int, Tuple[str, int, int, Optional[int]]]] = []

    for m in _FREE_TEXT_SCRIPTURE_RE.finditer(text):
        candidate = re.sub(r"\.", " ", m.group(0))
        candidate = re.sub(r"\s+", " ", candidate).strip()
        parsed = _parse_verse_or_range(candidate)
        if parsed is None:
            # Superficial alternation match that didn't survive real
            # parsing -- leave unmasked rather than guess.
            continue
        spans_to_mask.append((m.start(), m.end()))
        validated_citations.append((m.start(), m.end(), parsed))

    if verse_lookup:
        for c_start, c_end, (abbrev, chapter, v_start, v_end) in validated_citations:
            verse_text = _verse_range_text(verse_lookup, abbrev, chapter, v_start, v_end)
            if verse_text is None:
                continue  # no ground truth for this specific citation -- citation-only mask stands
            quote_span = _find_quote_span(text, c_start, c_end, verse_text)
            if quote_span is not None:
                spans_to_mask.append(quote_span)

    return _apply_masked_spans(text, spans_to_mask, token_factory)


def _find_vocab_span(
    text_tokens: List[Tuple[str, int, int]], hit_pos: int, phrase_tokens: Tuple[str, ...],
) -> Optional[Tuple[int, int]]:
    """Common-religious-vocabulary counterpart to _find_quote_span, reusing
    _anchor_extend_density_span -- the SAME algorithm and the SAME constants
    (VERSE_QUOTE_ANCHOR_MIN_WORDS, VERSE_QUOTE_GAP_TOLERANCE,
    VERSE_QUOTE_MIN_EXTEND_BLOCK_WORDS, VERSE_QUOTE_DENSITY_FLOOR), never a
    re-tuned copy -- against a LOCAL window of the scanned text's own
    (word, char_start, char_end) token list. text_tokens is the WHOLE text,
    already tokenized-with-spans once by _mask_vocab and passed in here.

    Unlike _find_quote_span (which searches a citation-ANCHORED window,
    because a validated scripture citation nearby is strong prior evidence a
    real quote follows), a vocabulary phrase carries no such anchor point.
    The only prior signal here is hit_pos: a text-token index where a
    literal _VOCAB_INDEX_GRAM_LEN-word run shared with phrase_tokens was
    already found via VocabMatcher's inverted index (see _mask_vocab). The
    search window is centered on that confirmed hit and sized directly off
    phrase_tokens' own length plus VERSE_QUOTE_GAP_TOLERANCE on each side --
    not a new, separately tuned window constant: VERSE_QUOTE_GAP_TOLERANCE
    is the same value the extend step itself already uses to decide how far
    it will reach from the anchor, so sizing the window by exactly that much
    beyond the phrase's own length is sufficient to contain anything the
    extend step could legally absorb, and no more."""
    n = len(text_tokens)
    margin = len(phrase_tokens) + VERSE_QUOTE_GAP_TOLERANCE
    lo = max(0, hit_pos - margin)
    hi = min(n, hit_pos + _VOCAB_INDEX_GRAM_LEN + margin)
    window = text_tokens[lo:hi]
    if not window:
        return None
    words = [t for t, _s, _e in window]
    found = _anchor_extend_density_span(words, list(phrase_tokens))
    if found is None:
        return None
    first_a, last_a, _matched = found
    return window[first_a][1], window[last_a][2]


def _mask_vocab(
    text: str, token_factory: Callable[[], str], vocab_matcher: Optional[VocabMatcher],
) -> str:
    """Scans the WHOLE text for any of the 1,210 common-religious-vocabulary
    phrases (scripts/data/common_religious_vocab.json) via VocabMatcher's
    inverted 4-gram index -- an inverted-index-over-the-whole-text approach,
    mirroring how Dispatch A2 built its own standalone scripture matcher,
    NOT a single-span call like _find_quote_span (which has a citation to
    anchor a search window around; a vocabulary phrase doesn't). Defaults to
    a no-op when vocab_matcher is None -- see build_vocab_matcher and
    exempt_for_containment/exempt_for_run for how a caller opts in.

    For every text-position _VOCAB_INDEX_GRAM_LEN-gram that appears in the
    index, every candidate phrase sharing that exact gram is checked via
    _find_vocab_span (same anchor + gap-tolerant-extend + density-floor
    discipline and constants as _find_quote_span, via the shared
    _anchor_extend_density_span helper -- see that function). Every
    qualifying span across every candidate hit is collected and handed to
    _apply_masked_spans, which already merges overlapping/touching spans
    into one sentinel token each -- so overlapping hits (from different
    phrases, or the same phrase confirmed at adjacent text positions)
    collapse correctly rather than double-masking."""
    if vocab_matcher is None:
        return text
    text_tokens = _tokenize_with_spans(text, 0)
    if len(text_tokens) < _VOCAB_INDEX_GRAM_LEN:
        return text
    words = [t for t, _s, _e in text_tokens]

    spans_to_mask: List[Tuple[int, int]] = []
    for i in range(len(words) - _VOCAB_INDEX_GRAM_LEN + 1):
        gram = tuple(words[i : i + _VOCAB_INDEX_GRAM_LEN])
        phrase_indices = vocab_matcher.inverted_index.get(gram)
        if not phrase_indices:
            continue
        for phrase_idx in phrase_indices:
            phrase_tokens = vocab_matcher.phrase_token_lists[phrase_idx]
            span = _find_vocab_span(text_tokens, i, phrase_tokens)
            if span is not None:
                spans_to_mask.append(span)

    return _apply_masked_spans(text, spans_to_mask, token_factory)


def _mask_names(text: str, name_pattern: Optional[re.Pattern], token_factory: Callable[[], str]) -> str:
    if name_pattern is None:
        return text
    return name_pattern.sub(lambda m: " " + token_factory() + " ", text)


def _mask_theology(text: str, token_factory: Callable[[], str]) -> str:
    return _THEOLOGY_RE.sub(lambda m: " " + token_factory() + " ", text)


def exempt_for_containment(
    text: str, name_pattern: Optional[re.Pattern], verse_lookup: Optional[Dict[str, str]] = None,
    vocab_matcher: Optional[VocabMatcher] = None,
) -> str:
    """Exemption pass used by the primary trigram metric: one shared
    sentinel string per category, regardless of how many times or which
    specific span triggered it. Safe because any trigram containing a
    sentinel is excluded from BOTH sets before intersection (see
    _trigrams()) -- never compared, so category-level sentinel reuse cannot
    create a spurious cross-document match. verse_lookup (see
    build_verse_lookup) enables the 2026-07-26 scripture-wording fix in
    _mask_scripture; defaults to None (citation-only masking, prior
    behavior) for callers that haven't built one. vocab_matcher (see
    build_vocab_matcher, PLAN.md #45 Phase 6) enables the common-religious-
    vocabulary exemption in _mask_vocab; defaults to None (no-op) for
    callers that haven't built one either.

    MASKING ORDER -- deliberately scripture, THEN vocab, THEN names, THEN
    theology (not the reverse, and not vocab last). Named risk this order
    exists to close: _mask_theology replaces individual WORDS (e.g. "god")
    with a sentinel via a plain regex substitution -- and several of those
    same words are themselves ANCHOR words inside common-religious-
    vocabulary phrases (e.g. "god the father god the son and" -- confirmed
    live in the 1,210-phrase list, 8 docs/5 teachers). If theology masking
    ran BEFORE vocab masking, it would fragment a vocab phrase's own anchor
    words into sentinel tokens first, and the vocab fuzzy matcher (which
    tokenizes and matches against the phrase's OWN literal words, never
    against a sentinel placeholder) would then simply fail to find the
    phrase at all -- a real discount silently lost to masking-order alone,
    not a genuine absence of the phrase. Running vocab BEFORE theology (and
    before names, for the same reason -- names masking is also a
    plain-word/regex substitution that could, in principle, consume a word
    a vocab phrase also needs) means the vocab matcher always sees the
    least-mutated text available, so a listed phrase's own wording is intact
    for it to find. Scripture runs first regardless, because it operates on
    citation-anchored SPANS (not bare stoplist words) that essentially never
    overlap a vocab phrase's own wording, so its position relative to vocab
    doesn't carry the same fragmentation risk the theology/name stoplists
    do. See test_closeness_check_unit_proof.py's vocab case for the
    end-to-end proof this order actually discounts the intended phrasing
    (masked-token-stream and containment/residual before vs. after)."""
    text = unicodedata.normalize("NFKC", text)
    text = _mask_scripture(text, _constant_factory(SENTINEL_SCRIPTURE), verse_lookup)
    text = _mask_vocab(text, _constant_factory(SENTINEL_VOCAB), vocab_matcher)
    text = _mask_names(text, name_pattern, _constant_factory(SENTINEL_NAME))
    text = _mask_theology(text, _constant_factory(SENTINEL_THEOLOGY))
    return text


def exempt_for_run(
    text: str, name_pattern: Optional[re.Pattern], side: str, verse_lookup: Optional[Dict[str, str]] = None,
    vocab_matcher: Optional[VocabMatcher] = None,
) -> str:
    """Exemption pass used by the secondary longest-run signal: every
    masked occurrence gets a UNIQUE token (side-tagged so P-side and S-side
    sentinels can never equal each other either), so SequenceMatcher can
    never report a 'match' that is actually two different verses / two
    different names / two different stoplist words / two different vocab
    phrases that both happened to get masked. verse_lookup threads through
    to _mask_scripture the same way as exempt_for_containment (see there);
    defaults to None. vocab_matcher threads through to _mask_vocab the same
    way; defaults to None. Masking order (scripture, vocab, names, theology)
    is identical to exempt_for_containment -- see that function's docstring
    for why (the theology/name-word-fragmentation risk applies equally
    here)."""
    text = unicodedata.normalize("NFKC", text)
    text = _mask_scripture(text, _unique_factory(SENTINEL_SCRIPTURE, side), verse_lookup)
    text = _mask_vocab(text, _unique_factory(SENTINEL_VOCAB, side), vocab_matcher)
    text = _mask_names(text, name_pattern, _unique_factory(SENTINEL_NAME, side))
    text = _mask_theology(text, _unique_factory(SENTINEL_THEOLOGY, side))
    return text


# ── Tokenization ────────────────────────────────────────────────────────────
# lowercase, unicode-normalize, collapse whitespace, split on word boundaries.
# (unicode-normalize already applied upstream in exempt_for_* before masking,
# so exemption regexes see accented/composed forms consistently too.)

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def tokenize(text: str) -> List[str]:
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return _WORD_RE.findall(text)


# ── Trigram containment (primary metric) ───────────────────────────────────

def _trigrams(tokens: List[str]) -> Set[Tuple[str, str, str]]:
    """Trigram SET (each distinct 3-token window counted once). Any trigram
    containing a sentinel token is dropped -- excluded, never compared."""
    out: Set[Tuple[str, str, str]] = set()
    for i in range(len(tokens) - 2):
        tri = (tokens[i], tokens[i + 1], tokens[i + 2])
        if any(t in _SENTINELS for t in tri):
            continue
        out.add(tri)
    return out


def containment_score(paraphrase_tokens: List[str], source_tokens: List[str]) -> Tuple[float, int]:
    """Returns (containment, paraphrase_trigram_count).
    containment = |trigrams(P) ∩ trigrams(S)| / |trigrams(P)|.
    0.0 with a trigram count of 0 if the paraphrase has fewer than 3
    non-sentinel tokens in a row anywhere (the too-little check, not this
    function, is responsible for flagging that case -- this function just
    reports what it measured)."""
    p_tris = _trigrams(paraphrase_tokens)
    s_tris = _trigrams(source_tokens)
    if not p_tris:
        return 0.0, 0
    overlap = p_tris & s_tris
    return len(overlap) / len(p_tris), len(p_tris)


def residual_token_count(tokens: List[str]) -> int:
    """Non-sentinel token count -- what the too-little check measures."""
    return sum(1 for t in tokens if t not in _SENTINELS)


# ── Longest contiguous verbatim run, in words (secondary signal) ──────────────

def longest_common_run(
    paraphrase_text: str, source_text: str, name_pattern: Optional[re.Pattern],
    verse_lookup: Optional[Dict[str, str]] = None, vocab_matcher: Optional[VocabMatcher] = None,
) -> Tuple[int, Tuple[str, ...]]:
    """difflib.SequenceMatcher over residual WORD tokens (not characters).
    Uses exempt_for_run()'s per-occurrence-unique sentinels so exempted
    spans can never contribute to the reported run. verse_lookup threads
    through to exempt_for_run the same way as elsewhere; defaults to None.
    vocab_matcher threads through the same way; defaults to None."""
    p_text = exempt_for_run(paraphrase_text, name_pattern, "p", verse_lookup, vocab_matcher)
    s_text = exempt_for_run(source_text, name_pattern, "s", verse_lookup, vocab_matcher)
    p_tokens = tokenize(p_text)
    s_tokens = tokenize(s_text)

    sm = difflib.SequenceMatcher(None, p_tokens, s_tokens, autojunk=False)
    match = sm.find_longest_match(0, len(p_tokens), 0, len(s_tokens))
    run = tuple(p_tokens[match.a : match.a + match.size])
    return match.size, run


# ── Three-verdict classification (classifies only -- does not act) ────────────

class ClosenessResult(NamedTuple):
    verdict: str
    containment: float
    residual_tokens: int
    paraphrase_trigram_count: int
    longest_run_words: int
    longest_run_tokens: Tuple[str, ...]


def classify(
    paraphrase_text: str, source_text: str, name_pattern: Optional[re.Pattern],
    verse_lookup: Optional[Dict[str, str]] = None, vocab_matcher: Optional[VocabMatcher] = None,
) -> ClosenessResult:
    """verse_lookup (see build_verse_lookup) enables the 2026-07-26
    scripture-wording exemption fix; defaults to None for backward
    compatibility with call sites that haven't built one (citation-only
    masking, the prior behavior). vocab_matcher (see build_vocab_matcher,
    PLAN.md #45 Phase 6) enables the common-religious-vocabulary exemption;
    also defaults to None for the same backward-compatibility reason --
    NOT auto-built or auto-injected here, a caller must explicitly build and
    pass one to opt in."""
    p_masked = exempt_for_containment(paraphrase_text, name_pattern, verse_lookup, vocab_matcher)
    s_masked = exempt_for_containment(source_text, name_pattern, verse_lookup, vocab_matcher)
    p_tokens = tokenize(p_masked)
    s_tokens = tokenize(s_masked)

    residual = residual_token_count(p_tokens)
    containment, p_tri_count = containment_score(p_tokens, s_tokens)
    run_len, run_tokens = longest_common_run(
        paraphrase_text, source_text, name_pattern, verse_lookup, vocab_matcher,
    )

    # Two INDEPENDENT trip conditions for QUOTE_CANDIDATE (Phase 4, PLAN.md
    # #45, wired in after Step 2's re-run derived LONGEST_RUN_WORD_THRESHOLD
    # from real should-pass/R-run data): containment >= CONTAINMENT_FLOOR
    # (primary/first-checked, per prior direction) OR
    # longest_run_words >= LONGEST_RUN_WORD_THRESHOLD (second, independent
    # condition -- not a replacement). The OR is required, not a stricter
    # AND: the R-run adversarial evidence (Step 2 re-run, this file's own
    # validate_closeness_check.py) showed genuine splice items whose
    # containment STAYS LOW (0.20-0.29 after splicing, well under the 0.40
    # floor -- containment alone would PASS every one of them) while their
    # longest_run jumps from a clean pair's 2-3 words to 12-13 words for the
    # spliced run. An AND would let those items slip through on containment
    # alone; the OR catches them via the run-length signal instead, exactly
    # as the R-run items were built to demonstrate.
    if residual < RESIDUAL_TOO_LITTLE_CUTOFF:
        verdict = HOLD_TOO_LITTLE
    elif containment >= CONTAINMENT_FLOOR or run_len >= LONGEST_RUN_WORD_THRESHOLD:
        verdict = QUOTE_CANDIDATE
    else:
        verdict = PASS

    return ClosenessResult(
        verdict=verdict,
        containment=containment,
        residual_tokens=residual,
        paraphrase_trigram_count=p_tri_count,
        longest_run_words=run_len,
        longest_run_tokens=run_tokens,
    )
