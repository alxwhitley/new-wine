"""
propositions.py — shared module for proposition extraction and storage.

Called by ingest scripts after chunk insertion. Gate: extracts for licensed
and unlicensed sources only (skips public_domain and owned), with Precept
Austin locked out by name (see process_document). Non-fatal by contract: no
public function raises.

--------------------------------------------------------------------------
Closeness-check gate (PLAN.md #45 Phase 5, 2026-07-26) — OPTIONAL, DEFAULT-OFF
--------------------------------------------------------------------------
process_document() accepts two new optional parameters, name_pattern and
verse_lookup (both default None), that mirror closeness_check.classify()'s
own signature. The gate is OFF unless name_pattern is explicitly supplied
by the caller -- every real ingest path today (shared_ingest.py,
ingest_helloao.py) passes neither, so behavior for every existing caller is
BYTE-IDENTICAL to pre-Phase-5: same extraction call, same store_propositions
call with the full unfiltered list, same "stored:{n}" return string, same
never-raises contract. closeness_check is imported LAZILY, inside the
gate-active branch only, so an off caller incurs zero import-time cost or
side effect from that module either.

When the gate IS active (name_pattern is not None), every extracted
proposition is classified via closeness_check.classify(content, text,
name_pattern, verse_lookup) -- `text` (the whole source document) doubles
as the source_text classify() needs, since process_document already
receives it. PASS items proceed to store_propositions() unchanged (that
function itself is NOT modified -- it still just receives a list).
QUOTE_CANDIDATE and HOLD_TOO_LITTLE items are withheld from the insert and
appended instead to CLOSENESS_REVIEW_PATH (see _write_review_records) with
full provenance. Every extracted proposition lands in exactly one bucket --
see the assertion in process_document() below. The return value extends to
"stored:{n}:flagged:{m}" so a statement is never silently lost between the
two counts (only when the gate is active; an off caller still gets the
plain "stored:{n}" it always got).

process_document() also accepts a third optional parameter, vocab_matcher
(PLAN.md #45 Phase 6, 2026-07-28, default None), mirroring
closeness_check.classify()'s own vocab_matcher parameter (see
closeness_check.build_vocab_matcher). It threads straight through to the
classify() call the same inert way name_pattern/verse_lookup already do --
supplying it has no effect unless the gate is already active (name_pattern
supplied), and NOT supplying it (the default) leaves behavior byte-identical
to before this parameter existed. Still no gate activation and no new
default-on behavior: this is wiring only.

--------------------------------------------------------------------------
Closeness-check gate RETIRED (project owner decision, 2026-07-29)
--------------------------------------------------------------------------
The gate described immediately above is now permanently disabled,
regardless of what any caller supplies for name_pattern/verse_lookup/
vocab_matcher. Decision: near-verbatim reuse of a teacher's own wording is
an accepted risk going forward, not something to review or block. The
retroactive 213-item review this gate's calibration was built to feed
(PLAN.md #47) was closed without full completion for the same reason --
see rhemata-status.md.

Enforced by a single flag, CLOSENESS_CHECK_RETIRED (defined just above
process_document() below), which widens process_document()'s existing
`if name_pattern is None:` branch condition so it is now ALWAYS taken. This
is deliberately NOT a deletion: the gate-active branch inside
process_document() (the lazy closeness_check import, the classify() loop,
the review-file write) and closeness_check.py itself remain fully intact,
character-for-character, for a possible future reversal -- flip that one
constant back to False. Every other direct importer of closeness_check
(closeness_triage.py, validate_closeness_check.py, and the rest of the
retroactive-triage tooling) is entirely unaffected, since this flag only
gates process_document()'s own internal branch, not the module itself.

--------------------------------------------------------------------------
Reference-grounding fix (PLAN.md #45, 2026-07-28) -- ALWAYS ON, NOT a gate
--------------------------------------------------------------------------
Unlike the closeness-check gate above (default-OFF, opt-in via name_pattern),
this fix is unconditional and lives INSIDE extract_propositions() itself --
not process_document() -- because a now-deleted one-off script proved
extract_propositions()/store_propositions() are directly callable, bypassing
process_document()'s gates entirely. A fix that only ran in process_document()
would leave that exact bypass open; wiring it into extract_propositions()
closes it for every caller, direct or gated, with no opt-out parameter.

After the model's raw JSON response is parsed, every scripture reference
found in each proposition's `content` (via reference_grounding.
find_reference_spans()) is checked with reference_grounding.
check_reference_grounded() against `text` (the source document already in
scope). GROUNDED references are left untouched. UNGROUNDED/UNCERTAIN
references have ONLY their own parsed-reference span removed from `content`
(boundary-safe -- never a blind str.replace(), see
_strip_ungrounded_references()) -- everything else in `content`, including
surrounding prose, is left verbatim. No proposition is ever dropped by this
step; every strip is logged to GROUNDING_REVIEW_PATH (see
_write_grounding_review_records()), gitignored, same convention as
CLOSENESS_REVIEW_PATH above.

verse_lookup is never supplied here (extract_propositions() has no DB
connection of its own to build one) -- so only check_reference_grounded()'s
citation-string arm ever fires from this call site; its wording arm is
reachable only by a caller that supplies verse_lookup directly to that
function (e.g. this module's own test suite). This is a known, accepted
scope boundary, not an oversight -- see reference_grounding.py's own
docstring for the two-arm design.

--------------------------------------------------------------------------
Bypass-proofing Phase 1 additions (PLAN.md #45 Phase 1, 2026-07-29)
--------------------------------------------------------------------------
Two additions on top of the always-on strip above, both still unconditional
with no opt-out parameter:

1. UPSTREAM: _build_allowed_reference_block() appends a CLOSED list of every
   compact-form reference find_reference_spans() finds in `text` to the
   outgoing model message, on both the v3 and v4 branches -- see that
   function's own comment for the known asymmetry it accepts (spoken-form
   references are invisible to it; the downstream arbiter below is the
   backstop for those).

2. DOWNSTREAM: an UNGROUNDED/UNCERTAIN reference is no longer stripped
   immediately -- _strip_ungrounded_references() now sends it to
   citation_verifier_layers.verify_reference_grounded() (the widened,
   spoken-form-aware Layers 1-3 arbiter) first. A reference the arbiter
   CONFIRMS is kept, not stripped, even though the primary (compact-form-
   only) check here couldn't find it. See _strip_ungrounded_references()'s
   own docstring for the full four-way outcome table and the StripResult
   accounting shape this changed.
"""

import hashlib
import json
import logging
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from groq import Groq
from psycopg2.extras import execute_values

import reference_grounding as rg
from magazine_review.schemas import ApprovedPropositionSet, ArtifactValidationError

logger = logging.getLogger(__name__)

# ── Closeness-check review file (PLAN.md #45 Phase 5) ─────────────────────────
# Gitignored, local-only holding area for QUOTE_CANDIDATE/HOLD_TOO_LITTLE
# statements withheld from the DB by the gate above. NOT `recovery/` --
# that directory's own existing convention is DB-restoration snapshots
# (deletion backups etc.), a different kind of artifact; this is a
# human-review queue for the closeness check. See .gitignore for the
# matching `closeness_review/` entry.
CLOSENESS_REVIEW_DIR = Path(__file__).resolve().parent.parent / "closeness_review"
CLOSENESS_REVIEW_PATH = CLOSENESS_REVIEW_DIR / "flagged_propositions.jsonl"


def _write_review_records(records: List[dict]) -> bool:
    """Best-effort append of `records` (one JSON object per line, JSONL) to
    CLOSENESS_REVIEW_PATH. Returns True on success, False on any failure --
    NEVER raises past this function. A filesystem failure here must not be
    indistinguishable from, and must not roll back, an already-successful,
    already-committed store_propositions() call for this same document (see
    process_document()'s TRANSACTION-ORDERING NOTE below) -- so a failure is
    logged at ERROR with the full record payload (nothing silently lost from
    the logs' perspective even if the file write itself fails) rather than
    raised."""
    try:
        CLOSENESS_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with open(CLOSENESS_REVIEW_PATH, "a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:
        logger.error(
            "CLOSENESS_REVIEW_WRITE_FAIL path=%r n_records=%d error=%s records=%r",
            str(CLOSENESS_REVIEW_PATH), len(records), exc, records,
        )
        return False


# ── Reference-grounding review file (PLAN.md #45, 2026-07-28) ─────────────────
# Gitignored, local-only holding area for every UNGROUNDED/UNCERTAIN scripture
# reference stripped by extract_propositions() -- see this module's top-of-file
# docstring "Reference-grounding fix" section. Same directory-per-concern
# convention as CLOSENESS_REVIEW_DIR above (a separate path, not reused,
# since this is a different check writing a different record shape) -- see
# .gitignore for the matching `reference_grounding_review/` entry.
GROUNDING_REVIEW_DIR = Path(__file__).resolve().parent.parent / "reference_grounding_review"
GROUNDING_REVIEW_PATH = GROUNDING_REVIEW_DIR / "stripped_references.jsonl"


def _write_grounding_review_records(records: List[dict]) -> bool:
    """Best-effort append of `records` (one JSON object per line, JSONL) to
    GROUNDING_REVIEW_PATH. Returns True on success, False on any failure --
    NEVER raises past this function, mirroring _write_review_records()
    above exactly (same rationale: a filesystem failure here must not be
    indistinguishable from, and must not roll back, extraction that already
    succeeded -- logged at ERROR with the full record payload instead of
    raised)."""
    try:
        GROUNDING_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with open(GROUNDING_REVIEW_PATH, "a", encoding="utf-8") as f:
            for record in records:
                persisted_record = dict(record)
                persisted_record.setdefault(
                    "written_at", datetime.now(timezone.utc).isoformat()
                )
                f.write(json.dumps(persisted_record, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:
        logger.error(
            "GROUNDING_REVIEW_WRITE_FAIL path=%r n_records=%d error=%s records=%r",
            str(GROUNDING_REVIEW_PATH), len(records), exc, records,
        )
        return False


def _remove_reference_span(text: str, start: int, end: int) -> str:
    """Boundary-safe removal of exactly text[start:end] -- never a blind
    str.replace(reference_string, ""), which would also corrupt an
    unrelated, separately-occurring longer/prefixed reference elsewhere in
    the string that happens to literally contain the removed reference's
    own string (e.g. blind-replacing "Galatians 6:1" would also maim a
    separate, later, GROUNDED "Galatians 6:14" into "4"). Only the exact
    character span `find_reference_spans()` located is ever touched.

    After removal, performs NARROW seam cleanup AT THE SEAM ONLY (never
    elsewhere in the string): collapses a double space landing exactly at
    the seam into one, and drops a stray space immediately before a comma
    landing exactly at the seam (mechanical debris from the removal itself
    -- e.g. "in Romans 8:28, where" -> "in , where" -> "in, where").
    Deliberately does NOT touch adjacent connector words ("as stated in",
    "citing", "per") or any punctuation not directly at the seam -- those
    are surrounding text, out of bounds. Leaving "as stated in, where
    Paul..." after a strip is an accepted, disclosed cosmetic gap, not
    repaired further here."""
    new_text = text[:start] + text[end:]
    seam = start

    # Collapse a double space landing exactly at the seam into one.
    if new_text[seam - 1:seam] == " " and new_text[seam:seam + 1] == " ":
        new_text = new_text[:seam] + new_text[seam + 1:]

    # Drop a stray space immediately before a comma landing at the seam.
    if new_text[seam:seam + 1] == "," and new_text[seam - 1:seam] == " ":
        new_text = new_text[:seam - 1] + new_text[seam:]

    return new_text


class StripResult(NamedTuple):
    """Return shape for _strip_ungrounded_references(). Positionally
    unpack-compatible with the pre-arbitration 6-tuple this replaces (every
    field through n_stripped_uncertain is in the same order) PLUS one new
    trailing field, n_kept_arbitration -- every existing 6-value unpack call
    site needs exactly one more variable added, nothing reordered."""
    new_content: str
    review_records: List[dict]
    n_found: int
    n_grounded: int
    n_stripped_fabricated: int
    n_stripped_uncertain: int
    n_kept_arbitration: int


def _strip_ungrounded_references(
    content: str, source_text: str, document_id: str, proposition_index,
) -> StripResult:
    """Finds every scripture reference in `content`, checks each against
    `source_text` via reference_grounding.check_reference_grounded()
    (verse_lookup=None -- see module docstring). GROUNDED references are
    left untouched.

    UNGROUNDED/UNCERTAIN references are NOT immediately stripped (PLAN.md
    #45 Phase 1, 2026-07-29 arbitration build). Before stripping, each one
    is sent to citation_verifier_layers.verify_reference_grounded() (the
    widened, spoken-form-aware Layers 1-3 arbiter) as a second opinion --
    the primary check here only recognizes compact "Book C:V" citation
    forms, so a genuine spoken-form reference the primary check can't find
    would otherwise be wrongly stripped. Four-way outcome:

      arbiter confirmed=True                          -> KEEP (not stripped)
        review label "arbitration_overturned"
      confirmed=False, reason starts "layer3_llm_call_failed"
        -> STRIP (fail-safe), label "arbitration_unavailable"
      confirmed=False, reason == "unparseable_reference"
        -> STRIP (fail-safe), label "arbitration_unavailable_unparseable"
      confirmed=False, any other reason (e.g. "layer3_llm_denied")
        -> STRIP (existing boundary-safe removal, unchanged),
           label "arbitration_agreed"

    The two "_unavailable*" fail-safe branches are a disclosed, deliberate,
    narrow exception to CLAUDE.md Invariant 11's general "never strip on
    mere failure-to-confirm" posture -- scoped ONLY to "the arbiter itself
    could not run/parse," never to the old, rejected "primary check simply
    couldn't confirm" trigger Invariant 11 was written to close. Alex's own
    task brief for this build: "A fabricated reference reaching users is
    worse than a lost genuine one." This will be reflected explicitly in a
    later records-update phase of this same project, not left silently
    implicit here.

    citation_verifier_layers is imported LAZILY, inside this function, on
    every call that needs it -- NOT at this module's top level. Reason:
    citation_verifier_layers.py itself already imports this module
    (`propositions`) at ITS OWN top level (to reuse _get_groq()/
    EXTRACTION_MODEL for its Layer 3 LLM call) -- a module-level import
    here would be circular. Called as a bare module attribute
    (`cvl.verify_reference_grounded(...)`), never bound via `from
    citation_verifier_layers import verify_reference_grounded` -- a `from`
    import captures the function object at import time and would not see a
    test's later monkeypatch of the module's own attribute; calling through
    the module object does (same monkeypatch precedent this file's own
    `rg.check_reference_grounded` call already relies on for testability).

    Returns a StripResult (new_content, review_records, n_found, n_grounded,
    n_stripped_fabricated, n_stripped_uncertain, n_kept_arbitration) -- the
    five right-hand counts always satisfy n_found == n_grounded +
    n_stripped_fabricated + n_stripped_uncertain + n_kept_arbitration
    (asserted by the caller, _apply_reference_grounding()), so a reference
    can never silently vanish from the accounting -- an arbitration-kept
    reference is neither "grounded by the primary check" nor "stripped"; it
    has its own bucket.

    review_records now carries an entry for EVERY reference that reached
    arbitration (kept OR stripped, not stripped-only as before) -- each one
    retains the ORIGINAL primary-check signal in "reason" ("fabricated" for
    UNGROUNDED / "uncertain" for UNCERTAIN, unchanged from before
    arbitration existed) AND adds "arbitration" (one of the four labels
    above) plus "arbitration_reason" (the arbiter's own raw reason string,
    for auditability) as new fields alongside it, never replacing it.

    A per-reference exception inside check_reference_grounded() itself is
    caught locally and treated as UNCERTAIN -- exactly as before -- and
    that forced UNCERTAIN then goes through arbitration exactly like any
    other UNCERTAIN, no special-cased fail-safe path for it specifically.
    A per-reference exception raised unexpectedly by the ARBITER itself
    (verify_reference_grounded is documented not to raise for ordinary
    cases, but this does not trust that blindly) is caught the same way and
    treated as "arbitration_unavailable" -> STRIP, same as a reported
    layer3_llm_call_failed result."""
    spans = rg.find_reference_spans(content)
    if not spans:
        return StripResult(content, [], 0, 0, 0, 0, 0)

    n_grounded = 0
    n_fabricated = 0
    n_uncertain = 0
    n_kept_arbitration = 0
    review_records: List[dict] = []
    to_strip: List[Tuple[int, int, str]] = []  # (start, end, raw)

    for span in spans:
        try:
            result = rg.check_reference_grounded(span.raw, source_text, verse_lookup=None)
            status = result.status
        except Exception as exc:
            logger.warning(
                "REFERENCE_GROUNDING_CHECK_FAIL doc=%r ref=%r error=%s -- treating as UNCERTAIN",
                document_id, span.raw, exc,
            )
            status = rg.UNCERTAIN

        if status == rg.GROUNDED:
            n_grounded += 1
            continue

        primary_reason = "fabricated" if status == rg.UNGROUNDED else "uncertain"

        # Lazy, in-function import -- see this function's own docstring for
        # why (circular-import avoidance + test-monkeypatch requirement).
        import citation_verifier_layers as cvl

        try:
            arb = cvl.verify_reference_grounded(span.raw, source_text, llm_enabled=True)
            arb_confirmed = arb.confirmed
            arb_reason = arb.reason
            arb_raised = False
        except Exception as exc:
            logger.warning(
                "ARBITRATION_CALL_FAIL doc=%r ref=%r error=%s -- treating as "
                "unavailable, stripping (fail-safe)",
                document_id, span.raw, exc,
            )
            arb_confirmed = False
            arb_reason = "arbitration_raised:{0}".format(exc)
            arb_raised = True

        if arb_confirmed:
            arbitration_label = "arbitration_overturned"
            n_kept_arbitration += 1
        else:
            # arb_raised (the arbiter FUNCTION itself raised, caught above)
            # is checked FIRST and unconditionally maps to
            # "arbitration_unavailable" -- it must never fall through to the
            # string-prefix checks below, which only apply to a normally
            # RETURNED VerificationResult's own `reason` field.
            if arb_raised or arb_reason.startswith("layer3_llm_call_failed"):
                arbitration_label = "arbitration_unavailable"
            elif arb_reason == "unparseable_reference":
                arbitration_label = "arbitration_unavailable_unparseable"
            else:
                arbitration_label = "arbitration_agreed"
            to_strip.append((span.start, span.end, span.raw))
            if primary_reason == "fabricated":
                n_fabricated += 1
            else:
                n_uncertain += 1

        review_records.append({
            "document_id": document_id,
            "proposition_index": proposition_index,
            "reference": span.raw,
            "reason": primary_reason,
            "arbitration": arbitration_label,
            "arbitration_reason": arb_reason,
        })

    if not to_strip:
        return StripResult(
            content, review_records, len(spans), n_grounded,
            n_fabricated, n_uncertain, n_kept_arbitration,
        )

    new_content = content
    # Descending start order: removing the rightmost span first never shifts
    # the character offsets of spans still pending removal (all of which lie
    # strictly to its left, per find_reference_spans()'s non-overlapping,
    # ascending-order regex matches) -- see this function's own module-level
    # docstring section and the boundary-safety unit test for the proof.
    for start, end, _raw in sorted(to_strip, key=lambda t: t[0], reverse=True):
        new_content = _remove_reference_span(new_content, start, end)

    return StripResult(
        new_content, review_records, len(spans), n_grounded,
        n_fabricated, n_uncertain, n_kept_arbitration,
    )


# Single source of truth for both the model requested (recorded verbatim on
# every stored row -- see store_propositions()'s model param) and the
# default prompt_version every real ingest path uses (process_document()
# never exposes prompt_version to its callers, so this constant is what
# "v3" actually means there -- referencing it in both places means the
# extraction call and its provenance stamp can never name two different
# versions by accident).
EXTRACTION_MODEL = "openai/gpt-oss-120b"
DEFAULT_PROMPT_VERSION = "v3"

# ── Prompt ────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """\
You are extracting propositions from a single theological document for a research tool. A proposition is one self-contained teaching claim from the document, restated entirely in your own words.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is physically present in the document text provided. You are summarizing this one document, not teaching the topic. You may not add anything from your own knowledge — not a Bible reference, not an example, not a cross-reference, not a related verse, not background context. If it is not in the provided text, it does not exist for this task. When in doubt, leave it out.

Applying that rule:

Scripture references — capture every one the source gives, invent none it doesn't. If the document explicitly prints a reference (e.g. the text says "Hebrews 3:1" or "Mark 11:23"), and a proposition covers that teaching, that reference MUST appear in the proposition. At the same time: if the author quotes or alludes to a verse without naming it, restate the teaching but do NOT supply the reference, even if you recognize the verse. Two equal failures to avoid: dropping a reference the author printed, and adding one the author didn't. Capture what's there; invent nothing that isn't.
Examples and illustrations: Use only the examples the document actually contains. Never introduce an illustration, story, or analogy of your own.
Claims: Represent only what the document asserts. Do not extend, infer, or theologize beyond it.

Paraphrase rules:

Full rewrite in your own words. Never reuse the author's distinctive phrasing or sentence structure. Never reproduce three or more consecutive words from the source (quoted scripture excepted — scripture wording may stand). If a restatement starts mirroring the original, rebuild it from scratch.
This applies even to short, simple, or definitional sentences — those are the easiest to copy by accident. For example, if the author writes "A disciple is simply a follower of Christ," do not reuse that clause; restructure the idea, e.g. "The author defines discipleship plainly — following Christ, not attaining a special status." Only quoted scripture wording may stand unchanged.
Attribute naturally ("the author teaches…") but only to what the author actually said.
Neutral voice. Never use charged language ("heretical," "demonic," "apostate") in your own voice even if the source does.

Count and distinctness:

Extract one teaching passage per genuinely distinct teaching point. There is NO target number and no minimum count. When the document contains a genuine, distinct teaching point, however brief, it must still be extracted as its own passage — a short passage that makes one real teaching claim still deserves to be pulled out. But when the document contains no genuine, distinct teaching point at all — administrative content, a bare fragment or title, a throwaway remark with nothing substantive to paraphrase — the correct, expected output is an empty array. Do not manufacture a teaching passage from padding, from restating a title, or from inflating a throwaway remark just to produce output.
If two points make substantially the same claim, MERGE them into one. Near-duplicate passages are a failure.

Length: ~80–150 words each.

Output ONLY a JSON array, no preamble, no markdown fences:
[{"proposition_index": 1, "content": "..."}, {"proposition_index": 2, "content": "..."}]"""

# ── v3.1 prompt (2026-07-30) — ISOLATED naming fix only ───────────────────────
# Alex's explicit decision: fix the "the author" defect (measured at 84% of
# 222 propositions in the 25-doc backfill proving batch, same session) WITHOUT
# adopting v4's bundled length/sentence-structure/voice retuning. v4 already
# diagnosed and solved the naming problem (see v4's own change #2 below,
# "Attribution") -- this constant is EXACTLY EXTRACTION_PROMPT (v3) with ONLY
# that one mechanism grafted in, nothing else touched.
#
# Mechanism, precisely: (a) the model is told the speaker's real name via a
# new {speaker} format placeholder (mirroring v4's own mechanism -- extract_
# propositions() must be called with a non-empty speaker for this version,
# exactly like v4 already requires); (b) every place v3's prompt referred
# generically to "the author" (8 occurrences across 4 lines: the scripture-
# reference bullet x3, the paraphrase-rules "reuse the author's phrasing"
# bullet x1, the worked micro-example x2, the attribution bullet x2) is
# replaced with {speaker}; (c) the attribution bullet gains one explicit
# negative instruction, "never 'the author'" (v4's own proven phrasing for
# this), since leaving the OLD bullet's wording (which explicitly modeled
# "the author teaches..." as correct) unchanged would directly contradict a
# same-sentence instruction not to write that -- the worked example at (b)
# needed the identical fix for the identical reason (it modeled "The author
# defines..." as the CORRECT restructured form).
#
# Everything else is BYTE-IDENTICAL to EXTRACTION_PROMPT: the opening framing
# sentence, the FOUR CORNERS rule, the examples/illustrations and claims
# bullets, "Neutral voice...", the ENTIRE "Count and distinctness" section,
# and "Length: ~80-150 words each." (v3's original single-line length
# guidance, not v4's expanded section+worked-example -- the thing this
# change is explicitly NOT adopting). Only the trailing JSON-array line's
# literal braces are escaped ({{ }}) for .format() mechanics -- the text
# itself is unchanged. Selected via extract_propositions(prompt_version=
# "v3.1", speaker=...); process_document() only uses it when a caller
# explicitly supplies prompt_version="v3.1" (or "v4") -- DEFAULT_PROMPT_
# VERSION stays "v3", so every existing caller/test that doesn't opt in is
# byte-identical to before this change (same discipline as name_pattern/
# verse_lookup/vocab_matcher/chunk_ids above).
EXTRACTION_PROMPT_V3_1 = """\
You are extracting propositions from a single theological document for a research tool. A proposition is one self-contained teaching claim from the document, restated entirely in your own words.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is physically present in the document text provided. You are summarizing this one document, not teaching the topic. You may not add anything from your own knowledge — not a Bible reference, not an example, not a cross-reference, not a related verse, not background context. If it is not in the provided text, it does not exist for this task. When in doubt, leave it out.

Applying that rule:

Scripture references — capture every one the source gives, invent none it doesn't. If the document explicitly prints a reference (e.g. the text says "Hebrews 3:1" or "Mark 11:23"), and a proposition covers that teaching, that reference MUST appear in the proposition. At the same time: if {speaker} quotes or alludes to a verse without naming it, restate the teaching but do NOT supply the reference, even if you recognize the verse. Two equal failures to avoid: dropping a reference {speaker} printed, and adding one {speaker} didn't. Capture what's there; invent nothing that isn't.
Examples and illustrations: Use only the examples the document actually contains. Never introduce an illustration, story, or analogy of your own.
Claims: Represent only what the document asserts. Do not extend, infer, or theologize beyond it.

Paraphrase rules:

Full rewrite in your own words. Never reuse {speaker}'s distinctive phrasing or sentence structure. Never reproduce three or more consecutive words from the source (quoted scripture excepted — scripture wording may stand). If a restatement starts mirroring the original, rebuild it from scratch.
This applies even to short, simple, or definitional sentences — those are the easiest to copy by accident. For example, if {speaker} writes "A disciple is simply a follower of Christ," do not reuse that clause; restructure the idea, e.g. "{speaker} defines discipleship plainly — following Christ, not attaining a special status." Only quoted scripture wording may stand unchanged.
Attribute naturally by name ("{speaker} teaches…") — never "the author" — but only to what {speaker} actually said.
Neutral voice. Never use charged language ("heretical," "demonic," "apostate") in your own voice even if the source does.

Count and distinctness:

Extract one teaching passage per genuinely distinct teaching point. There is NO target number and no minimum count. When the document contains a genuine, distinct teaching point, however brief, it must still be extracted as its own passage — a short passage that makes one real teaching claim still deserves to be pulled out. But when the document contains no genuine, distinct teaching point at all — administrative content, a bare fragment or title, a throwaway remark with nothing substantive to paraphrase — the correct, expected output is an empty array. Do not manufacture a teaching passage from padding, from restating a title, or from inflating a throwaway remark just to produce output.
If two points make substantially the same claim, MERGE them into one. Near-duplicate passages are a failure.

Length: ~80–150 words each.

Output ONLY a JSON array, no preamble, no markdown fences:
[{{"proposition_index": 1, "content": "..."}}, {{"proposition_index": 2, "content": "..."}}]"""

# ── v4 prompt (2026-07-16, revised 2026-07-23) ────────────────────────────────
# Added alongside EXTRACTION_PROMPT (v3), which is unchanged and remains the
# default. Selected via extract_propositions(prompt_version="v4", speaker=...).
# Original three changes from v3:
#   1. Length: v3's length line was a bare, unexplained number ("~80-150 words
#      each") sitting directly after count/dedup language ("do not pad" /
#      "merge near-duplicates") that governs proposition COUNT, not length --
#      the adjacency plausibly caused the model to read "don't pad" as
#      governing length too. Observed result: median 40 words against a
#      stated 80-150 target. v4 gives length its own clearly separated
#      section, states explicitly what should fill the space (claim +
#      grounding + qualification), and gives a worked thin-vs-complete
#      example, matching the weight every other rule in this prompt already
#      gets.
#   2. Attribution: v3 explicitly modeled "the author teaches..." as the
#      correct form, which is why every v3 proposition uses that exact
#      framing. v4 removes it and requires the passed-in speaker name instead
#      (or no attributive frame at all).
#   3. Voice: v3's paraphrase rules are entirely about NOT copying wording;
#      nothing tells the model to keep concrete specifics once it starts
#      generalizing wording, so specifics get abstracted away along with the
#      phrasing. v4 separates "generalize the wording" from "preserve the
#      content" explicitly.
#
# 2026-07-23 revision (4th change, sentence structure): a 5-teacher/15-doc
# sample test found #2 fixed outright (zero "the author" instances) but #1
# only partially -- average landed at ~62 words against the 80-150 target,
# one document relapsing to the pre-fix ~40 word average. Manual review of
# the raw output found the likely cause: the model was writing each
# proposition as a single run-on sentence chaining claims with repeated
# "and that... and that..." constructions rather than as several well-formed
# sentences -- a chained clause hits a natural stopping point earlier than a
# real paragraph would, capping length artificially. The original "Complete"
# worked example (originally labeled "Thin") was itself a single long
# sentence plus a short second one, which plausibly reinforced the pattern
# rather than correcting it. This revision added an explicit sentence-count
# instruction (2-4 well-formed sentences, one main idea per sentence) and
# replaced that example with a three-way thin/run-on/well-formed contrast
# using the same content, so the model sees the fix is about restructuring,
# not padding.
#
# 2026-07-23 revision (5th change, terminology rename + example-leakage fix):
# two more findings from re-running the same 15-doc sample against the
# sentence-structure fix above. First, the requested experiment: the word
# "proposition" carries a strong competing technical meaning in the RAG
# literature (Chen et al. 2023, "Dense X Retrieval" -- an atomic, minimal,
# indivisible single-fact statement), heavily represented in training data
# and RAG-framework templates, and asking for "propositions" while also
# demanding an 80-150-word, voiced, multi-sentence passage plausibly fights
# that term's own gravity. All model-facing prose now says "teaching
# passage"/"passage" instead of "proposition"/"propositional." The JSON
# output key `proposition_index` is UNCHANGED -- that's a structural field
# name store_propositions() parses, not conceptual framing, and this revision
# is instruction-text-only per Alex's explicit scope. Second, an unplanned
# but directly relevant bug found while re-reading that same 15-doc run: in
# 4 of the 15 documents (3 different teachers -- Prince, Deere x2,
# Kreighbaum), the model's first output was a near-verbatim copy of the
# prompt's own concrete "Well-formed" worked example ("prayer matters more
# than preaching..."), with only the speaker's name swapped in -- fabricated
# content wrongly attributed to a real teacher, a direct four-corners
# violation. The worked examples below are now bracketed structural
# templates with no real sentence left to copy, explicitly labeled as such.
# Nothing else changed: attribution (including the optional no-frame direct
# statement), specifics-preservation, the four-corners rule, scripture-
# reference capture, no-3+-consecutive-words, neutral voice, sentence-count
# target, 80-150 word target, and JSON-only output are all untouched.
EXTRACTION_PROMPT_V4 = """\
You are writing teaching passages from a single theological document for a research tool. Each teaching passage captures one of {speaker}'s teaching points from the document, restated entirely in your own words, reading like {speaker}'s own teaching rather than a report about the document — the claim itself, the grounding {speaker} gives for it, and any qualification {speaker} attaches to it, all within that one passage.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is physically present in the document text provided. You are summarizing this one document, not teaching the topic. You may not add anything from your own knowledge — not a Bible reference, not an example, not a cross-reference, not a related verse, not background context. If it is not in the provided text, it does not exist for this task. When in doubt, leave it out.

Applying that rule:

Scripture references — capture every one the source gives, invent none it doesn't. If the document explicitly prints a reference (e.g. the text says "Hebrews 3:1" or "Mark 11:23"), and a teaching passage covers that teaching, that reference MUST appear in it. At the same time: if the speaker quotes or alludes to a verse without naming it, restate the teaching but do NOT supply the reference, even if you recognize the verse. Two equal failures to avoid: dropping a reference the speaker printed, and adding one the speaker didn't. Capture what's there; invent nothing that isn't.
Examples and illustrations: Use only the examples the document actually contains. Never introduce an illustration, story, or analogy of your own.
Claims: Represent only what the document asserts. Do not extend, infer, or theologize beyond it.
Overstatement and walk-back: if the speaker overstates a claim and then qualifies, hedges, or walks it back within the same passage, both belong in the SAME teaching passage — the overstatement and its walk-back are one teaching move, not two separate passages.

Paraphrase rules:

Full rewrite in your own words. Never reuse the speaker's distinctive phrasing or sentence structure. Never reproduce three or more consecutive words from the source (quoted scripture excepted — scripture wording may stand). If a restatement starts mirroring the original, rebuild it from scratch.
This applies even to short, simple, or definitional sentences — those are the easiest to copy by accident. Only quoted scripture wording may stand unchanged.
Neutral voice in your own narration. Never use charged language ("heretical," "demonic," "apostate") as your own assessment even if the source does.

SPEAKER ATTRIBUTION. The speaker is {speaker}. Never write "the author." Either name {speaker} naturally ("{speaker} teaches that...", "{speaker} argues...", "According to {speaker}...") or state the teaching directly with no attributive frame at all (e.g. "Prayer matters more than preaching, because..."). Both are acceptable. "The author" is never acceptable.

PRESERVE THE SPECIFICS. Generalize the WORDING, not the CONTENT. Keep the concrete detail that gives the teaching its force: names, numbers, the specific illustration or story used, the actual shape of the argument (if the speaker reasons "because X, therefore Y," keep that shape — don't flatten it to a bare abstract claim). A paraphrase that keeps only the general idea and drops the specifics has lost the thing worth retrieving, even if every word is original.

SENTENCE STRUCTURE — write 2-4 sentences, not one chained sentence. Each teaching passage should read as several distinct, well-formed sentences — never as a single sentence that chains multiple claims together with repeated "and that... and that..." constructions. If you notice yourself writing "and that" more than once in one sentence, stop and start a new sentence instead. Break at natural claim boundaries: each sentence carries one main idea (the claim, a piece of grounding, a specific detail, a qualification) rather than piling every piece onto one breathless sentence. This is not about cutting content — the same content reads as 2-4 clear sentences instead of one overloaded one.

LENGTH AND COMPLETENESS. Target 80-150 words across those 2-4 sentences. A teaching passage this length has room for three things, and each one works better as its own sentence than as a clause bolted onto the last: the claim itself, the grounding or reasoning the speaker gives for it (why they say it, what it's based on), and any qualification, exception, or walk-back the speaker attaches. A 20-30 word passage is almost always missing one of these three pieces — check what got left out before finalizing.

The pattern below is a STRUCTURAL TEMPLATE only. The bracketed parts are placeholders, not real content — never copy this template's own wording into your output; fill it with what {speaker} actually said in the source text.
  Thin (do not do this): "{speaker} teaches that [the claim], full stop — nothing else."
  Run-on (do not do this either — this is the more common failure): "{speaker} teaches that [the claim], and that [the grounding], and that [a specific detail], and that [the qualification]."
  Well-formed (do this instead): "{speaker} teaches that [the claim]. [A sentence giving the grounding or reasoning, with a specific detail from the source]. [A closing sentence carrying the qualification, exception, or the speaker's own concluding line, when the source gives one]."

Count and distinctness — fewer, fuller teaching passages is correct. Write one passage per genuinely distinct teaching point. There is NO target number and no minimum count. Do NOT increase the count to hit a length or count target — a document with few distinct points should yield few, fuller passages, not more thin ones. When a genuine, distinct teaching point is present, however brief, it must still be written as its own passage — a short passage that makes one real teaching claim still deserves to be pulled out. But when the document contains no genuine, distinct teaching point at all — administrative content, a bare fragment or title, a throwaway remark with nothing substantive to paraphrase — the correct, expected output is an empty array. Do not manufacture a teaching passage from padding, from restating a title, or from inflating a throwaway remark just to produce output.
If two points make substantially the same claim, MERGE them into one. Near-duplicate passages are a failure.

Output ONLY a JSON array of these teaching passages, no preamble, no markdown fences:
[{{"proposition_index": 1, "content": "..."}}, {{"proposition_index": 2, "content": "..."}}]"""

# ── Allowed-reference-list prompt block (PLAN.md #45 Phase 1, 2026-07-29) ──────
# Upstream constraint, complementing the downstream strip in
# _strip_ungrounded_references() -- this narrows what the model is TOLD it
# may cite in the first place; the strip below is what still catches it if
# the model ignores this block anyway. Neither replaces the other. Wired
# unconditionally into extract_propositions()'s outgoing message (see that
# function) on BOTH the v3 and v4 branches, with no parameter to opt out --
# same no-opt-out discipline as the always-on grounding strip.
#
# Known, accepted asymmetry (do not "fix" by widening the scanner here --
# out of scope for this block): this list is built from rg.find_reference_
# spans(), which only recognizes compact "Book C:V"/"Book C:V-E" citation
# forms -- the same limitation find_reference_spans() carries everywhere
# else in this codebase. A source that gives a reference only in spoken
# form ("Hebrews chapter ten, verse twenty-five") will NOT appear in this
# list, so the model is (incorrectly, from this block's narrow view) told
# not to use it. This is deliberately tolerated: the downstream arbiter in
# _strip_ungrounded_references() (citation_verifier_layers.py, Layers 1-3,
# which DO recognize spoken forms) is the authoritative backstop that will
# KEEP a genuine spoken-form reference this list omits, if the model prints
# it anyway despite this block's instruction. This block only needs to be
# right about what's confidently ALLOWED, not exhaustive about everything
# a source actually contains.
def _build_allowed_reference_block(text: str) -> str:
    """Pure function -- no I/O, no LLM call, no DB. Reuses
    rg.find_reference_spans(text) (imported, never forked) to locate every
    compact-form scripture reference actually present in `text`, dedupes by
    each span's PARSED tuple (so "Rom 8:28" and "Romans 8:28" collapse to
    one entry, keeping whichever raw spelling was seen FIRST in `text` as
    the display string), and renders a clearly delimited, explicitly CLOSED
    list section for the extraction prompt. If `text` contains zero
    recognizable references, the returned block says explicitly that the
    output must contain no scripture reference at all -- not merely that
    the list is empty."""
    spans = rg.find_reference_spans(text)
    seen: Dict[Tuple, str] = {}
    for span in spans:
        if span.parsed not in seen:
            seen[span.parsed] = span.raw

    if not seen:
        return (
            "\n\n---\n\n"
            "ALLOWED SCRIPTURE REFERENCES (CLOSED LIST):\n"
            "This document contains NO scripture references in a form this "
            "check recognizes. Your output must not include ANY scripture "
            "reference at all -- not one you recognize as real, not one you "
            "believe the document implies. If you cannot state a teaching "
            "without a reference, state it without one.\n"
        )

    lines = "\n".join("- {0}".format(raw) for raw in seen.values())
    return (
        "\n\n---\n\n"
        "ALLOWED SCRIPTURE REFERENCES (CLOSED LIST):\n"
        "The references below are the ONLY scripture references you may use "
        "in your output. This list is CLOSED: you may not use any reference "
        "beyond what is listed here, even one you recognize as a real, "
        "correct citation the document doesn't happen to state. If a "
        "teaching point has no reference in this list, state the teaching "
        "without attaching one.\n"
        "{0}\n".format(lines)
    )


# ── Groq client (lazy) ────────────────────────────────────────────────────────

_groq_client: Optional[Groq] = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


# ── Public API ────────────────────────────────────────────────────────────────

class PropositionExtractionFailed(Exception):
    """Raised by extract_propositions() when the model call itself did not
    complete -- network error, rate limit, timeout, or a response that
    doesn't parse as the expected JSON array. Deliberately distinct from a
    genuine empty result: extract_propositions() returning [] must always
    mean the model was called successfully and legitimately found nothing
    to extract, never that the call broke. process_document() catches this
    (it's still an Exception) and reports "error" -- the same signal
    already used for a storage-side failure, since both mean "nothing was
    written, safe to retry," just at different steps.
    """


class ApprovedArtifactMismatch(ValueError):
    """The reviewed proposition transport no longer matches current inputs."""


def validate_approved_propositions(
    approved: ApprovedPropositionSet,
    text: str,
    prompt_version: str,
    *,
    speaker: Optional[str] = None,
) -> List[dict]:
    """Validate one frozen review result and return its exact storage shape."""
    if not isinstance(approved, ApprovedPropositionSet):
        raise ApprovedArtifactMismatch("approved_proposition_set_required")
    try:
        approved.validate()
    except ArtifactValidationError as exc:
        raise ApprovedArtifactMismatch(str(exc)) from exc
    if prompt_version in ("v3.1", "v4") and (
        not isinstance(speaker, str) or not speaker.strip()
    ):
        raise ApprovedArtifactMismatch("approved_speaker_required")
    if approved.prompt_version != prompt_version:
        raise ApprovedArtifactMismatch("approved_prompt_version_mismatch")
    if approved.prompt_fingerprint != prompt_fingerprint(prompt_version):
        raise ApprovedArtifactMismatch("approved_prompt_fingerprint_mismatch")
    if approved.model != EXTRACTION_MODEL:
        raise ApprovedArtifactMismatch("approved_model_mismatch")
    article_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if approved.article_hash != article_hash:
        raise ApprovedArtifactMismatch("approved_article_hash_mismatch")
    return approved.as_storage_list()


def _select_prompt_template(prompt_version: str) -> str:
    """Return the raw, unformatted instruction template for prompt_version --
    the exact text before any speaker/content substitution is filled in.

    This is the ONLY function that decides which template text a given
    prompt_version sends, and both extract_propositions() and
    prompt_fingerprint() go through it -- so if a future revision ever
    branches the template on something else (content type, for instance),
    that branch only needs to be added here once, and the fingerprint
    automatically reflects it with no separate update anywhere else.
    """
    if prompt_version == "v4":
        return EXTRACTION_PROMPT_V4
    if prompt_version == "v3.1":
        return EXTRACTION_PROMPT_V3_1
    return EXTRACTION_PROMPT


def prompt_fingerprint(prompt_version: str) -> str:
    """SHA-256 hex digest of the exact instruction template text for
    prompt_version, computed fresh from the literal constant every call --
    never hand-maintained, so it cannot silently drift out of sync with the
    real wording the way the prompt_version label itself already has (the
    2026-07-23 sentence-structure and terminology-rename revisions both
    kept the label "v4" while the actual template text changed twice).
    Authoritative over the prompt_version label wherever the two disagree.
    """
    template = _select_prompt_template(prompt_version)
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def _repair_unescaped_quotes(raw: str) -> str:
    """Deterministic, schema-aware repair for the model-emitted JSON-escaping
    defect (2026-08-02): the extraction output is a JSON array of
    ``{"proposition_index": int, "content": "..."}`` objects, and the model
    intermittently writes a nested quotation inside a ``content`` value with the
    inner ``"`` unescaped -- e.g. ``... says, "My times are in your hands," and
    ...`` -- which breaks ``json.loads`` with an "Expecting ',' delimiter" error.

    This is NOT a retry loop and never re-calls the model. It walks the raw string
    once, tracking string state, and escapes every ``"`` that is an INNER content
    quote. It uses the fixed schema to decide when a ``"`` genuinely closes a
    string: a KEY string (opened right after ``{`` or ``,``) closes before ``:``;
    a VALUE string -- ``content``, always the last field of its object -- closes
    before ``}`` or ``]``. Any other in-string ``"`` is a literal inner quote and
    is escaped. Already-escaped quotes (``\\"``) and escaped backslashes are passed
    through untouched.

    Runs ONLY as a fallback after a first ``json.loads`` fails, so a well-formed
    response is never altered. If the schema assumption does not hold (e.g. the
    model reordered fields so ``content`` is not last), the repaired string simply
    fails ``json.loads`` again and the caller raises PropositionExtractionFailed --
    it never silently stores corrupt content. Correctness of the repaired content
    is additionally hand-checked against source before any reliance (this session's
    verification requirement)."""
    out = []  # type: List[str]
    i, n = 0, len(raw)
    in_string = False
    role = None  # 'key' | 'value' while in_string
    while i < n:
        c = raw[i]
        if not in_string:
            out.append(c)
            if c == '"':
                in_string = True
                j = len(out) - 2  # char before this opening quote
                while j >= 0 and out[j] in ' \t\r\n':
                    j -= 1
                prev = out[j] if j >= 0 else ''
                role = 'value' if prev == ':' else 'key'
            i += 1
            continue
        if c == '\\':  # pass an escape sequence through verbatim
            out.append(c)
            if i + 1 < n:
                out.append(raw[i + 1])
            i += 2
            continue
        if c == '"':
            k = i + 1
            while k < n and raw[k] in ' \t\r\n':
                k += 1
            nxt = raw[k] if k < n else ''
            closes = (nxt == ':') if role == 'key' else (nxt in '}]')
            if closes:
                out.append(c)
                in_string = False
                role = None
            else:
                out.append('\\"')  # literal inner quote -> escape it
            i += 1
            continue
        out.append(c)
        i += 1
    return ''.join(out)


_DEFAULT_GROUNDING_REVIEW_SINK = object()


def extract_propositions(
    text: str,
    doc_id: str = "",
    speaker: Optional[str] = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    grounding_review_sink=_DEFAULT_GROUNDING_REVIEW_SINK,
) -> List[dict]:
    """Send text to Groq and return parsed proposition list.

    prompt_version: "v3" (default) uses EXTRACTION_PROMPT unchanged -- every
    existing caller (process_document, all ingest scripts) is unaffected.
    "v3.1" uses EXTRACTION_PROMPT_V3_1 -- v3's exact wording with ONLY the
    named-teacher mechanism grafted in (see that constant's own comment) --
    and, like "v4", REQUIRES a non-empty `speaker`. "v4" uses
    EXTRACTION_PROMPT_V4 (fuller length, named-speaker attribution,
    specifics-preserving voice -- see that constant's comment for the full
    diff against v3) and also REQUIRES a non-empty `speaker`. Both raise
    ValueError rather than silently falling back to "the author"-style
    prose if one isn't given.

    Returns [] ONLY for a genuine empty result -- the model was called
    successfully and found nothing worth extracting. Raises
    PropositionExtractionFailed for everything else (network error, rate
    limit, timeout, a response that fails to parse as JSON): a failed call
    must never be indistinguishable from a legitimate empty one.

    REFERENCE GROUNDING (PLAN.md #45, 2026-07-28, ALWAYS ON): before
    returning, every scripture reference in every proposition's `content`
    is checked against `text` via reference_grounding.check_reference_
    grounded() and stripped if UNGROUNDED/UNCERTAIN -- see this module's
    top-of-file docstring "Reference-grounding fix" section for the full
    design. This runs unconditionally, with no parameter to disable it, on
    every call to this function regardless of caller -- including a caller
    that bypasses process_document() entirely, which is exactly the gap
    this fix closes. No proposition is ever dropped by this step (only
    reference substrings within a proposition's own content, never the
    proposition itself); see _strip_ungrounded_references()'s own
    docstring for the exhaustive found/grounded/stripped accounting this
    guarantees.
    """
    return extract_propositions_with_evidence(
        text,
        doc_id=doc_id,
        speaker=speaker,
        prompt_version=prompt_version,
        grounding_review_sink=grounding_review_sink,
    ).output


class ReferenceGroundingComputation(NamedTuple):
    propositions: List[dict]
    review_records: List[dict]
    n_found: int
    n_grounded: int
    n_stripped_fabricated: int
    n_stripped_uncertain: int
    n_kept_arbitration: int


class PropositionExtractionComputation(NamedTuple):
    """Provider evidence plus the exact grounded legacy extraction output."""

    output: List[dict]
    model: str
    usage: Optional[Dict[str, int]]
    cost_usd: Optional[float]
    grounding: ReferenceGroundingComputation


def compute_reference_grounding(
    propositions: List[dict],
    text: str,
    doc_id: str,
) -> ReferenceGroundingComputation:
    """Return the complete grounding result without writing review records."""
    result: List[dict] = []
    all_review_records: List[dict] = []
    total_found = 0
    total_grounded = 0
    total_fabricated = 0
    total_uncertain = 0
    total_kept_arbitration = 0

    for prop in propositions:
        content = prop.get("content", "")
        prop_index = prop.get("proposition_index")
        strip_result = _strip_ungrounded_references(content, text, doc_id, prop_index)
        total_found += strip_result.n_found
        total_grounded += strip_result.n_grounded
        total_fabricated += strip_result.n_stripped_fabricated
        total_uncertain += strip_result.n_stripped_uncertain
        total_kept_arbitration += strip_result.n_kept_arbitration
        all_review_records.extend(strip_result.review_records)

        new_prop = dict(prop)
        new_prop["content"] = strip_result.new_content
        result.append(new_prop)

    assert len(result) == len(propositions), (
        "reference-grounding step must never add or drop a proposition"
    )
    assert total_found == (
        total_grounded + total_fabricated + total_uncertain + total_kept_arbitration
    ), (
        "reference-grounding accounting failed to reconcile: found=%d != "
        "grounded=%d + fabricated=%d + uncertain=%d + kept_arbitration=%d" % (
            total_found,
            total_grounded,
            total_fabricated,
            total_uncertain,
            total_kept_arbitration,
        )
    )
    return ReferenceGroundingComputation(
        propositions=result,
        review_records=all_review_records,
        n_found=total_found,
        n_grounded=total_grounded,
        n_stripped_fabricated=total_fabricated,
        n_stripped_uncertain=total_uncertain,
        n_kept_arbitration=total_kept_arbitration,
    )


def _proposition_response_usage(response) -> Optional[Dict[str, int]]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    normalized: Dict[str, int] = {}
    for destination, candidates in (
        ("input_tokens", ("input_tokens", "prompt_tokens")),
        ("output_tokens", ("output_tokens", "completion_tokens")),
        ("total_tokens", ("total_tokens",)),
    ):
        for candidate in candidates:
            value = getattr(usage, candidate, None)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                normalized[destination] = value
                break
    return normalized or None


def _publish_reference_grounding(
    computation: ReferenceGroundingComputation,
    doc_id: str,
    review_sink=_DEFAULT_GROUNDING_REVIEW_SINK,
) -> None:
    if review_sink is _DEFAULT_GROUNDING_REVIEW_SINK:
        review_sink = _write_grounding_review_records
    if computation.review_records and review_sink is not None:
        review_sink(computation.review_records)

    logger.info(
        "REFERENCE_GROUNDING doc=%r found=%d grounded=%d stripped_fabricated=%d "
        "stripped_uncertain=%d kept_arbitration=%d",
        doc_id,
        computation.n_found,
        computation.n_grounded,
        computation.n_stripped_fabricated,
        computation.n_stripped_uncertain,
        computation.n_kept_arbitration,
    )


def extract_propositions_with_evidence(
    text: str,
    doc_id: str = "",
    speaker: Optional[str] = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    grounding_review_sink=_DEFAULT_GROUNDING_REVIEW_SINK,
) -> PropositionExtractionComputation:
    """Run the legacy extraction/grounding path and retain provider evidence."""
    if prompt_version in ("v3.1", "v4"):
        if not speaker:
            raise ValueError(
                f"prompt_version={prompt_version!r} requires a non-empty speaker name"
            )
        prompt = _select_prompt_template(prompt_version).format(speaker=speaker)
    else:
        prompt = _select_prompt_template(prompt_version)
    try:
        client = _get_groq()
        # Keep the closed reference block outside the tuned prompt literal so its
        # fingerprint and the legacy provider request remain unchanged.
        msg = f"{prompt}\n\n---\n\n{text}" + _build_allowed_reference_block(text)
        response = client.chat.completions.create(
            model=EXTRACTION_MODEL,
            messages=[{"role": "user", "content": msg}],
            temperature=0.2,
            max_tokens=8192,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = json.loads(_repair_unescaped_quotes(raw))
    except Exception as exc:
        logger.warning("PROPOSITION_EXTRACT_FAIL doc=%r error=%s", doc_id, exc)
        raise PropositionExtractionFailed(str(exc)) from exc

    grounding = compute_reference_grounding(parsed, text, doc_id)
    _publish_reference_grounding(grounding, doc_id, grounding_review_sink)
    raw_cost = getattr(response, "cost_usd", None)
    cost_usd = (
        float(raw_cost)
        if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool)
        else None
    )
    return PropositionExtractionComputation(
        output=grounding.propositions,
        model=getattr(response, "model", None) or EXTRACTION_MODEL,
        usage=_proposition_response_usage(response),
        cost_usd=cost_usd,
        grounding=grounding,
    )


def _apply_reference_grounding(
    propositions: List[dict],
    text: str,
    doc_id: str,
    *,
    review_sink=_DEFAULT_GROUNDING_REVIEW_SINK,
) -> List[dict]:
    """Applies the always-on reference-grounding strip (see
    extract_propositions()'s own docstring) to every proposition in
    `propositions`, against source text `text`. Runs OUTSIDE
    extract_propositions()'s own try/except that raises
    PropositionExtractionFailed -- a bug here must never be reported as a
    network/parse failure of the model call, which already completed
    successfully by the time this runs.

    Returns a NEW list, same length and same proposition_index values as
    `propositions` -- only `content` is ever rewritten, and only to remove
    stripped reference spans; no proposition is ever added or dropped here.
    Asserts the exhaustive accounting (every reference found lands in
    exactly one of grounded / stripped-fabricated / stripped-uncertain /
    kept-via-arbitration -- PLAN.md #45 Phase 1, 2026-07-29 arbitration
    build added the fourth bucket; see _strip_ungrounded_references()'s own
    docstring for what each one means) before returning."""
    computation = compute_reference_grounding(propositions, text, doc_id)
    _publish_reference_grounding(computation, doc_id, review_sink)
    return computation.propositions


def get_license_status(conn, source_id: str) -> Optional[str]:
    """Return license_status for source_id, or None if not found."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT license_status FROM sources WHERE id = %s",
            (source_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


class PropositionPayload(NamedTuple):
    """Immutable DB-ready proposition computation shared by preview/storage."""

    content: str
    proposition_index: int
    embedding: Tuple[float, ...]
    prompt_version: str
    prompt_fingerprint: str
    model: str
    embedding_model: str


class PropositionPayloadContext(NamedTuple):
    """Derived provenance shared by bulk preview and interleaved storage."""

    prompt_version: str
    prompt_fingerprint: str
    model: str
    embedding_model: str


def build_proposition_payload_context(
    *,
    prompt_version: str,
    model: str = EXTRACTION_MODEL,
    embedding_model: str = "text-embedding-3-small",
) -> PropositionPayloadContext:
    return PropositionPayloadContext(
        prompt_version=prompt_version,
        prompt_fingerprint=prompt_fingerprint(prompt_version),
        model=model,
        embedding_model=embedding_model,
    )


def build_proposition_payload_item(
    content: str,
    proposition_index: int,
    embedding: List[float],
    *,
    context: PropositionPayloadContext,
) -> PropositionPayload:
    """Build one canonical item from already-snapshotted source values."""
    return PropositionPayload(
        content=content,
        proposition_index=proposition_index,
        embedding=tuple(float(value) for value in embedding),
        prompt_version=context.prompt_version,
        prompt_fingerprint=context.prompt_fingerprint,
        model=context.model,
        embedding_model=context.embedding_model,
    )


def build_proposition_payload(
    propositions: List[dict],
    embeddings: List[List[float]],
    *,
    prompt_version: str,
    model: str = EXTRACTION_MODEL,
    embedding_model: str = "text-embedding-3-small",
) -> Tuple[PropositionPayload, ...]:
    """Build the one ordered, immutable proposition payload consumers use."""
    if len(propositions) != len(embeddings):
        raise ValueError("proposition embedding count mismatch")
    context = build_proposition_payload_context(
        prompt_version=prompt_version,
        model=model,
        embedding_model=embedding_model,
    )
    return tuple(
        build_proposition_payload_item(
            proposition["content"],
            proposition["proposition_index"],
            embedding,
            context=context,
        )
        for proposition, embedding in zip(propositions, embeddings)
    )


def store_propositions(
    conn,
    document_id: str,
    propositions: List[dict],
    embed_fn: Callable[[str], List[float]],
    prompt_version: str,
    chunk_ids: Optional[List[str]] = None,
    clear_existing: bool = True,
) -> int:
    """Clear existing propositions for document_id, then embed and insert new ones.

    clear_existing (book-chapter build, additive, trailing
    keyword-only-in-practice parameter, default True): when True --
    every existing caller, since this is the default -- the
    `DELETE FROM propositions WHERE document_id = %s` below remains the
    first database statement. Each proposition is then embedded and inserted
    before the next proposition is embedded, preserving the legacy provider/
    persistence side-effect order. When False, that DELETE is skipped entirely;
    everything else (the interleaved embed/INSERT loop, the proposition_chunks
    cartesian-product insert, and the final commit) runs unchanged. This exists for
    _extract_and_store_book_chapters() below,
    which issues its OWN single, document-level DELETE once before its
    chapter loop (never once per chapter) and then calls this function once
    per chapter with clear_existing=False, so a later chapter's store call
    never wipes an earlier chapter's just-stored rows for the same
    document_id.

    prompt_version (bypass-proofing Phase 4, PLAN.md #45, 2026-07-29,
    REQUIRED -- no default): an unstamped write is now IMPOSSIBLE, not
    merely discouraged. Before this phase, prompt_version/fingerprint/model
    were all optional-with-None-default -- a caller could omit all three
    and land a silently-NULL-provenance row (see CLAUDE.md Invariant 10 and
    the Landmines section: this is exactly how every live proposition row
    ended up with NULL provenance, via the now-deleted
    sample_v4_propositions_2026-07-23.py, which called this function with 4
    bare positional args and nothing else). Omitting prompt_version now is a
    Python TypeError at call-binding time -- before a single line of this
    function's body runs, before the DELETE, before any DB call at all.

    fingerprint and model are NO LONGER caller-suppliable at all -- they
    were removed as parameters entirely. This function now derives them
    itself, internally, from prompt_version every single call (see just
    below), the same way process_document() always used to compute them
    before passing them in. This closes a narrower but real gap the old
    signature still had even when a caller DID pass all three: nothing
    stopped a caller from passing a prompt_version of "v3" alongside a
    fingerprint or model string that didn't actually match it (a typo, a
    stale copy-paste, an honest mismake) -- the two were independently
    caller-supplied and could silently disagree. Deriving them here from the
    single stated prompt_version makes that kind of mismatch structurally
    unrepresentable: there is only one value in the caller's control
    (prompt_version), and fingerprint/model are always whatever that value
    actually implies, every time, with no separate slot for a caller to get
    wrong. fingerprint remains the authoritative field over prompt_version
    when investigating a stored row (see prompt_fingerprint()'s docstring
    for why) -- that authority relationship is unchanged, only how
    fingerprint gets produced has moved.

    chunk_ids (bypass-proofing Phase 2b, PLAN.md #45, 2026-07-29, optional,
    default None): the full current chunk-id set for document_id (as
    determined by the caller -- see shared_ingest.ingest_document()'s own
    single-query fetch). When truthy, one (proposition_id, chunk_id) pair
    is recorded in proposition_chunks for EVERY chunk id in this list,
    against EVERY proposition stored in this call -- the cartesian product,
    not a per-chunk assignment. This is the honest precision available:
    extraction runs over the document's full reconstructed text, not a
    single chunk, so a stored proposition's only truthful back-link is
    "every chunk that made up the text this extraction call actually saw."
    When chunk_ids is None or empty (the default -- every caller that
    predates this parameter), zero proposition_chunks rows are written and
    behavior is otherwise identical to before this parameter existed. The
    proposition ids used are the REAL ids generated inline below, not
    reconstructed after the fact. No existing pre-Phase-2b row is ever
    touched, backfilled, or reinterpreted by this addition.

    The existing `DELETE FROM propositions WHERE document_id = %s` above
    needs no matching `DELETE FROM proposition_chunks` -- migration 074's
    `proposition_id uuid NOT NULL REFERENCES propositions (id) ON DELETE
    CASCADE` already removes any stale back-link rows automatically the
    instant their parent proposition row is deleted.

    Commits the transaction. Returns count inserted.
    fts column is GENERATED ALWAYS AS STORED — not included in INSERT.
    """
    # Derive prompt provenance before the first database statement, matching
    # the legacy sequencing. Canonical item construction stays shared with the
    # preview, but embedding remains interleaved with each INSERT below.
    payload_context = build_proposition_payload_context(
        prompt_version=prompt_version,
    )

    with conn.cursor() as cur:
        if clear_existing:
            cur.execute(
                "DELETE FROM propositions WHERE document_id = %s",
                (document_id,),
            )

        inserted = 0
        stored_prop_ids: List[str] = []
        for raw_proposition in propositions:
            content = raw_proposition["content"]
            proposition_index = raw_proposition["proposition_index"]
            embedding = embed_fn(content)
            proposition = build_proposition_payload_item(
                content,
                proposition_index,
                embedding,
                context=payload_context,
            )
            embedding_str = "[" + ",".join(
                str(value) for value in proposition.embedding
            ) + "]"
            prop_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO propositions
                       (id, document_id, content, embedding, proposition_index,
                        prompt_version, prompt_fingerprint, model)
                   VALUES (%s, %s, %s, %s::vector, %s, %s, %s, %s)""",
                (
                    prop_id,
                    document_id,
                    proposition.content,
                    embedding_str,
                    proposition.proposition_index,
                    proposition.prompt_version,
                    proposition.prompt_fingerprint,
                    proposition.model,
                ),
            )
            stored_prop_ids.append(prop_id)
            inserted += 1

        if chunk_ids:
            # Cartesian product: every proposition stored in THIS call
            # links to every chunk id THIS call was given -- see the
            # chunk_ids parameter docstring above for why that's the
            # honest precision, not an invented per-chunk assignment.
            # Bulk execute_values(), mirroring shared_ingest._insert_
            # chunks()'s own bulk-insert style -- avoids an N-times-M
            # per-row round trip at book-scale documents.
            pairs = [
                (prop_id, chunk_id)
                for prop_id in stored_prop_ids
                for chunk_id in chunk_ids
            ]
            if pairs:
                execute_values(
                    cur,
                    "INSERT INTO proposition_chunks (proposition_id, chunk_id) VALUES %s",
                    pairs,
                    template="(%s, %s)",
                )

    conn.commit()
    return inserted


# Precept Austin is locked OUT of the propositions layer entirely (decided
# 2026-07-02): its existing excerpts are near-verbatim reorderings of the
# source text, not paraphrases, and fresh Groq extraction was explicitly
# declined. Enforced here by source_id so no caller (including future
# backfills) can wire it in by accident.
PRECEPT_AUSTIN_SOURCE_ID = "698e0596-a9c6-4890-958d-9199f1b8f762"


# Real corpus evidence (2026-07-29, live-queried, 857 eligible documents): the
# absolute minimum word count of any currently-eligible document is 61 words
# (Leonard Ravenhill, "The Power of the Second Blessing in Faith"), and that
# document legitimately produced 1 real teaching passage. Zero documents in
# the corpus fall under 61, 50, 30, or 20 words. This floor sits comfortably
# below that observed minimum (11-word margin) -- it has ZERO effect on any
# real document that exists today; it exists purely as forward-looking
# protection against a genuinely degenerate future input (a scraping
# artifact, a title-only stub, a near-empty transcript), not as a change to
# any observed corpus behavior.
MIN_SUBSTANTIVE_WORD_COUNT = 50

# ── Front/back-matter detection (book-chapter build, correction pass) ─────────
# CORRECTION TO A PRIOR MISCLASSIFICATION: an earlier report described the
# 543-word span split_book_into_chapters() detects as "preface_pre_boundary"
# content for The True Vine as "the preface" and treated it as fine to leave
# as-is. That was WRONG. Re-investigation found that span is actually CCEL
# bibliographic metadata (Author(s)/Title/Publisher/Description/Subjects
# fields) immediately followed by a Table of Contents -- labeled with the
# BOOK'S OWN TITLE (via _label_from_context(), which just reads the first
# non-blank line), not "Preface" at all. The REAL Preface is a SEPARATE,
# later, genuinely-labeled 196-word span ("Preface\nPreface\nPREFACE\n...")
# containing real Andrew Murray prose ("I have felt drawn to try to write
# what young Christians might easily apprehend...") -- it produced 4 real
# propositions in the original live-proof run and MUST stay classified as
# content. These two spans are easy to conflate (both are near the front of
# the book, both are front-matter-ADJACENT) and the whole design below
# depends on telling them apart correctly -- a label-keyword check ALONE
# cannot do it, since the CCEL-metadata span isn't labeled with any
# front-matter keyword at all (it's labeled with the book's own title); only
# its CONTENT SHAPE (CCEL field lines, then a dense table of contents)
# reveals what it actually is. This is exactly why is_front_back_matter()
# below has two independent signals (label AND shape), not just one.
#
# Thresholds below were empirically validated during the planning step
# against 10 real public-domain books already in the corpus (this build's
# own regression tests re-confirm a subset directly, read-only, against live
# chunk data -- see test_propositions_book_chapters.py). A previously-tried
# generic "Capitalized Word Then Colon" shape heuristic was explicitly
# REJECTED during planning: it false-positived on real long chapters (e.g.
# Absolute Surrender's "The Fruit of the Spirit is Love" and "Kept by the
# Power of God" chapters, Bounds' "8. Examples of Praying Men") -- do not
# reintroduce anything like it.
FRONT_BACK_MATTER_DIGIT_RATIO = 0.10      # real content spans measured <=0.043; index/locator spans measured 0.10-0.95
CCEL_METADATA_FIELD_MIN = 2               # real content spans measured 0-1 distinct CCEL fields; metadata spans measured >=3
FRONT_BACK_MATTER_MIN_SHAPE_WORDS = 30    # below this the digit-ratio signal is noise; tiny spans already fall to the existing thin-check

_MATTER_LABEL_EXACT = {
    "title page", "contents", "table of contents", "copyright", "colophon",
    "bibliography", "acknowledgments", "acknowledgements", "dedication",
    "errata", "half title", "indexes",
}
_MATTER_LABEL_PREFIX = (
    "index", "about the author", "about this book", "about the electronic",
    "subject index", "scripture index",
)
# Editorial-apparatus labels (fix (a)) -- EXACT normalized match, deliberately
# NOT a prefix match like _MATTER_LABEL_PREFIX above: a prefix match here
# would collide with a real chapter titled e.g. "The Biography of Faith"
# (starts with "biograph..." if stemmed loosely, but is NOT the editorial
# "Biographical Sketch"/"Biographical Note" apparatus this set targets).
_MATTER_LABEL_APPARATUS = {
    "editor's note", "editors note", "editorial note",
    "publisher's note", "publishers note",
    "translator's note", "translators note",
    "biographical sketch", "biographical note",
}
# PROTECTED labels short-circuit is_front_back_matter() to (False, "")
# BEFORE any shape check ever runs -- see that function's own docstring for
# why this ordering is the false-positive guard the whole design leans on
# (the real 196-word Preface's own content shape is never even examined).
_MATTER_LABEL_PROTECT = {
    "preface", "introduction", "foreword", "prologue", "epilogue",
    "afterword", "conclusion", "appendix",
}
_CCEL_FIELD_RE = re.compile(
    r'(?im)^\s*(author\(s\)|title|publisher|description|subjects?|'
    r'language|rights|source|lc call no|lc subjects)\s*:'
)

_LEADING_MATTER_NUMBER_RE = re.compile(r'^(?:\d+|[ivxlcdm]+)[.):\-]?\s+', re.IGNORECASE)
_TRAILING_CONTINUATION_RE = re.compile(r'\s*\(untitled continuation\)\s*$')
_ROMAN_NUMERAL_TOKEN_RE = re.compile(r'^[ivxlcdm]+$', re.IGNORECASE)
_LOCATOR_TOKEN_RE = re.compile(r'^\d+:\d+(?:-\d+)?$')


def _normalize_matter_label(label: str) -> str:
    """Lowercases `label`; strips a leading number/roman-numeral +
    separator if present (e.g. "8. Examples of Praying Men" ->
    "examples of praying men", so numbered-chapter conventions from other
    books don't defeat the keyword checks below); strips a trailing
    "(untitled continuation)"-style suffix if present (the exact suffix
    split_book_into_chapters()'s own oversized-stretch fallback appends,
    e.g. "Some Chapter (untitled continuation)" -> "some chapter", so a
    size-fallback continuation of a real chapter is judged by the SAME
    label as its parent, never treated as a separate, unlabeled span);
    collapses internal whitespace; strips. The leading-number strip
    requires a roman-numeral candidate to be a WHOLE token composed only of
    i/v/x/l/c/d/m characters followed by a real separator -- this is what
    keeps it from ever matching an ordinary word (e.g. "Indexes" begins
    with "i" but "n" immediately follows with no separator in between, so
    nothing is stripped)."""
    s = label.lower()
    s = _LEADING_MATTER_NUMBER_RE.sub("", s)
    s = _TRAILING_CONTINUATION_RE.sub("", s)
    s = " ".join(s.split())
    return s.strip()


def _distinct_ccel_fields(text: str) -> set:
    """The set of distinct CCEL bibliographic field names (lowercased)
    _CCEL_FIELD_RE matches at the start of a line in `text` -- e.g. a CCEL
    header block containing "Author(s): Murray, Andrew\\nPublisher: ...\\n
    Description: ...\\nSubjects: The Bible" yields {"author(s)",
    "publisher", "description", "subjects"}, size 4. A real teaching
    chapter essentially never opens multiple lines with these exact
    bibliographic field labels, which is what makes this such a strong,
    low-noise signal for "this span is a CCEL metadata block", independent
    of what it happens to be labeled."""
    return {m.group(1).lower() for m in _CCEL_FIELD_RE.finditer(text)}


# ── Roman-numeral round-trip validation (fix (b) dependency) ────────────────
# Shared, single source of truth for "is this string a genuinely valid
# canonical roman numeral" -- used by _digit_token_ratio()'s tightened
# roman-numeral arm below. (Also reused, unforked, by a separate
# single-occurrence numeral/roman-numeral chapter-heading detector that
# lives elsewhere in this module's own history but is not part of this
# commit.)
_ROMAN_NUMERAL_UNIT_VALUES = [
    ("M", 1000), ("CM", 900), ("D", 500), ("CD", 400),
    ("C", 100), ("XC", 90), ("L", 50), ("XL", 40),
    ("X", 10), ("IX", 9), ("V", 5), ("IV", 4), ("I", 1),
]


def _int_to_roman(n: int) -> str:
    """Standard greedy roman-numeral renderer -- used only as the second
    half of _roman_to_int()'s own round-trip validation below, never
    called directly by any other function in this module."""
    parts: List[str] = []
    for symbol, value in _ROMAN_NUMERAL_UNIT_VALUES:
        while n >= value:
            parts.append(symbol)
            n -= value
    return "".join(parts)


def _roman_to_int(s: str) -> Optional[int]:
    """Converts an UPPERCASE roman-numeral string to its integer value,
    correctly handling subtractive notation (IV=4, IX=9, XL=40, XC=90,
    CD=400, CM=900). Returns None if `s` is not a VALID CANONICAL roman
    numeral -- not merely "composed of roman-numeral characters". Validated
    by ROUND-TRIP: parse s -> int via the standard left-to-right
    subtractive-pair algorithm, then re-render that int back to ITS OWN
    canonical roman-numeral string via _int_to_roman() and require an EXACT
    match against `s`. This single check simultaneously rejects both
    "IIII" (parses to 4 under the algorithm, but 4's own canonical form is
    "IV", not "IIII" -- mismatch) and "VX" (parses to 5 under the
    algorithm -- V=5 < X=10 so subtracted, net 10-5=5 -- but 5's canonical
    form is "V", not "VX" -- mismatch), with no separate hand-written rule
    needed for either malformed shape specifically."""
    if not s or not all(ch in "IVXLCDM" for ch in s):
        return None
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for i, ch in enumerate(s):
        v = values[ch]
        if i + 1 < len(s) and v < values[s[i + 1]]:
            total -= v
        else:
            total += v
    if total <= 0 or total > 3999:
        return None
    if _int_to_roman(total) != s:
        return None
    return total


def _digit_token_ratio(text: str) -> float:
    """Fraction of `text`'s whitespace-split tokens that are a bare
    integer (a page number), a roman numeral (a page-footer convention
    this corpus's own front matter uses -- e.g. "ii", "iii"), or a
    verse/page locator shape like "15:1" or "92:13-14" (the dominant token
    shape inside a scripture index's own body, per the real True Vine
    "Index of Scripture References"/"Index of Scripture Commentary" spans
    this was checked against). A token's own trailing comma/period/
    semicolon is tolerated (stripped before testing) since real index
    listings often separate locators that way. Returns 0.0 if `text` has
    no tokens at all -- never divides by zero.

    ROMAN-NUMERAL ARM, tightened (bug fix): a token counts as roman-
    numeral-shaped ONLY if it is (a) lowercase IN THE ORIGINAL TEXT -- this
    is what excludes the capitalized first-person pronoun "I" (a genuine
    corpus bug: Wesley's Defenders measured 22 of 24 "digit" tokens as the
    pronoun "I" before this fix) -- AND (b) round-trips through the
    existing _roman_to_int() as a genuinely VALID canonical roman numeral,
    not merely a string built from i/v/x/l/c/d/m characters -- this is
    what excludes ordinary lowercase English words that happen to be
    spelled entirely from that letter set (e.g. "did", "mid", "civil" --
    another real corpus bug: Wesley Discusses Old Sermons had "did" alone
    match 4 times). _roman_to_int() itself is reused, never forked --
    single source of truth for what counts as a valid roman numeral
    anywhere in this module. A single-character token (e.g. a bare "i" or
    "x") is excluded outright (len(stripped) >= 2 required) -- a one-letter
    "roman numeral" is exactly the shape most likely to just be an
    ordinary short word or a stray character, and no real corpus example
    this fix was checked against needed single-character roman-numeral
    tokens to be counted for the digit-locator signal to still work."""
    tokens = text.split()
    if not tokens:
        return 0.0
    n_digitish = 0
    for tok in tokens:
        stripped = tok.strip(",.;")
        if not stripped:
            continue
        if stripped.isdigit():
            n_digitish += 1
        elif (
            len(stripped) >= 2 and stripped == stripped.lower()
            and _roman_to_int(stripped.upper()) is not None
        ):
            n_digitish += 1
        elif _LOCATOR_TOKEN_RE.match(stripped):
            n_digitish += 1
    return n_digitish / len(tokens)


# ── Third-party byline detector (fix (a)) ──────────────────────────────────
# Catches a span like a real Wesley journal edition's own "INTRODUCTION" or
# "AN APPRECIATION OF JOHN WESLEY'S JOURNAL" -- neither is label-matched
# (neither is in _MATTER_LABEL_EXACT/_MATTER_LABEL_PREFIX, and both would be
# PROTECTED anyway if they were, e.g. "Introduction"), and neither is
# CCEL-metadata- or digit-locator-shaped -- but both are written by someone
# OTHER than the book's own credited author, exactly the class of span this
# corpus's own "citable requires a real attributable name" discipline
# (CLAUDE.md Invariant 7) already cares about getting right upstream of
# extraction: attributing a third party's own words to the book's speaker
# would be a real misattribution, not just noise.
_BYLINE_RE = re.compile(r'(?i)^\s*by\s+(.+?)\s*$')
_NAME_HONORIFICS = {
    "the", "rev", "reverend", "dr", "mr", "mrs", "ms", "sir", "prof",
    "professor", "hon", "honorable", "st", "saint", "esq", "jr", "sr",
    "kings", "king", "counsel",
}


def _normalize_person_name(s: str) -> set:
    """Tokenizes a person-name-shaped string into a set of its own
    significant name tokens: lowercased, curly apostrophes normalized to
    straight ones FIRST (reusing the module's own _CURLY_QUOTE_MAP -- not
    forked), then apostrophes/commas/periods stripped to spaces, split on
    whitespace, and honorifics/titles/short filler tokens (see
    _NAME_HONORIFICS, and a bare len(t) < 3 floor that also drops middle
    initials) dropped. E.g. "Augustine Birrell, King's Counsel" ->
    {"augustine", "birrell"} (both "king's" and "counsel" are in
    _NAME_HONORIFICS). Returns an empty set for an empty/whitespace-only
    input -- callers treat an empty set as "no name to compare"."""
    s = "".join(_CURLY_QUOTE_MAP.get(c, c) for c in s).lower()
    s = re.sub(r"[.,'’]", " ", s)
    return {t for t in s.split() if len(t) >= 3 and t not in _NAME_HONORIFICS}


def _has_third_party_byline(text: str, author: Optional[str]) -> bool:
    """Scans the first 8 non-blank lines of `text` for a short,
    byline-shaped line ("By <name>") crediting someone whose own name
    tokens share NOTHING with `author`'s own name tokens. Returns False
    (conservative default) if `author` is falsy/empty (nothing to compare
    against -- this is what makes the `author` parameter's own None
    default fully inert, per is_front_back_matter()'s own contract), or if
    no byline-shaped line is found at all, or if a byline IS found but
    credits the SAME author (or shares at least one name token with them --
    e.g. a middle name or a variant spelling still counts as a match,
    erring toward NOT flagging a real match as a false third party).

    The <=12-word cap on a candidate line (before even trying the byline
    regex) is what rejects an incidental "by" appearing INSIDE a long
    prose sentence (a real byline is always short) rather than a genuine
    credit line -- this mirrors the same "a real heading/byline is short"
    discipline the numeral-heading detector's own discriminator 1 already
    uses elsewhere in this module, applied here to a different shape."""
    author_toks = _normalize_person_name(author or "")
    if not author_toks:
        return False
    for line in [l.strip() for l in text.split("\n") if l.strip()][:8]:
        if len(line.split()) > 12:
            continue
        m = _BYLINE_RE.match(line)
        if not m:
            continue
        credited = _normalize_person_name(m.group(1))
        if credited and not (author_toks & credited):
            return True
    return False


def _label_is_front_back_matter(label: str) -> bool:
    """Label-only front/back-matter signal. A PROTECTED label
    (preface/introduction/foreword/prologue/epilogue/afterword/
    conclusion/appendix) returns False immediately -- this check runs
    BEFORE the exact/prefix keyword checks below, so a book whose real
    front-matter convention happens to literally use one of those words
    (e.g. a book with a real "Introduction" chapter) is never label-matched
    as matter. Otherwise: an EXACT normalized match against
    _MATTER_LABEL_EXACT, or a first-word match against {"index", "indexes",
    "contents"} (covers "Index of Scripture References" etc., whose full
    normalized label isn't itself in the exact set but starts with a
    matter-indicating word), or a normalized-label prefix match against
    _MATTER_LABEL_PREFIX (covers "About the Author", "Subject Index", "About
    the Electronic Edition"-shaped labels) all return True."""
    n = _normalize_matter_label(label)
    first = n.split()[0] if n else ""
    if first in _MATTER_LABEL_PROTECT:
        return False
    if n in _MATTER_LABEL_EXACT or first in {"index", "indexes", "contents"}:
        return True
    return any(n.startswith(p) for p in _MATTER_LABEL_PREFIX)


def _shape_is_front_back_matter(text: str) -> bool:
    """Content-SHAPE front/back-matter signal, used when the label alone
    doesn't already say so -- this is what catches a span like The True
    Vine's own 543-word CCEL-metadata-plus-Table-of-Contents block, which
    is labeled with the book's own title (via _label_from_context()), not
    any matter keyword. Two independent shape tests, either one sufficient:
    (1) CCEL_METADATA_FIELD_MIN or more distinct CCEL bibliographic field
    lines (see _distinct_ccel_fields()); (2) at least
    FRONT_BACK_MATTER_MIN_SHAPE_WORDS words AND a digit/roman-numeral/
    locator token ratio (see _digit_token_ratio()) at or above
    FRONT_BACK_MATTER_DIGIT_RATIO -- the word-count floor exists because
    the digit-ratio signal is noise on a tiny span (a 5-word fragment that
    happens to be "1 2 3" is not meaningfully "shaped like an index"; a
    genuinely tiny span already falls to the pre-existing
    MIN_SUBSTANTIVE_WORD_COUNT thin-check regardless of this function)."""
    if len(_distinct_ccel_fields(text)) >= CCEL_METADATA_FIELD_MIN:
        return True
    if (
        len(text.split()) >= FRONT_BACK_MATTER_MIN_SHAPE_WORDS
        and _digit_token_ratio(text) >= FRONT_BACK_MATTER_DIGIT_RATIO
    ):
        return True
    return False


def is_front_back_matter(
    label: str, text: str, author: Optional[str] = None,
) -> Tuple[bool, str]:
    """Is (label, text) -- one chapter/sub-unit's own parent_label and
    text, as produced by split_book_into_chapters()/
    _apply_word_ceiling_fallback() -- front or back matter that should
    never reach extract_propositions() at all? Returns (is_matter,
    reason), reason one of "third_party_byline" (fix (a), checked FIRST --
    see below), "editorial_apparatus" (fix (a), an exact-match editorial-
    apparatus label), "label" (a matter-indicating label), "ccel_metadata"
    (>=CCEL_METADATA_FIELD_MIN distinct CCEL field lines), "digit_locator"
    (word-count + digit-ratio shape), or "" (not matter).

    `author` (fix (a), optional, default None): the book's own credited
    speaker/author name, used ONLY for the third-party-byline check below.
    None (the default) makes that check unconditionally inert -- see
    _has_third_party_byline()'s own docstring -- so every existing caller
    that doesn't pass it (including the OTHER call site inside
    detect_book_chapters()'s own R-computation, deliberately left as-is)
    is byte-identical to this function's behavior before fix (a) existed.

    THIRD-PARTY-BYLINE CHECK RUNS FIRST, BEFORE the protected-label
    short-circuit below -- deliberately, so a PROTECTED label like
    "Introduction" credited to someone other than the book's own author
    (a real corpus example: a Wesley journal edition's own third-party
    "INTRODUCTION", written by someone else entirely) still gets caught,
    rather than being protected from ever being checked at all. This is
    the one case where a protected label does NOT win outright -- see
    _has_third_party_byline()'s own docstring for why this is safe (it
    requires an actual, name-mismatched "By <name>" line, not merely
    absence of a name match, so a real "Introduction" written by the
    book's own author, or with no byline printed at all, is unaffected).

    EDITORIAL-APPARATUS LABEL CHECK runs second, via an EXACT normalized
    match against _MATTER_LABEL_APPARATUS (not a prefix match, unlike
    _MATTER_LABEL_PREFIX -- see that set's own comment for why prefix
    matching would be unsafe here).

    Only AFTER both of the above does the ORIGINAL, unchanged logic run: a
    PROTECTED label (see _MATTER_LABEL_PROTECT) returns (False, "")
    without ever examining shape at all -- this is the false-positive
    guard the whole design depends on: The True Vine's real 196-word
    Preface span (label exactly "Preface") short-circuits here and is
    NEVER run through _shape_is_front_back_matter(), so it does not matter
    whether that span's own prose happens to contain a few numbers.

    IMPLEMENTATION NOTE (bug caught by this build's own regression test,
    fixed here rather than silently worked around): the planning step's own
    given pseudocode for this function was `if _label_is_front_back_matter
    (label): return True, "label"` followed unconditionally by the shape
    check -- but _label_is_front_back_matter() returning False for a
    protected label only means the LABEL signal didn't fire; nothing in
    that pseudocode actually stops execution from falling through to
    _shape_is_front_back_matter() afterward for that same protected label.
    That directly contradicts this same docstring's own stated guarantee
    ("ALWAYS returns (False, '') without ever examining shape") -- and a
    synthetic regression test built specifically to prove the guarantee
    (a "Preface"-labeled span with deliberately metadata-shaped content)
    caught the contradiction immediately: it returned (True,
    "ccel_metadata") instead of (False, ""). Fixed by checking protection
    explicitly, HERE, before either signal runs -- see the first three
    lines of this function's body below, which duplicate
    _label_is_front_back_matter()'s own normalize+first-word logic
    (cheap, pure string ops) rather than changing that helper's own `->
    bool` signature (kept exactly as specified) to smuggle a third state
    through it.

    Absent a label match, shape is checked. Absent BOTH a label match and a
    shape match, the default is (False, "") -- an ambiguous or genuinely
    novel front-matter convention this design doesn't recognize is treated
    as CONTENT, never silently dropped; a false negative here just means an
    extraction call runs on a section that turns out administrative, which
    extract_propositions()'s own "empty array is a valid, expected result"
    instruction already handles gracefully. A false POSITIVE (silently
    losing real content) is the failure mode this function is built to
    avoid, not a false negative."""
    if _has_third_party_byline(text, author):
        return True, "third_party_byline"
    if _normalize_matter_label(label) in _MATTER_LABEL_APPARATUS:
        return True, "editorial_apparatus"
    n = _normalize_matter_label(label)
    first = n.split()[0] if n else ""
    if first in _MATTER_LABEL_PROTECT:
        return False, ""
    if _label_is_front_back_matter(label):
        return True, "label"
    if _shape_is_front_back_matter(text):
        if len(_distinct_ccel_fields(text)) >= CCEL_METADATA_FIELD_MIN:
            return True, "ccel_metadata"
        return True, "digit_locator"
    return False, ""


# Closeness-check gate RETIRED -- project owner decision, 2026-07-29:
# near-verbatim reuse of a teacher's own wording is an accepted risk, not
# something to review or block. This bare True, with no per-call override
# (no parameter, no env var, no kwarg), forces process_document()'s
# `if name_pattern is None:` branch below to fire unconditionally --
# nothing any caller supplies can reactivate the gate. Deliberately not a
# deletion: the lazy `import closeness_check`, the classify() loop, and the
# review-file write immediately below in process_document() all stay
# exactly as they were, just permanently unreachable. To reverse this
# decision later, flip this one flag back to False -- nothing else to
# undo. See this module's top-of-file docstring, "Closeness-check gate
# RETIRED", for the full context.
CLOSENESS_CHECK_RETIRED = True


def process_document(
    conn,
    document_id: str,
    source_id: str,
    text: str,
    embed_fn: Callable[[str], List[float]],
    name_pattern: Optional[re.Pattern] = None,
    verse_lookup: Optional[Dict[str, str]] = None,
    vocab_matcher: Optional[object] = None,
    chunk_ids: Optional[List[str]] = None,
    speaker: Optional[str] = None,
    prompt_version: Optional[str] = None,
    approved_propositions: Optional[ApprovedPropositionSet] = None,
) -> str:
    """Top-level entry point for ingest scripts.

    speaker / prompt_version (named-teacher fix, 2026-07-30, both default
    None): OPTIONAL, same discipline as every other parameter below --
    byte-identical to before this change when omitted. `prompt_version`
    None means "use DEFAULT_PROMPT_VERSION" ("v3", unchanged) exactly as
    before this parameter existed; a caller opts into the naming fix by
    passing prompt_version="v3.1" (isolated fix only) or "v4" (the fuller
    bundled retune) AND a non-empty `speaker` -- extract_propositions()
    raises ValueError if a speaker-requiring version is selected without
    one, caught by this function's own outer except like any other
    extraction failure (never raises past this function). No caller is
    forced to supply either: every existing call site that passes neither
    continues to get "v3", exactly as always.

    name_pattern / verse_lookup (PLAN.md #45 Phase 5, both default None):
    OPTIONAL closeness-check gate, OFF unless name_pattern is supplied --
    see this module's top-of-file docstring for the full design. No real
    ingest path passes these yet; every existing caller's behavior is
    unchanged.

    RETIRED (project owner decision, 2026-07-29 -- see CLOSENESS_CHECK_RETIRED
    above and this module's top-of-file docstring, "Closeness-check gate
    RETIRED"): the gate below is now permanently disabled regardless of
    what's supplied for name_pattern/verse_lookup/vocab_matcher -- every
    caller now gets the "stored:{n}" shape below; "stored:{n}:flagged:{m}"
    can no longer be produced. Not a deletion -- see that constant's own
    comment for how to reverse this.

    vocab_matcher (PLAN.md #45 Phase 6, default None): OPTIONAL, inert
    unless the gate is already active. Typed as Optional[object] rather
    than closeness_check.VocabMatcher specifically, because this module
    imports closeness_check LAZILY (only inside the gate-active branch
    below) -- a module-level type import would defeat that lazy-import
    contract for every off caller. Threads straight through to the
    classify() call below exactly like name_pattern/verse_lookup; not
    supplying it (the default) is byte-identical to this parameter not
    existing at all.

    chunk_ids (bypass-proofing Phase 2b, PLAN.md #45, 2026-07-29, default
    None): plain optional enrichment parameter, not a safety gate -- no
    lazy-import coupling, no enforcement, no behavior change of its own.
    Passed straight through, unchanged, to store_propositions() on BOTH
    call sites below (the gate-off path and the gated pass_props branch)
    so the document's current chunk-id set gets recorded as a back-link
    for whichever propositions actually get stored on this call. Not
    supplying it (the default) is byte-identical to this parameter not
    existing at all -- same discipline as name_pattern/verse_lookup/
    vocab_matcher above.

    Returns one of:
      "skipped_licensed"        — source is public_domain/owned (or missing); nothing written
      "skipped_precept_austin"  — Precept Austin, locked out by name; nothing written
      "too_thin_to_extract"     — (bypass-proofing Phase 3, PLAN.md #45, 2026-07-29) `text`
                                   is under MIN_SUBSTANTIVE_WORD_COUNT words. The model is
                                   NEVER called on this path -- distinct from "no_propositions"
                                   below, where the model ran successfully and legitimately
                                   found nothing. This check fires AFTER the Precept-Austin
                                   and license-status gates above, so a thin-but-Precept-Austin
                                   document still returns "skipped_precept_austin" (that gate
                                   keeps priority) and a thin-but-public_domain/owned document
                                   still returns "skipped_licensed" -- the floor only ever
                                   fires for a document that would otherwise have proceeded to
                                   extraction (a licensed/unlicensed, non-Precept-Austin
                                   source). Nothing written either way.
      "no_propositions"         — the model ran successfully and genuinely found nothing
                                   to extract. A completed result, not a failure. Distinct
                                   from "too_thin_to_extract" -- the model WAS called here.
      "stored:{n}"              — n propositions written to DB, unfiltered. Byte-identical
                                   to pre-Phase-5 behavior. Now fires UNCONDITIONALLY, not
                                   only when name_pattern is None, because
                                   CLOSENESS_CHECK_RETIRED forces this branch regardless of
                                   caller input (see that constant above).
      "stored:{n}:flagged:{m}"  — RETIRED, no longer producible (CLOSENESS_CHECK_RETIRED,
                                   2026-07-29) — the branch that produced this return shape
                                   still exists below, unreachable, kept for a possible
                                   future reversal. Historical description, when it was
                                   live: n propositions (PASS verdict) written to DB, m
                                   withheld and appended instead to CLOSENESS_REVIEW_PATH
                                   (QUOTE_CANDIDATE/HOLD_TOO_LITTLE), n + m always equal to
                                   the number of propositions extract_propositions()
                                   returned for that call.
      "error"                   — the extraction call itself failed (network, rate limit,
                                   timeout, unparseable response) or a later step (license
                                   lookup, storage) failed. Nothing was written; safe to
                                   retry. Distinct from "no_propositions" by construction —
                                   see PropositionExtractionFailed above.

    Gate: extracts for "licensed" and "unlicensed" sources only. Skips
    "public_domain" and "owned" (already safely servable as verbatim
    chunks), and skips a missing/unknown source_id (fail closed). One named
    exception: Precept Austin never gets propositions — see
    PRECEPT_AUSTIN_SOURCE_ID above. A word-count floor (see
    MIN_SUBSTANTIVE_WORD_COUNT above) additionally skips documents too thin
    to plausibly contain a genuine teaching point, checked after both gates
    above and before any call to extract_propositions() -- see
    "too_thin_to_extract" in the return-value list.

    Every row this function writes (stored or later reviewed and approved)
    is stamped with provenance (which prompt version, its fingerprint,
    which model — see store_propositions()) using DEFAULT_PROMPT_VERSION,
    since this function never exposes prompt_version to its own callers and
    so always means that version here. Review-file records carry the exact
    same three provenance values (CLAUDE.md Invariant 10).

    Never raises.
    """
    try:
        if source_id == PRECEPT_AUSTIN_SOURCE_ID:
            return "skipped_precept_austin"

        license_status = get_license_status(conn, source_id)
        if license_status not in ("licensed", "unlicensed"):
            return "skipped_licensed"

        word_count = len(text.split())
        if word_count < MIN_SUBSTANTIVE_WORD_COUNT:
            logger.info(
                "PROPOSITION_TOO_THIN doc=%r word_count=%d threshold=%d",
                document_id, word_count, MIN_SUBSTANTIVE_WORD_COUNT,
            )
            return "too_thin_to_extract"

        prompt_version = prompt_version or DEFAULT_PROMPT_VERSION
        props = (
            validate_approved_propositions(
                approved_propositions,
                text,
                prompt_version,
                speaker=speaker,
            )
            if approved_propositions is not None
            else extract_propositions(
                text,
                doc_id=document_id,
                speaker=speaker,
                prompt_version=prompt_version,
            )
        )
        if not props:
            return "no_propositions"

        fingerprint = prompt_fingerprint(prompt_version)
        model = EXTRACTION_MODEL

        if name_pattern is None or CLOSENESS_CHECK_RETIRED:
            # GATE OFF -- byte-identical to pre-Phase-5 behavior. No import
            # of closeness_check anywhere on this path (not even lazily),
            # no classify() calls, no review file touched. Now fires
            # unconditionally regardless of caller input: CLOSENESS_CHECK_RETIRED
            # (project owner decision, 2026-07-29) means even a caller that
            # explicitly supplies name_pattern still takes this branch.
            count = store_propositions(
                conn, document_id, props, embed_fn,
                prompt_version=prompt_version,
                chunk_ids=chunk_ids,
            )
            return f"stored:{count}"

        # GATE ON. Lazy import — closeness_check (and its own DB-adjacent
        # imports: app.constants, app.services.reference_verifier,
        # source_resolver) is only ever loaded when a caller explicitly
        # opts in by supplying name_pattern, so an off caller incurs zero
        # import-time cost or side effect from this module.
        import closeness_check as cc

        pass_props: List[dict] = []
        review_records: List[dict] = []
        for prop in props:
            content = prop["content"]
            result = cc.classify(content, text, name_pattern, verse_lookup, vocab_matcher)
            if result.verdict == cc.PASS:
                pass_props.append(prop)
            else:
                review_records.append({
                    "written_at": datetime.now(timezone.utc).isoformat(),
                    "document_id": document_id,
                    "proposition_index": prop.get("proposition_index"),
                    "content": content,
                    "verdict": result.verdict,
                    "containment": result.containment,
                    "longest_run_words": result.longest_run_words,
                    "residual_tokens": result.residual_tokens,
                    "prompt_version": prompt_version,
                    "prompt_fingerprint": fingerprint,
                    "model": model,
                })

        # Exhaustive-partition guard -- every extracted proposition must
        # land in exactly one bucket, never neither and never both.
        assert len(pass_props) + len(review_records) == len(props), (
            "closeness-check partition dropped or duplicated a proposition"
        )

        stored_count = 0
        if pass_props:
            stored_count = store_propositions(
                conn, document_id, pass_props, embed_fn,
                prompt_version=prompt_version,
                chunk_ids=chunk_ids,
            )
        # else: nothing PASSED -- store_propositions() is never called, so
        # this function does not commit here. This mirrors the existing
        # "no_propositions"/"skipped_*" contract, where the CALLER's own
        # later commit (see shared_ingest.ingest_document) is what actually
        # lands document+chunks in that case. See the TRANSACTION-ORDERING
        # NOTE just below for why this matters to the review-file write.

        # TRANSACTION-ORDERING NOTE (design note only — the gate is inert
        # this session, so nothing below is a LIVE bug yet, but it is a
        # real, not-yet-closed gap that must be resolved before statement
        # generation resumes): review-file entries are written HERE, AFTER
        # the store_propositions() attempt above has already returned (or
        # been skipped because pass_props was empty) — never before it and
        # never interleaved with it. That ordering guarantees one thing: if
        # store_propositions() itself raises, execution never reaches this
        # point, so no review-file entry is ever written for a document_id
        # whose propositions insert just failed (caught by the outer except
        # below, which rolls back and returns "error", exactly as before).
        #   What it does NOT guarantee: the document row and its chunks are
        # inserted on this SAME shared connection by the CALLER
        # (shared_ingest.ingest_document), BEFORE process_document() ever
        # runs, and are only durably committed at one of two points --
        # inside store_propositions() itself (the pass_props-nonempty
        # branch, via its own conn.commit(), which commits document+chunks+
        # propositions together since they share this connection), OR,
        # when pass_props is empty, LATER, by the caller's own explicit
        # commit after process_document() returns (mirroring exactly how
        # "no_propositions" already behaves today). In that second case,
        # this function writes review-file entries for a document_id that
        # is still only PENDING on the connection at the moment of writing
        # -- if the caller's later commit never happens (a crash, or an
        # exception raised between this return and that commit), those
        # review-file entries would reference a document_id that was never
        # actually persisted: an orphaned entry. Not solved here — the real
        # fix (e.g. moving the review-file write into the caller, after ITS
        # own commit, or staging review records in memory and only
        # flushing to disk once a commit is confirmed) is out of scope for
        # this wiring-only step. Flagged here rather than silently wrong.
        if review_records:
            _write_review_records(review_records)

        return f"stored:{stored_count}:flagged:{len(review_records)}"
    except Exception as exc:
        logger.warning(
            "PROPOSITION_PROCESS_FAIL doc=%r source=%r error=%s",
            document_id, source_id, exc,
        )
        try:
            conn.rollback()
        except Exception:
            pass
        return "error"


# ═══════════════════════════════════════════════════════════════════════════
# Book-length document handling (chapter-scoped, multi-call extraction)
# ═══════════════════════════════════════════════════════════════════════════
# Chapter-scoped proposition-extraction path for book-length documents
# (source_type='book') -- implementation + regression tests only, this
# build. First real-data proof target: Andrew Murray's "The True Vine" (id
# 6daf6671-e386-4103-998e-1fb42914300b), run in a LATER, SEPARATE step (no
# live Groq call against the real book happens anywhere in this build).
#
# WHY THIS EXISTS: process_document()/extract_propositions() send the
# WHOLE reconstructed document text to Groq in a single call
# (max_tokens=8192). A book-length document can blow past what a single
# call can safely both send (context) and receive (output) -- CLAUDE.md
# Invariant 11 already names this as a newly-surfaced, unresolved gap
# (2 of the 7 still-failing documents from the 2026-07-30 backfill are
# this class). This section splits a book into its real chapters FIRST
# (structure, not size, drives the split -- see split_book_into_chapters()
# below), then calls the SAME, UNMODIFIED extract_propositions() once per
# chapter -- process_document() itself is untouched by this build.
#
# Two new entry points, mirroring this module's existing gated/gate-free
# distinction (process_document() vs. extract_propositions()/
# store_propositions() themselves being directly callable -- see this
# module's own top-of-file docstring):
#   process_book_document()             -- gated, production entry point.
#   _extract_and_store_book_chapters()  -- gate-free inner worker, the one
#                                          a later live-proof step calls
#                                          DIRECTLY on the True Vine PD
#                                          book, deliberately bypassing the
#                                          gate -- a disclosed, scoped
#                                          bypass, same shape this module's
#                                          own docstring already describes
#                                          for extract_propositions()/
#                                          store_propositions() being
#                                          directly callable.
# ═══════════════════════════════════════════════════════════════════════════

# ── Chapter-boundary detection ────────────────────────────────────────────────

_CURLY_QUOTE_MAP = {
    "‘": "'",   # LEFT SINGLE QUOTATION MARK
    "’": "'",   # RIGHT SINGLE QUOTATION MARK
    "“": '"',   # LEFT DOUBLE QUOTATION MARK
    "”": '"',   # RIGHT DOUBLE QUOTATION MARK
}


def _normalize_line(s: str) -> str:
    """Unicode NFKC-normalizes `s`, maps curly quotes/apostrophes to their
    straight ASCII equivalents, collapses internal whitespace, and strips.
    This is what lets a title-case chapter-heading line using a straight
    apostrophe ("Christ's Friendship: Its Origin") compare equal to its own
    repeated occurrence, even though the real source text's own ALL-CAPS
    third line for that same title ("CHRIST'S FRIENDSHIP: ITS ORIGIN")
    uses a CURLY apostrophe there instead -- confirmed present in the real
    corpus. That third line is confirmatory only per this module's own
    design brief; _find_title_repeat_boundaries() below never compares
    against it, only against the first two (identically-typeset) repeats."""
    s = unicodedata.normalize("NFKC", s)
    for curly, straight in _CURLY_QUOTE_MAP.items():
        s = s.replace(curly, straight)
    return " ".join(s.split()).strip()


class ChapterSpan(NamedTuple):
    """One detected chapter (or front-matter/back-matter section -- this
    module's boundary detection is generic, not chapter-name-aware) in a
    reconstructed book document.

    label         -- the raw matched title text (or a context-derived
                      label for the pre-first-boundary span).
    char_start,
    char_end      -- this span's [start, end) character offsets in the
                      SAME reconstructed string ordered_chunks were joined
                      into (see _build_chunk_offset_map()).
    text          -- text[char_start:char_end], stored directly so callers
                      never need to re-slice the full reconstructed string.
    chunk_ids     -- every chunk_id whose own [char_start, char_end) span
                      overlaps this chapter's span. A boundary-straddling
                      chunk legitimately belongs to BOTH neighboring
                      chapters -- this is correct, not a bug.
    split_method  -- "title_repeat_boundary" (a real "title repeated
                      verbatim twice" marker started this span),
                      "preface_pre_boundary" (this span is whatever
                      preceded the FIRST detected boundary -- front matter,
                      titled from context, not necessarily a literal
                      "Preface"), or "size_fallback" (no title-repeat
                      marker was found for an abnormally long stretch --
                      see LONG_STRETCH_WORD_THRESHOLD -- so this span was
                      produced by word-count-based splitting instead,
                      never silently treated as one giant chapter)."""
    label: str
    char_start: int
    char_end: int
    text: str
    chunk_ids: List[str]
    split_method: str


def _build_chunk_offset_map(
    ordered_chunks: List[Tuple[str, str]],
) -> Tuple[str, List[Tuple[str, int, int]]]:
    """Joins chunk contents with "\\n" into one reconstructed string (the
    SAME join convention this module's own test suite already uses to
    reconstruct document text from chunks -- see e.g.
    test_propositions_reference_grounding.py's _reconstruct_document_text()
    -- and the same convention shared_ingest.py relies on for
    process_document()'s own single-call `text` argument), and builds a
    parallel offset map recording each chunk_id's own [char_start, char_end)
    span in that EXACT string -- same join, so offsets line up exactly.
    Pure function: no DB, no LLM, no network."""
    parts: List[str] = []
    offset_map: List[Tuple[str, int, int]] = []
    pos = 0
    for chunk_id, content in ordered_chunks:
        start = pos
        end = start + len(content)
        offset_map.append((chunk_id, start, end))
        parts.append(content)
        pos = end + 1  # +1 for the "\n" separator "\n".join() below inserts
    text = "\n".join(parts)
    return text, offset_map


def _chunk_ids_overlapping(
    offset_map: List[Tuple[str, int, int]], start: int, end: int,
) -> List[str]:
    """Every chunk_id in offset_map whose own [c_start, c_end) span
    overlaps [start, end) -- standard half-open-interval overlap test (a
    chunk that only touches the boundary at one exact point does not
    count), so a chunk genuinely straddling a chapter boundary correctly
    appears in both neighboring chapters' lists."""
    return [
        chunk_id for chunk_id, c_start, c_end in offset_map
        if c_start < end and c_end > start
    ]


def _find_title_repeat_boundaries(text: str) -> List[Tuple[int, str]]:
    """Line-scans `text` for the "title repeated verbatim twice" boundary
    signal: a boundary starts at line i where _normalize_line(line[i]) ==
    _normalize_line(line[i+1]) and both are non-empty. The ALL-CAPS third
    line this pattern is usually followed by (and the scripture-reference
    line after THAT) are confirmatory only in the real source text -- never
    required to match here, and not even inspected by this function.

    Returns a list of (char_start_of_line_i, raw_label) tuples, in
    ascending offset order, where raw_label is line[i] itself (stripped) --
    title-case text, not the ALL-CAPS repeat. Matching is NON-OVERLAPPING:
    once a pair (i, i+1) is consumed as a boundary, scanning resumes at
    i+2, never re-matching line i+1 against line i+2 -- so a run of 3
    identical lines (observed in the real corpus, a page-break duplication
    artifact) yields exactly ONE boundary from that run, never two
    overlapping ones."""
    lines = text.split("\n")
    line_offsets: List[int] = []
    pos = 0
    for line in lines:
        line_offsets.append(pos)
        pos += len(line) + 1  # +1 for the "\n" this split() consumed

    boundaries: List[Tuple[int, str]] = []
    i = 0
    n = len(lines)
    while i < n - 1:
        a = _normalize_line(lines[i])
        b = _normalize_line(lines[i + 1])
        if a and a == b:
            boundaries.append((line_offsets[i], lines[i].strip()))
            i += 2
        else:
            i += 1
    return boundaries


def _label_from_context(pre_text: str) -> str:
    """Best-effort label for the span preceding the FIRST detected
    boundary -- there is no repeated-title marker to read a label from (by
    definition), so this falls back to the first non-blank line of the
    span itself, truncated to a sane length. Never raises; returns a
    generic fallback if pre_text is somehow entirely blank (should not
    happen in practice -- this function's one caller,
    split_book_into_chapters(), only calls it with an already
    `.strip()`-truthy pre_text)."""
    for line in pre_text.split("\n"):
        stripped = line.strip()
        if stripped:
            return stripped[:80]
    return "Front matter"


# Raised from 3000 to 6000 (2026-07-31, isolated one-constant change) to
# match the real per-call extraction ceiling, SAFE_CHAPTER_WORD_CEILING
# (defined later in this module) -- a detected chapter under that real
# ceiling is sent to extract_propositions() WHOLE, rather than needlessly
# fragmented into disconnected "(untitled continuation)" size_fallback
# pieces at a lower, unrelated threshold. (Deliberately not written as
# "= SAFE_CHAPTER_WORD_CEILING" -- a plain value match is the minimal,
# clearest edit; the two constants stay independently defined, not
# coupled, so a future change to one does not silently retune the other.)
# Original rationale, still true at the new value: the longest real True
# Vine chapter is 1143 words (2026-07-31 dry-run reconstruction of all 31
# chapters + Preface) -- comfortably under 6000 either way, so this change
# has no effect on that book (confirmed directly, not assumed -- see this
# module's own numeral-detection test suite's cross-check against both
# True Vine and Power Through Prayer's already-reported span counts).
LONG_STRETCH_WORD_THRESHOLD = 6000

_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"\S+")


def _paragraph_spans(text: str) -> List[Tuple[int, int]]:
    """(start, end) char spans for each non-empty, blank-line-delimited
    paragraph in `text`, in order. A run of one or more blank lines (a
    line containing only whitespace) is the delimiter; the delimiter text
    itself belongs to no paragraph. Used only by _split_text_by_size()'s
    own paragraph-first sub-split step."""
    spans: List[Tuple[int, int]] = []
    pos = 0
    for m in _PARAGRAPH_SPLIT_RE.finditer(text):
        piece = text[pos:m.start()]
        if piece.strip():
            spans.append((pos, m.start()))
        pos = m.end()
    piece = text[pos:]
    if piece.strip():
        spans.append((pos, len(text)))
    return spans


def _sentence_spans(text: str) -> List[Tuple[int, int]]:
    """(start, end) char spans for each non-empty sentence in `text` (split
    on whitespace immediately following ./!/? -- a simple heuristic, not a
    real sentence tokenizer, sufficient for this fallback's own purpose:
    finding a defensible smaller unit than "one whole paragraph" when a
    single paragraph alone exceeds a word ceiling). Used only by
    _split_text_by_size()'s own sentence-level sub-split step."""
    spans: List[Tuple[int, int]] = []
    pos = 0
    for m in _SENTENCE_SPLIT_RE.finditer(text):
        piece = text[pos:m.start()]
        if piece.strip():
            spans.append((pos, m.start()))
        pos = m.end()
    piece = text[pos:]
    if piece.strip():
        spans.append((pos, len(text)))
    return spans


def _hard_word_split_spans(text: str, ceiling_words: int) -> List[Tuple[int, int]]:
    """LAST-RESORT (start, end) char spans, each containing up to
    ceiling_words whitespace-delimited words -- used only by
    _split_text_by_size() when a SINGLE sentence alone still exceeds the
    ceiling. Explicitly flagged by the caller's own returned method label
    ("hard_word_split"), never silent."""
    words = list(_WORD_RE.finditer(text))
    spans: List[Tuple[int, int]] = []
    i = 0
    while i < len(words):
        batch = words[i:i + ceiling_words]
        spans.append((batch[0].start(), batch[-1].end()))
        i += ceiling_words
    return spans


def _batch_spans(
    text: str,
    spans: List[Tuple[int, int]],
    ceiling_words: int,
    method_label: str,
    oversized_fn: Callable[[str, int, int, int], List[Tuple[int, int, str, str]]],
) -> List[Tuple[int, int, str, str]]:
    """Shared batching primitive used at every granularity level of
    _split_text_by_size() (paragraph, then sentence, then hard word-split
    as the terminal level). Batches consecutive (start, end) spans from
    `spans` (already sorted, non-overlapping, in original document order)
    together into as few pieces as possible without any piece exceeding
    ceiling_words words, and WITHOUT ever splitting a single span across
    two pieces. A single span whose OWN word count exceeds ceiling_words is
    never batched with anything -- it is instead handed to
    oversized_fn(text, start, end, ceiling_words), which returns its own
    list of (start, end, sub_text, method) results for that one span,
    spliced into the returned list in that span's own place (letting the
    recursion continue at a finer granularity for THAT span only, while
    ordinary batching still applies to every other span at this level)."""
    result: List[Tuple[int, int, str, str]] = []
    batch_start: Optional[int] = None
    batch_end: Optional[int] = None
    batch_words = 0

    def _flush():
        nonlocal batch_start, batch_end, batch_words
        if batch_start is not None:
            result.append((batch_start, batch_end, text[batch_start:batch_end], method_label))
        batch_start, batch_end, batch_words = None, None, 0

    for s_start, s_end in spans:
        s_text = text[s_start:s_end]
        s_words = len(s_text.split())

        if s_words > ceiling_words:
            _flush()
            result.extend(oversized_fn(text, s_start, s_end, ceiling_words))
            continue

        if batch_start is None:
            batch_start, batch_end, batch_words = s_start, s_end, s_words
        elif batch_words + s_words <= ceiling_words:
            batch_end = s_end
            batch_words += s_words
        else:
            _flush()
            batch_start, batch_end, batch_words = s_start, s_end, s_words

    _flush()
    return result


def _split_by_hard_word(
    text: str, start: int, end: int, ceiling_words: int,
) -> List[Tuple[int, int, str, str]]:
    """Terminal fallback: a single sentence (start, end) that itself
    exceeds ceiling_words is hard-word-split, explicitly flagged
    "hard_word_split". Each produced piece already respects ceiling_words
    by construction (see _hard_word_split_spans()), so no further batching
    is needed at this level."""
    sub_text = text[start:end]
    return [
        (start + w_start, start + w_end, sub_text[w_start:w_end], "hard_word_split")
        for w_start, w_end in _hard_word_split_spans(sub_text, ceiling_words)
    ]


def _split_by_sentence(
    text: str, start: int, end: int, ceiling_words: int,
) -> List[Tuple[int, int, str, str]]:
    """A single paragraph (start, end) that itself exceeds ceiling_words is
    sub-split at sentence boundaries, with consecutive sentences BATCHED
    together up to ceiling_words (same batching discipline as the
    paragraph level in _split_text_by_size() -- never one output piece per
    sentence unconditionally). A single sentence that itself still exceeds
    ceiling_words falls to _split_by_hard_word()."""
    sub_text = text[start:end]
    local_spans = _sentence_spans(sub_text)
    if not local_spans:
        local_spans = [(0, len(sub_text))]
    abs_spans = [(start + s, start + e) for s, e in local_spans]
    return _batch_spans(text, abs_spans, ceiling_words, "sentence", _split_by_hard_word)


def _split_text_by_size(
    text: str, ceiling_words: int,
) -> List[Tuple[int, int, str, str]]:
    """Splits `text` into consecutive pieces, none exceeding ceiling_words
    words if avoidable: paragraph boundaries first (blank-line-delimited,
    consecutive whole paragraphs BATCHED together up to the ceiling, never
    splitting a single paragraph in half); if a SINGLE paragraph alone
    exceeds ceiling_words, that paragraph is instead sub-split at sentence
    boundaries (consecutive sentences batched the same way); if a SINGLE
    sentence alone exceeds ceiling_words, an explicitly-flagged hard
    word-split is the last resort. Batching applies at every level -- this
    is never "one output piece per paragraph/sentence unconditionally",
    only ever splitting further when a single unit at the current
    granularity is itself too large to batch with anything.

    Returns a list of (local_start, local_end, sub_text, method) tuples,
    offsets LOCAL to `text` itself (0-based -- the caller adds its own base
    offset if it needs an absolute position). method is one of "paragraph",
    "sentence", "hard_word_split" -- or, if `text`'s total word count is
    already <= ceiling_words, a single-item list with method
    "no_split_needed" (defensive; every real caller of this function only
    calls it after already confirming the ceiling is exceeded, but this
    function does not assume that of every possible caller).

    Pure function: no DB, no LLM, no network."""
    if len(text.split()) <= ceiling_words:
        return [(0, len(text), text, "no_split_needed")]

    paragraphs = _paragraph_spans(text)
    if not paragraphs and text.strip():
        paragraphs = [(0, len(text))]

    return _batch_spans(text, paragraphs, ceiling_words, "paragraph", _split_by_sentence)


# ── Optional TOC-based missing-chapter cross-check ─────────────────────────────
# Refinement, not a requirement: best-effort parse of a "Contents"/table-of-
# contents section, if one is present, used only to report which of ITS
# listed titles were never found among the boundaries this module's own
# line-scan detected. Never raises; returns [] (no cross-check performed)
# on anything it can't confidently parse, rather than guessing.

_TOC_LINE_RE = re.compile(r"^(.*\S)\s+(\d+)\.*$")
_ROMAN_NUMERAL_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)


def _extract_expected_chapter_titles(text: str) -> List[str]:
    """Scans for a line that normalizes to exactly "Contents" within the
    first 400 lines of `text`, then reads subsequent "<title> <page
    number>" lines as long as each page number strictly increases over the
    last one accepted -- a real table of contents always lists ascending
    page numbers, so this is what lets this scan stop cleanly at the real
    end of the Contents section rather than wandering into an unrelated
    later run of text that happens to also end in digits (confirmed
    necessary against the real True Vine source, whose own front matter
    contains a partial, corrupted repeat of one Contents line immediately
    after the genuine section -- the non-increasing page number on that
    corrupted line is exactly what stops this scan before it's reached).
    A bare roman-numeral page-footer line (e.g. "ii") is also rejected
    outright as a title candidate. Returns [] if no Contents header is
    found, or if nothing parses. Never raises past this function."""
    try:
        lines = text.split("\n")
        toc_start = None
        for i, line in enumerate(lines[:400]):
            if _normalize_line(line) == "Contents":
                toc_start = i + 1
                break
        if toc_start is None:
            return []

        titles: List[str] = []
        last_page = -1
        for line in lines[toc_start:toc_start + 200]:
            stripped = line.strip()
            if not stripped:
                continue
            m = _TOC_LINE_RE.match(stripped)
            if not m:
                if titles:
                    break
                continue
            title_part = m.group(1).strip()
            if _ROMAN_NUMERAL_RE.match(title_part):
                if titles:
                    break
                continue
            page_num = int(m.group(2))
            if page_num <= last_page:
                break
            last_page = page_num
            titles.append(_normalize_line(title_part))
        return titles
    except Exception:
        return []


def _find_missing_expected_titles(text: str, chapters: List[ChapterSpan]) -> List[str]:
    """Cross-checks _extract_expected_chapter_titles()'s parse (if any)
    against the labels this module's own boundary detection actually
    found. Returns the (normalized) expected titles that never matched any
    detected chapter label -- [] if no Contents section was found at all
    (nothing to cross-check against), NOT the same claim as "nothing is
    missing". Purely diagnostic; split_book_into_chapters() never treats a
    non-empty result here as an error."""
    expected = _extract_expected_chapter_titles(text)
    if not expected:
        return []
    detected = {_normalize_line(c.label) for c in chapters}
    return [t for t in expected if t not in detected]


def split_book_into_chapters(
    ordered_chunks: List[Tuple[str, str]],
) -> Tuple[List[ChapterSpan], List[str]]:
    """Splits a book-length document's chunks into chapter-scoped
    ChapterSpans, using STRUCTURE (a repeated-title marker), not raw size,
    as the primary split signal -- see ChapterSpan's own docstring for the
    full algorithm.

    ordered_chunks: (chunk_id, content) tuples in chunk_index order.

    Returns (chapters, missing_expected_titles):
      chapters                 -- List[ChapterSpan], in document order.
      missing_expected_titles  -- best-effort TOC cross-check (see
                                   _find_missing_expected_titles()) -- a
                                   diagnostic list, always [] if no
                                   Contents section could be parsed at all,
                                   never a claim that emptiness here means
                                   nothing was missed.

    Pure function: no DB, no LLM, no network -- callers supply
    ordered_chunks themselves (a single bulk SELECT, not fetched here)."""
    text, offset_map = _build_chunk_offset_map(ordered_chunks)
    boundaries = _find_title_repeat_boundaries(text)

    chapters: List[ChapterSpan] = []

    if not boundaries:
        # No title-repeat marker found ANYWHERE -- the whole document is
        # one long, entirely unmarked stretch. Size-fallback the entire
        # text rather than silently treating it as one giant "chapter".
        for s, e, sub_text, _method in _split_text_by_size(text, LONG_STRETCH_WORD_THRESHOLD):
            chapters.append(ChapterSpan(
                label="Untitled section",
                char_start=s, char_end=e, text=sub_text,
                chunk_ids=_chunk_ids_overlapping(offset_map, s, e),
                split_method="size_fallback",
            ))
        return chapters, []

    # Content preceding the FIRST detected boundary is its own span --
    # front matter in practice (title page, copyright notice, table of
    # contents), labeled from context, not assumed to be a literal
    # "Preface" (a real "Preface" boundary, if the source has one, is its
    # own separately-detected span below, same as every other chapter).
    first_start = boundaries[0][0]
    if first_start > 0:
        pre_text = text[0:first_start]
        if pre_text.strip():
            chapters.append(ChapterSpan(
                label=_label_from_context(pre_text),
                char_start=0, char_end=first_start, text=pre_text,
                chunk_ids=_chunk_ids_overlapping(offset_map, 0, first_start),
                split_method="preface_pre_boundary",
            ))

    for idx, (b_start, raw_label) in enumerate(boundaries):
        b_end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(text)
        span_text = text[b_start:b_end]
        word_count = len(span_text.split())

        if word_count > LONG_STRETCH_WORD_THRESHOLD:
            # This stretch, starting from a REAL detected boundary, is
            # abnormally long -- almost certainly containing more than one
            # real chapter this scan's marker just didn't catch (a
            # different heading shape, or a genuinely marker-less
            # section). Size-fallback-split THIS stretch only -- never
            # silently absorbed as one oversized "chapter".
            for s, e, sub_text, _method in _split_text_by_size(span_text, LONG_STRETCH_WORD_THRESHOLD):
                abs_s, abs_e = b_start + s, b_start + e
                chapters.append(ChapterSpan(
                    label="{0} (untitled continuation)".format(raw_label),
                    char_start=abs_s, char_end=abs_e, text=sub_text,
                    chunk_ids=_chunk_ids_overlapping(offset_map, abs_s, abs_e),
                    split_method="size_fallback",
                ))
        else:
            chapters.append(ChapterSpan(
                label=raw_label,
                char_start=b_start, char_end=b_end, text=span_text,
                chunk_ids=_chunk_ids_overlapping(offset_map, b_start, b_end),
                split_method="title_repeat_boundary",
            ))

    missing_expected_titles = _find_missing_expected_titles(text, chapters)
    return chapters, missing_expected_titles


# ── Sub-split-if-still-too-large fallback (SAFE_CHAPTER_WORD_CEILING) ──────────

# max_tokens=8192 ≈ 6000-6300 output words; conservative low end of a
# 4x-density-hypothesis safe-input-ceiling range.
SAFE_CHAPTER_WORD_CEILING = 6000


class ChapterSubUnit(NamedTuple):
    """One sub-unit of a ChapterSpan, after applying the
    SAFE_CHAPTER_WORD_CEILING fallback (see _apply_word_ceiling_fallback()).
    For a chapter at or under the ceiling, this is a 1:1 passthrough
    (method="single_unit"). For an over-ceiling chapter, there are multiple
    sub-units per parent chapter -- EVERY one still carries the PARENT
    chapter's own chunk_ids, never recomputed per sub-unit (chapter
    granularity, not further subdivided: sub-splitting here is a
    token/API-limit accommodation, not a genuine structural boundary, so
    the honest back-link is still "the whole parent chapter's chunks",
    identical across every sub-unit)."""
    parent_label: str
    text: str
    method: str  # "single_unit" | "paragraph" | "sentence" | "hard_word_split"
    chunk_ids: List[str]


def _apply_word_ceiling_fallback(chapters: List[ChapterSpan]) -> List[ChapterSubUnit]:
    """Applies SAFE_CHAPTER_WORD_CEILING to every ChapterSpan in `chapters`,
    in order. A chapter at or under the ceiling passes through unchanged as
    a single ChapterSubUnit. An over-ceiling chapter is sub-split via
    _split_text_by_size() (paragraph -> sentence -> hard word-split) into
    multiple ChapterSubUnits, each sharing the SAME parent chunk_ids.

    Expected to be INERT for The True Vine (real chapters run 719-1143
    words, per this build's own dry-run reconstruction -- far under the
    6000-word ceiling); exercised for real only by this module's own
    synthetic oversized-chapter regression test."""
    result: List[ChapterSubUnit] = []
    for ch in chapters:
        word_count = len(ch.text.split())
        if word_count <= SAFE_CHAPTER_WORD_CEILING:
            result.append(ChapterSubUnit(ch.label, ch.text, "single_unit", ch.chunk_ids))
            continue
        for _s, _e, sub_text, method in _split_text_by_size(ch.text, SAFE_CHAPTER_WORD_CEILING):
            result.append(ChapterSubUnit(ch.label, sub_text, method, ch.chunk_ids))
    return result


# ── Scripture-focus marker -- NOT BUILT, reported instead ──────────────────────
#
# Per this build's own mandatory pre-check (2026-07-31, live, READ-ONLY): 3
# real True Vine chapters ("The Vine" [ch. 1, 766 words], "Abide" [790
# words], "Christ's Friendship: Its Origin" [830 words]) were reconstructed
# via a real read-only DB connection and each run through
# reference_grounding.find_reference_spans(). Result: ZERO spans in ALL
# THREE chapters (average 0.0 spans/chapter, against a required >=3/chapter
# bar to proceed). Root cause confirmed by direct inspection of the
# reconstructed text: The True Vine cites scripture almost exclusively in
# DOTTED form ("John 15.1", "John 15.5", "Colossians 1.26,27" ...),
# essentially never in the colon form ("John 15:1") find_reference_spans()'s
# own scanning regex requires to recognize a candidate in the first place --
# exactly the known landmine CLAUDE.md already names ("colon-only scanner
# blind to True Vine's dotted 'John 15.1' references"), now confirmed
# empirically against this specific book rather than assumed. Per this
# build's own explicit instruction: do NOT build a fancier detector to
# compensate -- the trivial marker mechanism does not reliably capture
# scripture-focus for this book, reported, not built further. No
# scripture_focus field, code, table, column, endpoint, or classification
# logic of any kind exists anywhere in this module as a result.


# ── Entry points ────────────────────────────────────────────────────────────────

def process_book_document(
    conn,
    document_id: str,
    source_id: str,
    ordered_chunks: List[Tuple[str, str]],
    embed_fn: Callable[[str], List[float]],
    speaker: Optional[str] = None,
    prompt_version: Optional[str] = None,
) -> dict:
    """Production, GATED entry point for book-length (source_type='book')
    proposition extraction -- the book-length counterpart to
    process_document(). Runs the SAME gate order as process_document()'s
    own top, before delegating to the gate-free inner worker,
    _extract_and_store_book_chapters():

      1. Precept Austin short-circuit (PRECEPT_AUSTIN_SOURCE_ID) --
         returns {"status": "skipped_precept_austin"} immediately.
      2. get_license_status()/license-status gate -- a source that is not
         "licensed" or "unlicensed" (public_domain, owned, or unknown/
         missing) returns {"status": "skipped_licensed"} immediately.
         NEVER CALLED ON THE TRUE VINE PD BOOK IN PRODUCTION -- its source
         is public_domain, so a real call through THIS function (not the
         later live-proof step's own deliberate, disclosed bypass straight
         to _extract_and_store_book_chapters()) always returns
         skipped_licensed for it; see this module's own regression test
         for a real-gate, fake-conn proof of exactly that.

    On a licensed/unlicensed source, delegates to
    _extract_and_store_book_chapters() and returns its reconciliation dict
    with one key added, "status": "processed" (never overwriting any of
    that dict's own keys -- see that function's own docstring for the full
    shape).

    Return shape (a dict, always -- richer than process_document()'s bare
    string, since a book run has per-chapter reconciliation to report):
      {"status": "skipped_precept_austin"}
      {"status": "skipped_licensed"}
      {"status": "processed", "chapters_attempted": int,
       "chapters_stored": int, "chapters_empty": int,
       "chapters_errored": int, "chapters_skipped_thin": int,
       "chapters_skipped_front_matter": int,
       "propositions_stored": int, "per_chapter": [...]}

    Gate checks failing outright (e.g. a genuine DB error from
    get_license_status()) propagate as an ordinary exception here, exactly
    like process_document()'s own get_license_status() call would in
    isolation -- this function adds no additional try/except of its own at
    the gate-check layer. _extract_and_store_book_chapters()'s own inner
    loop is separately non-fatal per-chapter by design (one bad chapter
    never aborts the run) -- see that function's own docstring."""
    if source_id == PRECEPT_AUSTIN_SOURCE_ID:
        return {"status": "skipped_precept_austin"}

    license_status = get_license_status(conn, source_id)
    if license_status not in ("licensed", "unlicensed"):
        return {"status": "skipped_licensed"}

    result = _extract_and_store_book_chapters(
        conn, document_id, ordered_chunks, embed_fn,
        speaker=speaker,
        prompt_version=prompt_version or DEFAULT_PROMPT_VERSION,
    )
    merged = {"status": "processed"}
    merged.update(result)
    return merged


def _extract_and_store_book_chapters(
    conn,
    document_id: str,
    ordered_chunks: List[Tuple[str, str]],
    embed_fn: Callable[[str], List[float]],
    speaker: Optional[str],
    prompt_version: str,
    store_fn: Callable = store_propositions,
) -> dict:
    """GATE-FREE inner worker -- no Precept-Austin/license-status check of
    its own (see process_book_document() for the gated entry point). This
    is the function a later, separate live-proof step calls DIRECTLY on
    the True Vine public_domain book, a disclosed, scoped bypass of
    process_book_document()'s own gate -- the same shape this module's own
    top-of-file docstring already describes for extract_propositions()/
    store_propositions() themselves being directly callable.

    Steps:
      1. split_book_into_chapters(ordered_chunks) -- structure-first
         chapter detection. The returned missing_expected_titles
         diagnostic is logged (INFO) but not acted on further here.
      2. _apply_word_ceiling_fallback() -- sub-splits any chapter over
         SAFE_CHAPTER_WORD_CEILING (expected inert for The True Vine).
      3. Exactly ONE `DELETE FROM propositions WHERE document_id = %s`,
         issued HERE, before the chapter loop -- not delegated to
         store_fn/clear_existing (each per-chapter store_fn call below
         passes clear_existing=False for exactly this reason: one
         document-level clear, never one per chapter). This DELETE shares
         this call's own `conn` and is only durably committed once some
         later store_fn() call reaches its own conn.commit() (store_fn is
         store_propositions() by default, which always commits) -- if
         EVERY sub-unit ends up empty/errored/skipped_thin (store_fn never
         called at all), this DELETE is issued but left uncommitted on
         this connection, exactly mirroring process_document()'s own
         documented TRANSACTION-ORDERING behavior for its "nothing PASSED"
         case: the caller's own later commit (or lack of one) decides
         whether it lands.
      4. A running proposition_index counter, continuous across chapters
         (never reset per chapter) -- avoids a (document_id,
         proposition_index) collision class this repo has already been
         burned by.
      5. For each sub-unit, in order:
           - word-count check against MIN_SUBSTANTIVE_WORD_COUNT: under
             the floor -> bucketed "skipped_thin", NO model call.
           - else: extract_propositions(sub_unit.text, doc_id=document_id,
             speaker=speaker, prompt_version=prompt_version) -- UNMODIFIED,
             reused as-is (this is what gives per-chapter reference-
             grounding/allowed-reference-list scope for free).
               * PropositionExtractionFailed -> bucketed "errored", NEVER
                 aborts the remaining chapters.
               * [] (genuine empty result) -> bucketed "empty".
               * non-empty -> proposition_index values renumbered via the
                 running counter, then store_fn(conn, document_id,
                 renumbered_props, embed_fn, prompt_version=prompt_version,
                 chunk_ids=sub_unit.chunk_ids, clear_existing=False) ->
                 bucketed "stored".

    Returns a reconciliation dict:
      {"chapters_attempted": int, "chapters_stored": int,
       "chapters_empty": int, "chapters_errored": int,
       "chapters_skipped_thin": int, "chapters_skipped_front_matter": int,
       "propositions_stored": int,
       "per_chapter": [{"label": str, "split_method": str,
                        "word_count": int, "outcome": str,
                        "n_propositions": int, ...}, ...]}
    ("matter_reason": str is additionally present ONLY on a per_chapter
    entry whose "outcome" is "skipped_front_matter" -- see
    is_front_back_matter()'s own docstring for the possible values.)
    Buckets always reconcile: chapters_attempted == chapters_stored +
    chapters_empty + chapters_errored + chapters_skipped_thin +
    chapters_skipped_front_matter (asserted below before returning).

    FRONT/BACK-MATTER FILTER (correction pass; fix (a)/(b) below): each
    sub-unit is checked via is_front_back_matter(unit.parent_label,
    unit.text, author=speaker) BEFORE the MIN_SUBSTANTIVE_WORD_COUNT
    thin-check below -- a matter-classified span (a CCEL bibliographic-
    metadata-plus-Table-of-Contents block, a Title Page, an Indexes/
    scripture-index span, a third-party byline, an editorial-apparatus
    label, etc.) is bucketed "skipped_front_matter" and NEVER reaches
    extract_propositions() at all, regardless of its own word count.
    `author=speaker` is passed on THIS call site only -- the OTHER call
    site (detect_book_chapters()'s own R-computation) deliberately still
    calls without `author`, out of scope for that still-unwired path. See
    is_front_back_matter()'s own docstring (defined near
    MIN_SUBSTANTIVE_WORD_COUNT above) for the full label/shape decision
    (now including the byline/apparatus checks) and its protected-label
    false-positive
    guard -- a genuine "Preface"/"Introduction"/etc. span is NEVER
    shape-checked and always proceeds past this filter unfiltered."""
    chapters, missing_expected_titles = split_book_into_chapters(ordered_chunks)
    if missing_expected_titles:
        logger.info(
            "BOOK_CHAPTER_SPLIT_MISSING_TITLES doc=%r missing=%r",
            document_id, missing_expected_titles,
        )
    sub_units = _apply_word_ceiling_fallback(chapters)

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM propositions WHERE document_id = %s",
            (document_id,),
        )

    proposition_index = 1
    n_stored_chapters = 0
    n_empty_chapters = 0
    n_errored_chapters = 0
    n_skipped_thin_chapters = 0
    n_skipped_front_matter_chapters = 0
    n_propositions_stored = 0
    per_chapter: List[dict] = []

    for unit in sub_units:
        word_count = len(unit.text.split())

        matter, matter_reason = is_front_back_matter(unit.parent_label, unit.text, author=speaker)
        if matter:
            n_skipped_front_matter_chapters += 1
            per_chapter.append({
                "label": unit.parent_label, "split_method": unit.method,
                "word_count": word_count, "outcome": "skipped_front_matter",
                "matter_reason": matter_reason, "n_propositions": 0,
            })
            continue

        if word_count < MIN_SUBSTANTIVE_WORD_COUNT:
            n_skipped_thin_chapters += 1
            per_chapter.append({
                "label": unit.parent_label, "split_method": unit.method,
                "word_count": word_count, "outcome": "skipped_thin",
                "n_propositions": 0,
            })
            continue

        try:
            props = extract_propositions(
                unit.text, doc_id=document_id, speaker=speaker,
                prompt_version=prompt_version,
            )
        except PropositionExtractionFailed as exc:
            logger.warning(
                "BOOK_CHAPTER_EXTRACT_FAIL doc=%r label=%r error=%s",
                document_id, unit.parent_label, exc,
            )
            n_errored_chapters += 1
            per_chapter.append({
                "label": unit.parent_label, "split_method": unit.method,
                "word_count": word_count, "outcome": "errored",
                "n_propositions": 0,
            })
            continue

        if not props:
            n_empty_chapters += 1
            per_chapter.append({
                "label": unit.parent_label, "split_method": unit.method,
                "word_count": word_count, "outcome": "empty",
                "n_propositions": 0,
            })
            continue

        renumbered_props: List[dict] = []
        for prop in props:
            new_prop = dict(prop)
            new_prop["proposition_index"] = proposition_index
            renumbered_props.append(new_prop)
            proposition_index += 1

        n_stored_this_chapter = store_fn(
            conn, document_id, renumbered_props, embed_fn,
            prompt_version=prompt_version,
            chunk_ids=unit.chunk_ids,
            clear_existing=False,
        )
        n_stored_chapters += 1
        n_propositions_stored += n_stored_this_chapter
        per_chapter.append({
            "label": unit.parent_label, "split_method": unit.method,
            "word_count": word_count, "outcome": "stored",
            "n_propositions": n_stored_this_chapter,
        })

    chapters_attempted = len(sub_units)
    assert chapters_attempted == (
        n_stored_chapters + n_empty_chapters + n_errored_chapters
        + n_skipped_thin_chapters + n_skipped_front_matter_chapters
    ), (
        "book-chapter bucket accounting failed to reconcile: attempted=%d != "
        "stored=%d + empty=%d + errored=%d + skipped_thin=%d + skipped_front_matter=%d" % (
            chapters_attempted, n_stored_chapters, n_empty_chapters,
            n_errored_chapters, n_skipped_thin_chapters, n_skipped_front_matter_chapters,
        )
    )

    return {
        "chapters_attempted": chapters_attempted,
        "chapters_stored": n_stored_chapters,
        "chapters_empty": n_empty_chapters,
        "chapters_errored": n_errored_chapters,
        "chapters_skipped_thin": n_skipped_thin_chapters,
        "chapters_skipped_front_matter": n_skipped_front_matter_chapters,
        "propositions_stored": n_propositions_stored,
        "per_chapter": per_chapter,
    }



# ═══════════════════════════════════════════════════════════════════════════
# Single-occurrence numeral/roman-numeral chapter-heading detection
# ═══════════════════════════════════════════════════════════════════════════
# NEW, SEPARATE detection path for pattern (a): a book whose chapter
# headings each appear exactly ONCE (no "title repeated verbatim twice"
# marker _find_title_repeat_boundaries() relies on) -- e.g. Andrew Murray's
# "The Master's Indwelling" ('I. CARNAL CHRISTIANS.') or F.B. Meyer's "The
# Secret of Guidance" ('II. Where Am I Wrong?'). split_book_into_chapters(),
# _find_title_repeat_boundaries(), is_front_back_matter(),
# _extract_and_store_book_chapters(), process_book_document(), and
# store_propositions() are ALL UNTOUCHED by this section -- every one of
# them is called here exactly as it already exists, never reimplemented or
# modified. This section is purely additive.
#
# NOT in scope here (investigated and explicitly excluded, not a bug):
# `LONG_STRETCH_WORD_THRESHOLD`-driven re-splitting of correctly-detected
# 3000-6000-word repeat-marker chapters into "(untitled continuation)"
# size_fallback pieces inside split_book_into_chapters() itself -- a real,
# separate, already-existing quality issue in already-committed code,
# deliberately not touched this step. OCR-corrupted heading keywords
# ("CHAPTEE", "WOKD") are also explicitly out of scope -- no fuzzy matching
# is added for them; a book relying on those (Catherine Booth's "Aggressive
# Christianity", Phoebe Palmer's "The Way of Holiness") is INTENDED to fall
# through to needs_eyeball, not a gap this section closes.

# _ROMAN_NUMERAL_UNIT_VALUES/_int_to_roman()/_roman_to_int() (originally here
# too) now live earlier in this file, near _digit_token_ratio() -- fix (b)'s
# own dependency on them moved their definition, not forked it; reused
# unchanged here.
# ── Line-pattern regexes ────────────────────────────────────────────────────
# Deliberately NOT compiled with re.IGNORECASE -- the roman-numeral
# character classes below only ever match UPPERCASE I/V/X/L/C/D/M, and the
# "Chapter"/"CHAPTER" keyword alternation only ever matches those two exact
# spellings. This is what structurally satisfies discriminator (2) (a
# lowercase-roman page-number line like "ii" can never reach either regex
# at all, by construction, with no separate runtime check needed for it).
#
# Deliberately EXCLUDED (higher false-positive risk, explicitly out of
# scope per this section's own design brief): bare arabic-dot headings
# ("1. Title") with no "Chapter" keyword, and a bare number alone on its
# own line. A book relying only on those falls to needs_eyeball.
#
# ROMAN-DOT's own title-capture bound (58 chars) is DELIBERATELY left
# EXACTLY as it was -- this is what protects against inline argument-
# enumerators in ordinary prose (confirmed real false-positive risks:
# Finney's "I. To what particular points...", Ryle's "I. Let us consider,
# firstly...", CLF's "D. ..."). Only CHAPTER-WORD's own bound is widened
# below (58 -> 118 chars) -- the literal "Chapter"/"CHAPTER" keyword prefix
# makes a false match at THIS pattern specifically much less likely, and
# real in-body chapter titles at this pattern can run longer than 58 chars
# (e.g. Finney's real "Chapter 10: Dishonesty in Small Matters Inconsistent
# with Honesty in Anything", 77 chars total).
_ROMAN_DOT_HEADING_RE = re.compile(r'^([IVXLCDM]{1,7})\.\s+(\S.{0,58})$')
_CHAPTER_WORD_HEADING_RE = re.compile(
    r'^(?:Chapter|CHAPTER)\s+([IVXLCDM]{1,7}|\d{1,3})(?:\s*[-:]\s*(\S.{0,118}))?$'
)
_TRAILING_BARE_NUMBER_RE = re.compile(r'\s\d{1,4}\s*$')

# Leading quote characters to strip before discriminator 3's capital-letter
# check (roman-dot pattern only) -- reuses the EXISTING _CURLY_QUOTE_MAP
# (defined above, used elsewhere in this module for line normalization) as
# the single source of truth for which characters count as curly quotes,
# rather than inventing a second, parallel quote-character set. Straight
# quote marks are added on top since _CURLY_QUOTE_MAP itself only maps
# curly ones to their straight equivalents.
_LEADING_TITLE_QUOTE_CHARS = set(_CURLY_QUOTE_MAP.keys()) | {'"', "'"}

# Confidence thresholds (see _detect_numeral_heading_sequence()'s own
# docstring for what each guards against).
NUMERAL_MIN_ACCEPTED = 3
NUMERAL_MIN_COVERAGE_RATIO = 0.6
NUMERAL_MAX_GAP = 3

# Minimum body-text word count required BETWEEN two candidates for one to
# legally follow the other in the DP chain below (_select_numeral_chain())
# -- distinct from NUMERAL_MAX_GAP, which caps a gap between consecutive
# ACCEPTED SEQUENCE VALUES (e.g. value 5 following value 3), not a word
# count. A real chapter has at least this many words of body text before
# the next heading candidate; mirrors MIN_SUBSTANTIVE_WORD_COUNT's own
# rationale (content under 50 words is already treated as too thin to be a
# real chapter elsewhere in this module). This is what invalidates a link
# between two members of a front-matter TOC-restatement cluster or a
# same-value running-header repeat sitting almost back-to-back with almost
# no real content between them.
NUMERAL_MIN_CONTENT_GAP_WORDS = 50

# Document-span floor guard, the safety-critical one: the accepted chain's
# OWN span (last_accepted_offset - first_accepted_offset) must cover at
# least this fraction of the WHOLE document's own character length, or the
# result is needs_eyeball regardless of how clean the chain looks by every
# other measure (length, coverage, gap). Empirically validated: real,
# book-spanning chains on books that work correctly measured 75-89% span
# fraction (Master's Indwelling, Meyer's Secret of Guidance, Bounds'
# Necessity of Prayer, Torrey's How To Pray, Ryle's Holiness); the two
# confirmed-bad chains this guard exists to catch (Kreighbaum's own
# localized 5-point end-of-book outline, and School of Obedience's
# subsection-cluster chain when the numeral detector is consulted in
# isolation) measured 1.5% and 11.7% respectively -- a 63-point margin, so
# 0.5 is a safe, well-separated threshold, not a knife-edge guess. This is
# the guard that actually rejects Kreighbaum: Fix (B)'s own span-weighted
# DP objective change alone does NOT reject it (there is no wider
# candidate chain anywhere in that book for the objective to prefer
# instead -- the real top-level chapter structure doesn't use this
# detector's recognized conventions at all), so this independent,
# document-level floor is the backstop that catches a chain which is
# locally "clean" (high coverage, small gaps) but globally tiny relative
# to the whole document.
NUMERAL_MIN_DOC_SPAN_FRACTION = 0.5


def _select_numeral_chain(
    candidates: List[Tuple[int, int, str, int]],
    cum_words: List[int],
) -> List[dict]:
    """Longest strictly-value-increasing chain over `candidates`
    (line_start_offset, value, raw_label, line_idx), already ascending by
    offset and already discriminator-survived. `cum_words` is a prefix-sum
    array over the SAME document's lines (cum_words[k] == total word count
    across lines[0:k]) -- this is a pure PERFORMANCE optimization of
    "gap = word_count(text[offset_j:offset_i])": since every candidate
    offset is exactly a LINE-START offset, text[offset_j:offset_i] is
    always exactly the whole lines from line_idx_j up to (but not
    including) line_idx_i, so cum_words[line_idx_i] - cum_words[line_idx_j]
    yields the IDENTICAL word count a literal substring-slice-and-split
    would, in O(1) instead of O(gap length) per pair -- this matters at
    O(n^2) candidate-pair scale on a long, candidate-dense real book
    (confirmed necessary against a real fixture during this build: a naive
    per-pair text-slice computation did not complete in a reasonable time
    on one of this session's own real book fixtures). The DECISION the DP
    makes is unchanged either way; only how the same gap number is computed
    differs. A given numeral value may legitimately
    appear as MULTIPLE candidates (a running page-header repeating a
    chapter's own title through its body, a front-matter TOC-restatement
    cluster, a genuine phantom) -- this function does NOT dedupe them
    beforehand; the DP below decides which one, if any, belongs in the
    winning chain.

    DP recurrence, evaluated for each candidate i in ascending-offset
    order: only a value-1 candidate may START a chain on its own (seeded to
    length 1, max_gap 0, no predecessor) -- this is not a separate special
    case needing its own branch in the loop below, since no earlier
    candidate j can ever have value_j < 1, so the "values must strictly
    increase" check the general loop already applies would reject every
    possible predecessor for a value-1 candidate anyway; the explicit seed
    just avoids leaving a value-1 candidate at None when nothing else can
    ever produce a chain for it. For every other candidate i, considering
    each EARLIER candidate j (offset_j < offset_i) with a valid chain of
    its own (best[j] is not None): the link i<-j is valid only if value_i
    strictly exceeds value_j AND there are at least
    NUMERAL_MIN_CONTENT_GAP_WORDS words of body text between them
    (word_count(text[offset_j:offset_i])) -- this second condition is what
    invalidates a link between two members of a front-matter TOC-
    restatement cluster or two same-value running-header repeats sitting
    almost back-to-back, without needing any other signal to tell "real"
    from "phantom" candidates apart. Among all valid predecessors, keep the
    one that maximizes chain LENGTH first, and among equal-length options
    minimizes the chain's own largest single link-gap (never "prefer the
    latest occurrence" -- see below for why).

    WHY min-max-gap, not prefer-latest: consider a book whose real Chapter
    I heading is followed, deep inside chapter I's own body, by phantom
    "headings" that happen to satisfy every discriminator (a mid-book
    recap restating "II. ..." and "III. ..." as rhetorical section labels,
    for instance) at exactly the values chapters II and III would
    otherwise use. A chain that routes through those phantoms to reach
    chapter IV can tie in LENGTH with the chain that uses the real chapter
    II/III headings instead (both visit exactly the same set of distinct
    values). But the phantom-routed chain's own last link -- from the
    LATE phantom position back up to chapter IV's real, much-later
    position -- must span everything chapters II and III's own real bodies
    would have contained, since that content was never "spent" on the
    skipped real headings; that ONE link's gap is necessarily far larger
    than the largest gap in a chain of ordinary, evenly-sized chapter
    bodies. Minimizing the chain's own worst single gap is what correctly
    picks the real-heading chain over the phantom-routed one -- this
    reasoning is not merely assumed; see this module's own numeral-
    detection test suite for the real book (Andrew Murray's "The School of
    Obedience") this was verified against directly.

    Final tiebreak among chains still tied on (length, -max_gap): the
    SMALLEST starting offset -- i.e., among all candidate END-points i
    achieving the best (length, -max_gap) score, backtrack each one fully
    and prefer whichever full chain begins at the earliest document
    position (relevant when more than one value-1 candidate exists, e.g. a
    front-matter TOC restatement's own "I." next to the real "I."
    heading -- each seeds an independent chain, and this tiebreak applies
    if two competing full chains ever end up exactly tied otherwise).

    Returns the winning chain's candidates as {"value", "line_start_offset",
    "raw_label"} dicts, in document order -- [] if no candidate has value 1
    at all (nothing can ever start a chain). Pure function: no DB, no LLM,
    no network."""
    n = len(candidates)
    # best[i] = None, or (length, chain_start_offset, max_gap, prev_index).
    # chain_start_offset is THREADED through every step (inherited unchanged
    # from the chosen predecessor, exactly like max_gap already is) so that
    # span = candidates[i][0] - chain_start_offset is available -- and
    # compared -- at EVERY internal step, not only once at the very end.
    # This is a deliberate, verified departure from the simpler "compare
    # span only at final selection" approach: that simpler version was
    # implemented and tested FIRST, against School of Obedience specifically
    # -- it did NOT change that book's result at all, because the flawed
    # subsection-cluster chain already displaces the real, wider chain
    # INSIDE this loop (at the exact node where both chains, tied in
    # length, first converge -- see the WHY block below) long before any
    # final-only comparison ever runs. Comparing span at every step is what
    # actually lets the wider, earlier-starting real chain win at that
    # convergence point.
    best: List[Optional[Tuple[int, int, int, Optional[int]]]] = [None] * n

    for i in range(n):
        offset_i, value_i, _label_i, line_idx_i = candidates[i]
        if value_i == 1:
            best[i] = (1, offset_i, 0, None)
        for j in range(i):
            if best[j] is None:
                continue
            _offset_j, value_j, _label_j, line_idx_j = candidates[j]
            if value_i <= value_j:
                continue
            gap_words = cum_words[line_idx_i] - cum_words[line_idx_j]
            if gap_words < NUMERAL_MIN_CONTENT_GAP_WORDS:
                continue
            j_length, j_start, j_max_gap, _j_prev = best[j]
            candidate_length = j_length + 1
            candidate_start = j_start  # inherited unchanged -- span is a
            # property of the WHOLE chain from its own seed, never reset
            # partway through an extension.
            candidate_max_gap = max(j_max_gap, gap_words)
            candidate_span = offset_i - candidate_start
            if best[i] is None:
                current_key = None
            else:
                cur_length, cur_start, cur_max_gap, _cur_prev = best[i]
                current_key = (cur_length, offset_i - cur_start, -cur_max_gap)
            candidate_key = (candidate_length, candidate_span, -candidate_max_gap)
            if best[i] is None or candidate_key > current_key:
                best[i] = (candidate_length, candidate_start, candidate_max_gap, j)

    best_score: Optional[Tuple[int, int, int]] = None
    tied_indices: List[int] = []
    for i in range(n):
        if best[i] is None:
            continue
        length_i, start_i, max_gap_i, _prev_i = best[i]
        span_i = candidates[i][0] - start_i
        key = (length_i, span_i, -max_gap_i)
        if best_score is None or key > best_score:
            best_score = key
            tied_indices = [i]
        elif key == best_score:
            tied_indices.append(i)

    if not tied_indices:
        return []
    # Final determinism tiebreak among still-tied complete chains: earliest
    # first_offset (best[i][1] is already each candidate's own chain_start,
    # no backtracking needed to find it).
    chosen_idx = min(tied_indices, key=lambda i: best[i][1])

    chain_indices: List[int] = []
    cur: Optional[int] = chosen_idx
    while cur is not None:
        chain_indices.append(cur)
        cur = best[cur][3]
    chain_indices.reverse()

    return [
        {"value": candidates[idx][1], "line_start_offset": candidates[idx][0], "raw_label": candidates[idx][2]}
        for idx in chain_indices
    ]


def _detect_numeral_heading_sequence(text: str) -> dict:
    """Detects a single-occurrence numeral/roman-numeral chapter-heading
    SEQUENCE in `text`. Recognizes exactly two line shapes (see the regexes
    above), scanned in document order against each stripped line, with each
    raw match run through 5 discriminators BEFORE it is even considered a
    candidate for the chain-selection DP below:

      1. The line itself is <=130 chars AND <=20 words (an independent
         backstop beyond the regexes' own bounded title-length capture --
         widened from the original 64/12 specifically to accommodate
         longer real CHAPTER-WORD titles once that pattern's own bound was
         widened below; this mainly affects chapter-word matches, since
         roman-dot's own regex bound is tighter and unchanged).
      2. Structural (no runtime check needed) -- see the regex comments
         above: the roman-numeral portion can only ever be uppercase, and
         the chapter-word keyword can only ever be "Chapter"/"CHAPTER".
      3. For the ROMAN-DOT pattern specifically (not chapter-word), the
         title text must start with a capital letter -- rejects a
         lowercase sentence-continuation false match (e.g. Ryle's inline
         "II. I pass on to the second thing..." -- rejected outright at the
         regex-match stage in that specific real case, since its own title
         portion exceeds the UNCHANGED 58-char roman-dot bound; this
         discriminator is a second, independent guard for a SHORT-but-
         lowercase false match). A leading quote character (the curly ones
         from _CURLY_QUOTE_MAP's own keys, plus straight "/') is stripped
         from the title text FIRST, so a real quoted chapter title (e.g.
         Ryle's '"Lovest Thou Me?"') is judged by its first REAL letter,
         not by the leading punctuation mark.
      4. The line must NOT end in a trailing bare number (a Table-of-
         Contents page number, e.g. "I. CARNAL CHRISTIANS. 3").
      5. The candidate must be immediately followed by real prose -- a line
         >=50 chars within the next 3 non-blank lines after it (confirms
         this is an in-body heading directly before chapter text, not a
         cluster of short TOC lines).

    Surviving candidates then go through _select_numeral_chain() -- a
    two-pass, gap-validated DP replacing this function's original GREEDY
    "first occurrence of each value wins" walk. The greedy walk could not
    prefer a real heading over an earlier phantom/TOC-restatement that
    happened to satisfy every discriminator and share the same numeral
    value (confirmed twice against real books this session); the DP
    instead selects the LONGEST strictly-value-increasing chain, requiring
    at least NUMERAL_MIN_CONTENT_GAP_WORDS words of real body text between
    any two linked candidates, and tie-broken by MINIMUM worst-single-gap
    (never "prefer the latest occurrence") -- see _select_numeral_chain()'s
    own docstring for the full mechanism and why that specific tiebreak is
    load-bearing, not an arbitrary choice.

    Confidence ("confident": True) requires ALL of:
      - len(accepted) >= NUMERAL_MIN_ACCEPTED (3)
      - accepted[0]["value"] == 1
      - len(accepted) >= NUMERAL_MIN_COVERAGE_RATIO (0.6) * max_value
      - no gap > NUMERAL_MAX_GAP (3) between consecutive ACCEPTED values

    (Unchanged by the DP replacement -- these guards now simply operate on
    the DP's own chosen chain instead of the old greedy chain.) This is
    what rejects Doug Kreighbaum's "Manual Systematic Theology" (whose body
    uses "Chapter N" for SCRIPTURE chapter references, not book chapters,
    producing an accepted sequence like [1, 2, 500]) -- a huge gap AND
    near-zero coverage both fail independently, landing on needs_eyeball
    rather than a confident wrong answer.

    Returns a dict: {"confident": bool, "accepted": [{"value": int,
    "line_start_offset": int, "raw_label": str}, ...] (post-DP-selection,
    document order), "max_value": int, "gaps": List[int], "why": str}.

    Pure function: no DB, no LLM, no network."""
    lines = text.split("\n")
    line_offsets: List[int] = []
    pos = 0
    for line in lines:
        line_offsets.append(pos)
        pos += len(line) + 1

    # Prefix-sum word count over lines -- cum_words[k] == total word count
    # across lines[0:k] -- passed to _select_numeral_chain() so its O(n^2)
    # gap computation is O(1) per pair instead of O(gap length); see that
    # function's own docstring for why this matters at real-book scale.
    cum_words: List[int] = [0] * (len(lines) + 1)
    for k, line in enumerate(lines):
        cum_words[k + 1] = cum_words[k] + len(line.split())

    def _followed_by_real_prose(line_idx: int) -> bool:
        seen = 0
        for j in range(line_idx + 1, len(lines)):
            candidate_line = lines[j].strip()
            if not candidate_line:
                continue
            seen += 1
            if len(candidate_line) >= 50:
                return True
            if seen >= 3:
                break
        return False

    raw_candidates: List[Tuple[int, int, str, int]] = []  # (line_start_offset, value, raw_label, line_idx)
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        roman_match = _ROMAN_DOT_HEADING_RE.match(line)
        if roman_match:
            numeral_str, title_group = roman_match.group(1), roman_match.group(2)
        else:
            chapter_match = _CHAPTER_WORD_HEADING_RE.match(line)
            if not chapter_match:
                continue
            numeral_str, title_group = chapter_match.group(1), chapter_match.group(2)

        # Discriminator 1 (widened -- see this function's own docstring).
        if len(line) > 130 or len(line.split()) > 20:
            continue

        # Discriminator 3 -- roman-dot pattern only, per this function's
        # own design brief. Strips a leading quote character (curly or
        # straight) before checking the first REAL character is uppercase.
        if roman_match:
            title_check = title_group
            if title_check and title_check[0] in _LEADING_TITLE_QUOTE_CHARS:
                title_check = title_check[1:]
            if not (title_check and title_check[0].isupper()):
                continue

        # Discriminator 4.
        if _TRAILING_BARE_NUMBER_RE.search(line):
            continue

        value = int(numeral_str) if numeral_str.isdigit() else _roman_to_int(numeral_str)
        if value is None:
            continue

        # Discriminator 5.
        if not _followed_by_real_prose(i):
            continue

        raw_candidates.append((line_offsets[i], value, line, i))

    accepted = _select_numeral_chain(raw_candidates, cum_words)

    max_value = accepted[-1]["value"] if accepted else 0
    gaps = [accepted[k + 1]["value"] - accepted[k]["value"] for k in range(len(accepted) - 1)]

    doc_span_fraction = 0.0
    if accepted and len(text) > 0:
        doc_span_fraction = (
            accepted[-1]["line_start_offset"] - accepted[0]["line_start_offset"]
        ) / len(text)

    confident = (
        len(accepted) >= NUMERAL_MIN_ACCEPTED
        and bool(accepted) and accepted[0]["value"] == 1
        and max_value > 0 and len(accepted) >= NUMERAL_MIN_COVERAGE_RATIO * max_value
        and all(g <= NUMERAL_MAX_GAP for g in gaps)
        and doc_span_fraction >= NUMERAL_MIN_DOC_SPAN_FRACTION
    )

    if confident:
        why = (
            "confident: {0} accepted starting at 1, coverage {0}/{1} = {2:.0%}, "
            "max gap {3}, doc span {4:.0%}".format(
                len(accepted), max_value,
                (len(accepted) / max_value) if max_value else 0.0,
                max(gaps) if gaps else 0,
                doc_span_fraction,
            )
        )
    else:
        reasons = []
        if len(accepted) < NUMERAL_MIN_ACCEPTED:
            reasons.append("only {0} accepted candidate(s) (need >= {1})".format(
                len(accepted), NUMERAL_MIN_ACCEPTED))
        if accepted and accepted[0]["value"] != 1:
            reasons.append("sequence starts at {0}, not 1".format(accepted[0]["value"]))
        if max_value and len(accepted) < NUMERAL_MIN_COVERAGE_RATIO * max_value:
            reasons.append("coverage {0}/{1} = {2:.0%} < {3:.0%}".format(
                len(accepted), max_value, len(accepted) / max_value, NUMERAL_MIN_COVERAGE_RATIO))
        if gaps and max(gaps) > NUMERAL_MAX_GAP:
            reasons.append("gap of {0} between consecutive accepted values (max allowed {1})".format(
                max(gaps), NUMERAL_MAX_GAP))
        if accepted and doc_span_fraction < NUMERAL_MIN_DOC_SPAN_FRACTION:
            reasons.append("doc span {0:.1%} < required {1:.0%} (chain covers too little of "
                            "the whole document to be the real top-level structure)".format(
                                doc_span_fraction, NUMERAL_MIN_DOC_SPAN_FRACTION))
        if not reasons:
            reasons.append("no candidates found at all")
        why = "; ".join(reasons)

    return {
        "confident": confident, "accepted": accepted, "max_value": max_value, "gaps": gaps,
        "doc_span_fraction": doc_span_fraction, "why": why,
    }


def _build_numeral_chapters(
    text: str,
    offset_map: List[Tuple[str, int, int]],
    accepted: List[dict],
) -> List[ChapterSpan]:
    """Builds ChapterSpans from _detect_numeral_heading_sequence()'s own
    accepted candidate list -- reuses the EXISTING ChapterSpan shape, the
    EXISTING _label_from_context()/preface_pre_boundary convention
    split_book_into_chapters() itself already uses for content preceding
    its own first detected boundary, and the EXISTING
    _chunk_ids_overlapping() chunk-offset-mapping helper -- none of these
    are reforked. New split_method value: "numeral_heading_boundary"."""
    chapters: List[ChapterSpan] = []
    first_start = accepted[0]["line_start_offset"]
    if first_start > 0:
        pre_text = text[0:first_start]
        if pre_text.strip():
            chapters.append(ChapterSpan(
                label=_label_from_context(pre_text),
                char_start=0, char_end=first_start, text=pre_text,
                chunk_ids=_chunk_ids_overlapping(offset_map, 0, first_start),
                split_method="preface_pre_boundary",
            ))

    for idx, cand in enumerate(accepted):
        b_start = cand["line_start_offset"]
        b_end = accepted[idx + 1]["line_start_offset"] if idx + 1 < len(accepted) else len(text)
        span_text = text[b_start:b_end]
        chapters.append(ChapterSpan(
            label=cand["raw_label"],
            char_start=b_start, char_end=b_end, text=span_text,
            chunk_ids=_chunk_ids_overlapping(offset_map, b_start, b_end),
            split_method="numeral_heading_boundary",
        ))
    return chapters


class BookStructureResult(NamedTuple):
    """Return shape for detect_book_chapters() -- see that function's own
    docstring for the full decision logic.

    status      -- "repeat_detected" (the EXISTING split_book_into_
                   chapters() repeat-marker result is authoritative --
                   R >= 3, or the numeral detector didn't beat it),
                   "numeral_detected" (the new single-occurrence numeral/
                   roman-numeral heading-sequence detector fired instead),
                   or "needs_eyeball" (neither detector produced a
                   confident result).
    chapters    -- List[ChapterSpan], reusing the EXISTING ChapterSpan
                   shape unchanged. None IFF status == "needs_eyeball" --
                   never a guessed/partial list for a low-confidence book.
    detector    -- "title_repeat_boundary" | "numeral_heading_boundary" |
                   "none" -- names which split_method value the spans in
                   `chapters` actually carry (for "repeat_detected", this
                   is the EXISTING split_book_into_chapters() result
                   verbatim -- it may still legitimately contain
                   "preface_pre_boundary"/"size_fallback" spans alongside
                   "title_repeat_boundary" ones, exactly as that function
                   already produces; "detector" here just names which
                   overall path was chosen, not that every single span
                   shares one split_method value), or "none" for
                   needs_eyeball.
    diagnostics -- dict: {"R": int, "N": int, "max_value": int,
                   "gaps": List[int], "numeral_confident": bool,
                   "why": str} -- always present regardless of status, so a
                   caller can see WHY a given status was chosen even when
                   it's the confident one."""
    status: str
    chapters: Optional[List[ChapterSpan]]
    detector: str
    diagnostics: dict


def detect_book_chapters(ordered_chunks: List[Tuple[str, str]]) -> BookStructureResult:
    """Top-level book-structure-detection entry point, combining the
    EXISTING repeat-marker detector (split_book_into_chapters(), called
    here UNMODIFIED) with the NEW single-occurrence numeral-heading
    detector (_detect_numeral_heading_sequence(), see its own docstring)
    above.

    R (the repeat-detector's own "real chapter count") is the count of
    split_book_into_chapters()'s own returned spans whose split_method is
    exactly "title_repeat_boundary" AND which the ALREADY-COMMITTED,
    UNMODIFIED is_front_back_matter() would NOT classify as matter --
    front/back-matter spans (a repeated "Indexes"/"Title Page" marker,
    etc.) must never inflate R, or a book with real front matter but few
    or no real repeat-detected chapters could wrongly look "repeat_detected
    enough" on paper.

    N is _detect_numeral_heading_sequence()'s own len(accepted) count,
    computed against the SAME reconstructed text (via
    _build_chunk_offset_map(), the same helper split_book_into_chapters()
    itself uses -- reused, not reforked).

    Decision, in this exact order:
      1. If the numeral detector is confident AND N > R -> "numeral_detected"
         (the numeral detector found strictly MORE real chapters than the
         repeat detector did for this same book -- it wins).
      2. Elif R >= 3 -> "repeat_detected", returning split_book_into_
         chapters()'s own result VERBATIM, completely unchanged -- this is
         what guarantees byte-identical behavior for every already-clean
         book: for those books this branch fires and NOTHING about the
         returned chapters list differs from calling split_book_into_
         chapters() directly.
      3. Elif the numeral detector is confident (which already implies
         N >= 3, per its own confidence criteria) -> "numeral_detected".
      4. Else -> "needs_eyeball", chapters=None.

    Pure function: no DB, no LLM, no network -- callers supply
    ordered_chunks themselves, same convention as split_book_into_
    chapters()."""
    chapters_r, _missing = split_book_into_chapters(ordered_chunks)
    R = sum(
        1 for c in chapters_r
        if c.split_method == "title_repeat_boundary"
        and not is_front_back_matter(c.label, c.text)[0]
    )

    text, offset_map = _build_chunk_offset_map(ordered_chunks)
    numeral_result = _detect_numeral_heading_sequence(text)
    N = len(numeral_result["accepted"])
    numeral_confident = numeral_result["confident"]

    diagnostics = {
        "R": R,
        "N": N,
        "max_value": numeral_result["max_value"],
        "gaps": numeral_result["gaps"],
        "doc_span_fraction": numeral_result["doc_span_fraction"],
        "numeral_confident": numeral_confident,
        "why": numeral_result["why"],
    }

    if numeral_confident and N > R:
        chapters = _build_numeral_chapters(text, offset_map, numeral_result["accepted"])
        return BookStructureResult("numeral_detected", chapters, "numeral_heading_boundary", diagnostics)

    if R >= 3:
        return BookStructureResult("repeat_detected", chapters_r, "title_repeat_boundary", diagnostics)

    if numeral_confident:
        chapters = _build_numeral_chapters(text, offset_map, numeral_result["accepted"])
        return BookStructureResult("numeral_detected", chapters, "numeral_heading_boundary", diagnostics)

    return BookStructureResult("needs_eyeball", None, "none", diagnostics)
