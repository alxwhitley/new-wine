#!/usr/bin/env python3
"""
positions.py -- position layer foundation (PLAN.md #48, Phase 4 opening
session, 2026-07-28). Generates and stores a teacher-specific position: a
reviewable summary of what one teacher teaches on one topic, built from
that teacher's own eligible statements (propositions) only.

--------------------------------------------------------------------------
Structural guarantee: generation cannot see source/chunk text
--------------------------------------------------------------------------
generate_position_text() -- the only function that calls the LLM -- takes
exactly (teacher_name: str, topic: str, evidence: List[dict]), where each
evidence dict is {"id": <proposition uuid str>, "content": <already-
paraphrased statement text>}. It opens no database connection, imports
nothing that reads `chunks` or `documents`, and receives no document_id or
source_id. There is no parameter through which source/chunk text could
reach it -- this is enforced by the function's signature, not by a prompt
instruction telling the model to ignore something it was never given. The
one function that DOES touch the database, gather_evidence(), reads only
from `propositions` (never `chunks`) and hands generate_position_text()
nothing but that table's own `content` column.

--------------------------------------------------------------------------
Two scopes ('teacher' | 'corpus'): still double-locked
--------------------------------------------------------------------------
Corpus-wide positions were BANNED until 2026-08-01, then UNBANNED on Alex's
explicit decision that day (the #49 backfill -- 850/857 eligible documents,
incl. 477 of Derek Prince's -- satisfied the precondition CLAUDE.md
Invariant 13 named; the original ban existed because a corpus-wide position
authored before Prince's material landed would have named whichever teachers
happened to already have statements as "the corpus" and inverted the day his
documents were processed). A position's scope is now one of exactly two
values, and that set is still enforced twice, not once: write_position()
raises ValueError before ever opening a transaction if kind is not in
('teacher','corpus') (this module's own gate), AND the `positions` table's
CHECK (kind IN ('teacher','corpus')) constraint (migration 076, widened from
073's teacher-only lock) would reject the INSERT even if this module's own
gate were bypassed or forked. Widening to a THIRD scope requires a
deliberate code change AND a migration, never a runtime flag -- both locks
have to agree. A teacher position names exactly one source (source_id NOT
NULL); a corpus position names none (source_id NULL) and derives its
contributing teachers from its evidence -- enforced by migration 076's
scope/source coupling CHECK.

--------------------------------------------------------------------------
Honest-empty: the evidence-count floor
--------------------------------------------------------------------------
MIN_EVIDENCE_COUNT = 5. Chosen empirically against real Vlad Savchuk
evidence-gathering results at SIMILARITY_FLOOR = 0.4 (see this session's
report for the full density table): genuinely dense topics ("deliverance
from demons and spiritual warfare", "how to pray effectively") cleared
20-50 statements; genuinely thin-but-real topics ("church leadership
structure", 7; "predestination and Calvinist double election theology", 4)
sat in the low single digits; topics genuinely absent from Savchuk's corpus
("infant baptism and the sacraments", "liturgical calendar") returned ZERO.
5 sits just above that thin/absent boundary -- low enough not to block a
real but narrow position, high enough that a position is never built from
1-2 statements (which would be indistinguishable from restating a single
proposition, not a genuine cross-corpus position). This floor has NOT been
calibrated the way CONTAINMENT_FLOOR/LONGEST_RUN_WORD_THRESHOLD were
(PLAN.md #46-style human calibration against many teachers) -- it is a
reasoned starting point from one teacher's real data, explicitly flagged as
provisional, same posture PLAN.md #45's floors had before their own #46.
Re-checked, not re-derived, by the 2026-07-28 calibration diagnostic below
(38 real questions, 4 teachers, question-scoped gathering): raising this
floor to 10 fixed none of the diagnostic's confirmed false passes -- each
had far more than 10 loosely-related matches already -- while breaking a
genuine answer. The floor is not the lever that controls whether gathered
evidence actually answers the question; SIMILARITY_FLOOR is. Left at 5,
unchanged, on that evidence.

--------------------------------------------------------------------------
SIMILARITY_FLOOR: 0.4 -> 0.45, 2026-07-28 calibration diagnostic
--------------------------------------------------------------------------
SIMILARITY_FLOOR is a SEPARATE, secondary parameter from MIN_EVIDENCE_COUNT
-- not the honest-empty floor itself, just the relevance cutoff used to
gather candidates before the count floor is checked. Reused as a starting
point from TEACHER_POSITION_SIMILARITY_FLOOR (study.py, = 0.3) is
deliberately NOT done here -- PLAN.md #48 already states that floor "was
tuned for the current retrieval path and does not transfer." Originally set
to 0.4 (this module's opening Vlad Savchuk proof, above).

Raised to 0.45 (2026-07-28, Alex's ruling on
docs/audits/position_layer_calibration_diagnostic_2026-07-28.md) after a
38-question, 4-teacher diagnostic run at question-scoped gathering --
embedding a real question, not a short topic label, then measuring how much
of a teacher's evidence clears each candidate bar -- found 0.4 let through 3
confirmed false-pass fabrication cases (evidence that is topically related
but does not actually address the question asked, e.g. general
salvation/relationship material passing as an answer to a specific
doctrinal question none of the three teachers tested actually addresses).
0.45 fixes all 3 at the cost of 1 additional, already-borderline refusal.
0.50 was also tested and rejected: it fixes every false pass in the
diagnostic but also breaks 5 separate questions the teacher genuinely does
answer well -- an unacceptable trade the other direction. See the report
for the full per-question sweep.

0.45 is a starting point, not a settled constant -- it is empirically
derived from 38 constructed questions, not from real user traffic (there is
none yet; the position layer does not serve users). The diagnostic itself
found this bar cannot fully close the near-miss gap even at 0.45 (two
Savchuk cases -- child custody, fasting for weight loss -- still clear it);
see PLAN.md's position-layer section for why that residual has to be
handled at the writing stage, not here. Revisit this value once real
questions accumulate, per the diagnostic's own recommendation.

--------------------------------------------------------------------------
Provenance: NOT NULL from this table's first row
--------------------------------------------------------------------------
Every position row stamps prompt_version, prompt_fingerprint (SHA-256 of
the exact template text, computed fresh every call, never hand-maintained --
same authoritative-over-the-label design as propositions.prompt_
fingerprint()), and model. The positions table (migration 073) makes all
three NOT NULL -- an unstamped write is impossible here, not just
discouraged (contrast propositions.prompt_version, nullable, which is why
every one of the 2,409 live propositions has NULL provenance today).

There are now TWO instruction templates, not one: POSITION_PROMPT
("position_v2") for ordinary topics, and TENSION_MODE_PROMPT
("position_tension_v2") for the single, narrow, hard-coded Calvinism/
predestination exception (PLAN.md #48 item 3, 2026-07-30) -- see
is_calvinism_predestination_topic() and _prompt_and_version_for_topic()
below. Exactly one function, _prompt_and_version_for_topic(), decides both
which prompt gets sent to the model AND which version label / fingerprint
gets stamped on the written row -- generate_position_text() and
write_position() both call it rather than each independently deciding, so
the two can never disagree (the class of bug this guards against: a call
silently generating with TENSION_MODE_PROMPT while the write stamps
POSITION_PROMPT's fingerprint, mislabeling every tension-mode row's
provenance -- exactly what CLAUDE.md Invariant 10 exists to prevent). The
fingerprint always tracks whichever template actually fired for that row,
computed fresh from that template's literal text, never hand-maintained.

Both templates were bumped v1 -> v2 (PLAN.md #48 item 4, 2026-07-30) to add
a shared, standing premise-correction instruction: PREMISE_CORRECTION_CLAUSE,
defined once and referenced by both templates via substitution into the
shared base template at module load time (never hand-duplicated separately
in each), inserted as its own paragraph between the FOUR CORNERS paragraph
and the "Write ONE position..." paragraph in both. It tells the model to
name a gap plainly, woven into the substantive teaching rather than as a
meta-preamble, when the gathered evidence complicates or contradicts an
assumption built into the question as asked -- keyed explicitly on what
the gathered statements show, never on "if the premise is false" in the
abstract, to avoid making this a leakage vector for the model's own
outside knowledge (Open Decision #20). The version bump reflects that the
wording materially changed; three pre-existing "position_v1" rows from the
2026-07-28 opening proof remain in the table untouched -- nothing rewrites
old rows -- so v2 also keeps new rows' provenance from being conflated
with those three.

--------------------------------------------------------------------------
Repair 1 (2026-07-30): one shared base template, not two hand-duplicated
prompts
--------------------------------------------------------------------------
Until this fix, POSITION_PROMPT and TENSION_MODE_PROMPT were two separate
f-strings, each typed out in full -- every paragraph they share (the
opening sentence, the "you will be given..." sentence, the FOUR CORNERS
rule, the paraphrase-discipline paragraph, the single-teacher-only hedge,
and the closing "no preamble" line) existed as two hand-maintained copies,
kept in sync only by hand -- the same failure shape already on record for
the book-name map in CLAUDE.md's Landmines. BASE_TEMPLATE now holds that
shared text exactly ONCE, as a plain (non-f-string) .format()-style
template -- an f-string evaluates its substitutions immediately and can't
be reused as a fill-in-later template for two different final strings.
POSITION_PROMPT and TENSION_MODE_PROMPT are both now produced by formatting
BASE_TEMPLATE with two substitution points: PREMISE_CORRECTION_CLAUSE
(unchanged, still one shared constant, wired into the base template instead
of being embedded separately in each former per-prompt f-string) and a new
per-mode RESOLUTION_INSTRUCTION_ORDINARY / RESOLUTION_INSTRUCTION_TENSION
constant holding just the one "Write ONE position..." paragraph that is
actually supposed to differ between the two modes. This is a pure
structural/dedup refactor -- both final prompt strings are byte-identical,
confirmed by SHA-256, to what they were immediately before this change; no
wording changed as part of it.

--------------------------------------------------------------------------
Repair 2 (2026-07-30): tension-mode wording fix, "verbatim" -> "explicitly
states" (v2 -> v3, TENSION_MODE_PROMPT only)
--------------------------------------------------------------------------
RESOLUTION_INSTRUCTION_TENSION's exception clause previously read "...unless
the teacher has verbatim stated an explicit position, in which case state
that position." "Verbatim" reads as requiring an exact quoted match against
the teacher's original wording -- but the model is only ever handed already-
paraphrased propositions.content (never the teacher's original wording, see
this file's own structural-guarantee section above), so no such match is
ever actually checkable, and the literal instruction risked either being
impossible to satisfy or being interpreted loosely in a way the word
"verbatim" doesn't honestly describe. The bar this exception is meant to
gate on has always been explicitness of statement, not exactness of
phrasing -- corrected to "...unless the statements themselves explicitly
state a position, in which case state that position." TENSION_MODE_PROMPT_
VERSION bumped v2 -> v3 to reflect this same v1->v2 convention (wording
materially changed, so provenance for rows generated under the old wording
must not be conflated with rows generated under the new one). POSITION_
PROMPT / PROMPT_VERSION are untouched by this repair -- it only affects the
tension-mode branch.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.embeddings import embed_text  # noqa: E402
from app.services.llm_client import get_anthropic_client, get_guardrails_text, get_generation_model  # noqa: E402
from app.services.dominance import DOMINANCE_THRESHOLD, determine_scope  # noqa: E402,F401

PROMPT_VERSION = "position_v2"
TENSION_MODE_PROMPT_VERSION = "position_tension_v3"

SIMILARITY_FLOOR = 0.45
MAX_EVIDENCE = 15
MIN_EVIDENCE_COUNT = 5

# --------------------------------------------------------------------------
# Scope determination (PLAN.md #48 serving-path session, 2026-08-01)
# --------------------------------------------------------------------------
# DOMINANCE_THRESHOLD and determine_scope() now live in
# app.services.dominance (relocated 2026-08-06, PLAN.md v5.24 step 2) --
# imported above, not redefined here, so this module and
# app.services.single_teacher_lock (the retrieval-time lock) can never
# independently drift on the dominance threshold or its Counter logic. See
# that module's own docstring for the full reasoning and the value's
# provenance. Re-exported under these same names so every existing
# `positions.DOMINANCE_THRESHOLD` / `positions.determine_scope` call site
# (scripts/serve_position.py, scripts/test_serve_position.py) is unaffected.


def normalize_topic_key(topic: str) -> str:
    """Normalized lookup key for a position's topic: collapse every whitespace
    run to a single space, then trim, then lowercase.

    MUST match migration 077's SQL -- lower(btrim(regexp_replace(topic,
    '\\s+', ' ', 'g'))) -- byte-for-byte. The two are ONE contract, the same
    posture as normalize_alias_key / migration 050 (CLAUDE.md Invariant 6):
    if the app's key and the stored key ever disagree, lookups miss silently
    and the serving path regenerates a position that already exists. This is a
    SEPARATE normalization from alias keys -- deliberately NOT reusing or
    forking normalize_alias_key, which serves a different contract.

    Collapse BEFORE trim is deliberate: Python str.strip() removes all
    leading/trailing whitespace, but SQL btrim removes only spaces, so a
    leading tab must first become a space (via the collapse) for the two to
    agree."""
    return re.sub(r"\s+", " ", topic).strip().lower()

# --------------------------------------------------------------------------
# Premise-correction clause (PLAN.md #48 item 4, 2026-07-30)
# --------------------------------------------------------------------------
# Shared by BOTH POSITION_PROMPT and TENSION_MODE_PROMPT -- defined once,
# referenced twice via substitution into the shared BASE_TEMPLATE at module
# load time, never hand-duplicated as separate literal text in each
# template (a hand-duplicated copy could silently drift out of sync
# between the two the way the book-name map already has -- see CLAUDE.md
# Landmines). Keys explicitly on "the gathered statements" (the evidence
# actually handed to the model), never on "if the premise is false" in the
# abstract -- this is what stops it from becoming a leakage vector: the
# model correcting a premise from its own outside knowledge rather than
# from what the evidence in front of it actually shows (the concern
# already on record as Open Decision #20). The correction must be woven
# into the substantive teaching -- Draft 7's own shape: stating the
# teacher's actual view, which happens to correct the premise, as part of
# the teaching itself -- never a meta-preamble ("this question assumes X,
# but ..."), which would directly collide with both templates' existing
# "no preamble, no meta-commentary" closing line.
PREMISE_CORRECTION_CLAUSE = (
    "If the gathered statements complicate, correct, or contradict an "
    "assumption built into the question as asked, name that gap plainly "
    "before teaching from what the statements actually say — do not "
    "silently answer the assumption as if it were true, and do not "
    "silently ignore it either."
)


# --------------------------------------------------------------------------
# Shared base prompt template (Repair 1, 2026-07-30)
# --------------------------------------------------------------------------
# BASE_TEMPLATE holds every paragraph that used to be typed out identically
# in both POSITION_PROMPT and TENSION_MODE_PROMPT -- the opening sentence,
# the "you will be given..." sentence, the FOUR CORNERS governing rule, the
# paraphrase-discipline paragraph, the single-teacher-only hedge paragraph,
# and the closing "no preamble" line. Fingerprinted (via each fully-
# substituted final string) BEFORE any per-call teacher/topic substitution,
# same convention as propositions.py's prompt_fingerprint() (fingerprints
# the raw template text, not the speaker/topic-substituted version), so the
# fingerprint identifies "which wording of the instructions produced this
# row," independent of which teacher/topic a given call used. Sent as a
# system block alongside get_guardrails_text() -- the same shared
# theological-guardrails text every other LLM call that represents a
# source document's or teacher's views already uses (chat.py's answer
# stream, study.py's live teacher-card synthesis) -- reused here, not
# forked, so a position is held to the same guardrail standard as any
# other product surface that speaks in a teacher's voice.
#
# BASE_TEMPLATE is a plain (non-f-string) template using .format()-style
# placeholders, not an f-string -- an f-string evaluates its substitutions
# immediately at the point it's written and can't be reused as a fill-in-
# later template for two different final strings. It has exactly two
# substitution points: {premise_correction_clause} (PREMISE_CORRECTION_
# CLAUSE, already a shared constant above -- now wired into this one base
# template instead of being embedded separately in each of the two former
# per-prompt f-strings) and {resolution_instruction} (the one paragraph
# that is actually supposed to differ between ordinary and tension-mode
# generation -- see RESOLUTION_INSTRUCTION_ORDINARY / RESOLUTION_
# INSTRUCTION_TENSION below). POSITION_PROMPT and TENSION_MODE_PROMPT are
# now both produced by formatting this one template, never hand-typed
# twice -- the failure mode this closes is the same class as the book-name
# map drift already on record in CLAUDE.md's Landmines: two hand-maintained
# copies of "the same" text silently going out of sync over time as one
# gets edited and the other doesn't.
BASE_TEMPLATE = """\
You are writing a stored position: a summary of what a named teacher teaches on one topic, for a Bible-study research tool used by curious lay believers in the Spirit-filled tradition.

You will be given the teacher's name, a topic, and a set of already-paraphrased teaching statements extracted from that teacher's own material. These statements are your ONLY source of information about this teacher's teaching on this topic. You have no other knowledge of what this teacher has said, and you must not add anything beyond what the statements say.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is stated in the teaching statements you are given. Do not add scripture references, examples, or claims that are not in them. Do not draw on general theological knowledge to fill a gap. If the statements do not cover some angle of the topic, leave it out rather than infer it.

{premise_correction_clause}

{resolution_instruction}

Paraphrase. Do not quote the statements verbatim at length — restate them in connected prose, the same way the statements themselves already paraphrase their own source. A short (under roughly five word) precise phrase is fine only where it is genuinely how the teacher put a point in the evidence given to you.

This position represents the one named teacher only. Do not hedge as though other viewpoints exist unless the statements themselves show this teacher addressing a counter-view.

Output ONLY the position text — no preamble, no headers, no meta-commentary about the statements or the task."""


def prompt_fingerprint() -> str:
    return hashlib.sha256(POSITION_PROMPT.encode("utf-8")).hexdigest()


def _fingerprint(prompt_text: str) -> str:
    """SHA-256 of a literal template's own text. Same convention as
    prompt_fingerprint()/propositions.prompt_fingerprint() -- fingerprints
    the raw template, never a hand-maintained label -- factored out so
    _prompt_and_version_for_topic() is the one place that decides, for
    either branch, both which text is sent and what gets fingerprinted."""
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Per-mode resolution instruction (Repair 1, 2026-07-30; PLAN.md #48 item 3
# tension-mode exception originally added 2026-07-30)
# --------------------------------------------------------------------------
# The one paragraph BASE_TEMPLATE does NOT share between modes.
# RESOLUTION_INSTRUCTION_ORDINARY's "Write ONE position... Synthesize the
# distinct points... into one connected picture" instruction pushes toward
# resolution -- fine for most topics, but for Calvinism/predestination-
# adjacent topics it was confirmed (Draft 15, "predestination and
# unconditional election in the Calvinist sense" against Derek Prince's
# real evidence) to manufacture a one-sided resolution the teacher's own
# statements do not actually assert: "Prince resolves the tension between
# predestination and free will by appealing to..." -- stitching real
# statements into an over-resolved conclusion. RESOLUTION_INSTRUCTION_
# TENSION below replaces that one paragraph with a standing rule to
# present real tension as tension, not resolve it, unless the gathered
# statements themselves genuinely, explicitly state an explicit position --
# bumped to "position_tension_v3" (Repair 2, 2026-07-30) after the prior
# "verbatim stated" wording was found to read as requiring an exact quoted
# match, which is stricter than intended and not what this exception was
# ever meant to gate on: the bar is explicit statement of a position, not
# verbatim phrasing. Every other paragraph in the two final prompts
# (BASE_TEMPLATE's other paragraphs) is identical by construction now, not
# by hand-matching.
RESOLUTION_INSTRUCTION_ORDINARY = (
    "Write ONE position: a single coherent passage, roughly 100-200 words, "
    "stating what this teacher teaches about the given topic. Synthesize "
    "the distinct points across the statements into one connected picture "
    "— do not just concatenate them one after another, and do not just "
    "restate a single statement. Name the teacher at least once, "
    "naturally. Where the statements show a specific, memorable framing or "
    "a real qualification the teacher attaches, keep it — do not flatten a "
    "distinctive position into generic Christian consensus."
)

RESOLUTION_INSTRUCTION_TENSION = (
    "Write ONE position: a single coherent passage, roughly 100-200 words, "
    "stating what this teacher teaches about the given topic. Present what "
    "the teacher actually said, including any real tension between "
    "sovereignty/foreknowledge and free will, without resolving it into a "
    "side the teacher didn't take — unless the statements themselves "
    "explicitly state a position, in which case state that position. Do "
    "not just restate a single statement. Name the teacher at least once, "
    "naturally. Where the statements show a specific, memorable framing or "
    "a real qualification the teacher attaches, keep it — do not flatten a "
    "distinctive position into generic Christian consensus."
)

POSITION_PROMPT = BASE_TEMPLATE.format(
    premise_correction_clause=PREMISE_CORRECTION_CLAUSE,
    resolution_instruction=RESOLUTION_INSTRUCTION_ORDINARY,
)

TENSION_MODE_PROMPT = BASE_TEMPLATE.format(
    premise_correction_clause=PREMISE_CORRECTION_CLAUSE,
    resolution_instruction=RESOLUTION_INSTRUCTION_TENSION,
)


# --------------------------------------------------------------------------
# Corpus prompt (PLAN.md #48 serving-path session, 2026-08-01)
# --------------------------------------------------------------------------
# A SEPARATE template for corpus positions -- deliberately NOT a variant of
# BASE_TEMPLATE, because a corpus position is a materially different task:
# several named teachers, evidence LABELED per teacher, and the divergence
# rule (present real disagreement, never average past it) that has no analog
# in a single-teacher position. It is still source-blind by exactly the same
# mechanism as the teacher prompt: generate_corpus_position_text() (below)
# takes only a topic string and already-paraphrased proposition content plus
# plain teacher-NAME strings -- no source_id/document_id, no DB connection,
# no path to source/chunk text (CLAUDE.md Invariant 12, extended to cover
# this second generator).
#
# It reuses PREMISE_CORRECTION_CLAUSE verbatim (the one shared constant), and
# reuses the FOUR CORNERS rule, the paraphrase-discipline paragraph, and the
# no-preamble line verbatim from BASE_TEMPLATE. Those three are NOT factored
# into shared constants here (that would force re-fingerprinting the proven
# teacher prompts, which must stay byte-identical -- three live position_v1
# rows and the position_v2 fingerprint depend on it). Instead a regression
# test (test_positions.py) asserts these exact fragments appear in BOTH the
# teacher and corpus prompts, so a future edit to one that forgets the other
# fails loudly rather than drifting silently (the book-name-map failure shape,
# CLAUDE.md Landmines).
CORPUS_PROMPT_VERSION = "position_corpus_v1"

CORPUS_PROMPT = """\
You are writing a stored corpus position: a summary of what SEVERAL named teachers in a curated Bible-study research tool teach on one topic, for curious lay believers in the Spirit-filled tradition.

You will be given a topic and a set of already-paraphrased teaching statements. EACH statement is labeled, in square brackets, with the name of the teacher it came from. These labeled statements are your ONLY source of information about what these teachers teach on this topic. You have no other knowledge of what any of them has said, and you must not add anything beyond what the statements say.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is stated in the teaching statements you are given. Do not add scripture references, examples, or claims that are not in them. Do not draw on general theological knowledge to fill a gap. If the statements do not cover some angle of the topic, leave it out rather than infer it.

{premise_correction_clause}

Attribute views to the teachers who actually hold them, by name — the statements are labeled precisely so that you can. Write ONE position, roughly 150-250 words. Where the labeled statements show the teachers in genuine agreement, present that shared teaching together. Where they materially DISAGREE, present the disagreement plainly — name who holds which view — and do NOT resolve it into a blended middle, a split-the-difference compromise, or a consensus none of them actually stated. Do not imply agreement the statements do not show. Do not give a teacher who contributed a single passing statement the same standing as one who supplies the substance; let the balance of the position follow the balance of the evidence you were given.

Paraphrase. Do not quote the statements verbatim at length — restate them in connected prose, the same way the statements themselves already paraphrase their own source. A short (under roughly five word) precise phrase is fine only where it is genuinely how the teacher put a point in the evidence given to you.

Output ONLY the position text — no preamble, no headers, no meta-commentary about the statements or the task.""".format(
    premise_correction_clause=PREMISE_CORRECTION_CLAUSE
)


def is_calvinism_predestination_topic(topic: str) -> bool:
    """Case-insensitive substring match for the single, narrow tension-mode
    trigger. Deliberately NOT bare "election" -- that would over-trigger on
    generic "chosen by God" questions unrelated to the specific Calvinist
    doctrine."""
    t = topic.lower()
    triggers = (
        "calvinis",  # Calvinist / Calvinism / Calvinistic
        "predestination",
        "unconditional election",
        "double predestination",
    )
    return any(trigger in t for trigger in triggers)


def _prompt_and_version_for_topic(topic: str) -> Tuple[str, str]:
    """The ONE place that decides both which prompt gets sent to the model
    and what gets stamped as this row's provenance -- generate_position_
    text() and write_position() both call this rather than each separately
    re-deriving the same decision, so the two can never disagree (CLAUDE.md
    Invariant 10's principle, applied here)."""
    if is_calvinism_predestination_topic(topic):
        return TENSION_MODE_PROMPT, TENSION_MODE_PROMPT_VERSION
    return POSITION_PROMPT, PROMPT_VERSION


def _prompt_and_version(topic: str, kind: str) -> Tuple[str, str]:
    """Scope-aware extension of _prompt_and_version_for_topic(): the ONE place
    that decides, for EITHER scope, both which prompt is sent to the model and
    which version label is stamped on the written row. A corpus position
    always uses CORPUS_PROMPT (its own divergence handling subsumes the
    Calvinism tension-mode exception, which only exists to stop a
    single-teacher position from manufacturing a resolution -- a corpus
    position is required to present disagreement natively). A teacher position
    defers to the existing topic-based teacher selector. Both generators and
    write_position()/write_corpus_position() call THIS, so generation and
    provenance can never disagree (CLAUDE.md Invariant 10's principle)."""
    if kind == "corpus":
        return CORPUS_PROMPT, CORPUS_PROMPT_VERSION
    return _prompt_and_version_for_topic(topic)


def db_params() -> dict:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL not set in backend/app/.env")
    p = urlparse(db_url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/"),
    }


def _is_eligible(eligible, pid: str, content: str, doc_id: str) -> bool:
    """Polymorphic eligibility test. `eligible` may be a precomputed set of
    pass-both proposition IDs (membership test) OR an
    eligible_statements.EligibilityChecker (lazy per-candidate check). The
    lazy form is what makes the serving path viable -- the whole-corpus
    pass-both computation is far too slow to run at question time."""
    if hasattr(eligible, "is_eligible"):
        return eligible.is_eligible(pid, content, doc_id)
    return pid in eligible


# --------------------------------------------------------------------------
# License/visibility gate (2026-08-04, PLAN.md #48 step 3)
# --------------------------------------------------------------------------
# CLAUDE.md Invariant 2's exact predicate, reused verbatim -- not re-derived
# -- from migrations 049/056/065 and source_resolver.is_source_servable(), so
# gather_evidence()/gather_evidence_corpus() can never disagree with the rest
# of the product on which sources are servable. %s is the safe_mode_on
# boolean (see _read_safe_mode_on() -- read fresh every call, never cached,
# same discipline as is_source_servable()).
#
# Deliberately does NOT reference: documents.is_copyrighted (unreliable,
# Invariant 4 -- derived from folder path, wrong for e.g. Derek Prince's
# documents); citation_mode (a different concern, Invariant 7 -- attribution
# display, not rights); or sources.retrievable (a generated column confirmed
# INCONSISTENT with this exact predicate for a 'licensed' source -- see
# docs/audits/position_layer_revival_diagnostic_2026-08-04.md, Step 3 finding
# #5 -- currently dormant but not a substitute for this predicate).
LICENSE_GATE_SQL = """(
        s.license_status IN ('public_domain', 'owned')
        OR (NOT %s AND s.visibility = 'shown')
      )"""


def _read_safe_mode_on(cur) -> bool:
    """Read app_settings['safe_mode'] fresh on the given cursor -- never
    cache across calls, matching source_resolver.is_source_servable()'s own
    discipline (a global kill switch must always reflect the current value)."""
    cur.execute("SELECT value = 'on' FROM app_settings WHERE key = 'safe_mode'")
    row = cur.fetchone()
    return bool(row and row[0])


def gather_evidence(
    params: dict,
    source_id: str,
    topic: str,
    eligible_ids,
    floor: float = SIMILARITY_FLOOR,
    max_evidence: int = MAX_EVIDENCE,
) -> List[Dict]:
    """Embedding-similarity search over `propositions` ONLY (never `chunks`),
    restricted to this teacher's own documents, to sources currently
    servable under the license/visibility gate (LICENSE_GATE_SQL), and to the
    pass-both eligible set. `eligible_ids` may be a precomputed set OR an
    EligibilityChecker (see _is_eligible). Returns up to max_evidence
    {"id","content","similarity"} dicts, highest similarity first, all >=
    floor. The cheap similarity floor is applied BEFORE the (possibly
    expensive) eligibility check. Read-only; opens and closes its own
    connection."""
    import psycopg2

    embedding = embed_text(topic)
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        safe_mode_on = _read_safe_mode_on(cur)
        cur.execute(
            f"""
            SELECT p.id::text, p.content, d.id::text,
                   1 - (p.embedding <=> %s::vector) AS similarity
            FROM propositions p
            JOIN documents d ON d.id = p.document_id
            JOIN sources s ON s.id = d.source_id
            WHERE d.source_id = %s
              AND {LICENSE_GATE_SQL}
            ORDER BY p.embedding <=> %s::vector
            LIMIT 500
            """,
            (embedding, source_id, safe_mode_on, embedding),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    out = []
    for pid, content, doc_id, similarity in rows:
        if similarity < floor:
            continue
        if not _is_eligible(eligible_ids, pid, content, doc_id):
            continue
        out.append({"id": pid, "content": content, "similarity": float(similarity)})
        if len(out) >= max_evidence:
            break
    return out


def gather_evidence_corpus(
    params: dict,
    topic: str,
    eligible_ids,
    floor: float = SIMILARITY_FLOOR,
    max_evidence: int = MAX_EVIDENCE,
) -> List[Dict]:
    """Corpus-wide sibling of gather_evidence(): the SAME embedding-similarity
    search over `propositions` ONLY (never `chunks`), but across ALL teachers
    currently servable under the license/visibility gate (LICENSE_GATE_SQL),
    not restricted to one source. Returns up to max_evidence
    {"id","content","source_id","teacher","similarity"} dicts, highest
    similarity first, all >= floor and all in `eligible_ids` (the pass-both
    set). The "teacher" attached is a plain public source name -- used for
    scope determination, contributor counting, and per-statement labeling in
    CORPUS_PROMPT; it is NEVER a channel for source/chunk text (Invariant 12).
    Read-only; opens and closes its own connection. LIMIT 1000 (vs 500 for the
    single-teacher gather) because the eligible top-N is drawn from the whole
    corpus here, not one teacher's slice."""
    import psycopg2

    embedding = embed_text(topic)
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        safe_mode_on = _read_safe_mode_on(cur)
        cur.execute(
            f"""
            SELECT p.id::text, p.content, d.id::text, d.source_id::text, s.name,
                   1 - (p.embedding <=> %s::vector) AS similarity
            FROM propositions p
            JOIN documents d ON d.id = p.document_id
            JOIN sources s ON s.id = d.source_id
            WHERE {LICENSE_GATE_SQL}
            ORDER BY p.embedding <=> %s::vector
            LIMIT 1000
            """,
            (embedding, safe_mode_on, embedding),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    out = []
    for pid, content, doc_id, source_id, teacher, similarity in rows:
        if similarity < floor:
            continue
        if not _is_eligible(eligible_ids, pid, content, doc_id):
            continue
        out.append({
            "id": pid,
            "content": content,
            "source_id": source_id,
            "teacher": teacher,
            "similarity": float(similarity),
        })
        if len(out) >= max_evidence:
            break
    return out


def contributor_breakdown(evidence: List[Dict]) -> List[Dict]:
    """Per-teacher contribution counts derived from an in-memory evidence list
    (each item carrying 'source_id' and 'teacher'), sorted by count desc then
    name. Pure. This describes evidence in hand before a write; the
    authoritative breakdown for a STORED position is
    contributor_breakdown_from_db(), derived from that version's immutable
    position_evidence rows."""
    from collections import Counter

    counts = Counter((e["source_id"], e["teacher"]) for e in evidence)
    out = [
        {"source_id": sid, "name": name, "count": n}
        for (sid, name), n in counts.items()
    ]
    out.sort(key=lambda c: (-c["count"], c["name"]))
    return out


def contributor_breakdown_from_db(params: dict, position_id: str) -> List[Dict]:
    """Authoritative per-teacher contribution counts for a STORED position,
    derived from its immutable position_evidence rows joined out to sources --
    NOT a stored count. This is migration 073/077's explicit philosophy: never
    trust a count that could drift; derive it from the evidence rows
    themselves (a position version's evidence rows never change -- a rebuild
    writes a NEW version with its own rows). Read-only."""
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.source_id::text, s.name, count(*) AS c
            FROM position_evidence pe
            JOIN propositions p ON p.id = pe.proposition_id
            JOIN documents d ON d.id = p.document_id
            JOIN sources s ON s.id = d.source_id
            WHERE pe.position_id = %s
            GROUP BY d.source_id, s.name
            ORDER BY c DESC, s.name
            """,
            (position_id,),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    return [{"source_id": r[0], "name": r[1], "count": int(r[2])} for r in rows]


class PositionGenerationFailed(Exception):
    pass


def generate_position_text(teacher_name: str, topic: str, evidence: List[Dict]) -> str:
    """Calls the LLM to synthesize a position from `evidence` ONLY.

    `evidence` items need only a "content" key -- "id", if present, is
    never included in the prompt. This function opens no database
    connection and imports nothing capable of reading `chunks` or
    `documents`; there is no parameter through which source/chunk text
    could reach it. Raises PositionGenerationFailed on any call error, so a
    failed call is never indistinguishable from a legitimate result.

    Which instruction template is sent (POSITION_PROMPT vs.
    TENSION_MODE_PROMPT) is decided ONLY by _prompt_and_version_for_topic(
    topic) -- the same selector write_position() uses to decide what gets
    stamped, so generation and provenance can never disagree (see module
    docstring)."""
    system_prompt, _ = _prompt_and_version_for_topic(topic)
    evidence_block = "\n".join(f"- {e['content']}" for e in evidence)
    user_message = f"Teacher: {teacher_name}\n\nTopic: {topic}\n\nTeaching statements:\n{evidence_block}"
    try:
        client = get_anthropic_client()
        response = client.messages.create(
            model=get_generation_model(),
            max_tokens=500,
            thinking={"type": "disabled"},
            system=[
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": get_guardrails_text(), "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        raise PositionGenerationFailed(str(exc)) from exc


def generate_corpus_position_text(topic: str, attributed_evidence: List[Dict]) -> str:
    """Corpus sibling of generate_position_text(): synthesizes a corpus
    position from `attributed_evidence` ONLY. Each item needs a "content" key
    and a "teacher" key (a plain public source-name string). Like
    generate_position_text(), this opens no database connection and imports
    nothing capable of reading `chunks`/`documents`; there is no parameter
    through which source/chunk text could reach it -- the "teacher" label is a
    name, not source text. CLAUDE.md Invariant 12's source-blindness now
    covers BOTH generators, by signature, not by prompt instruction. Raises
    PositionGenerationFailed on any call error.

    The prompt/version is chosen by _prompt_and_version(topic, "corpus") -- the
    SAME selector write_corpus_position() stamps provenance from, so generation
    and provenance can never disagree (Invariant 10)."""
    system_prompt, _ = _prompt_and_version(topic, "corpus")
    evidence_block = "\n".join(
        f"- [{e['teacher']}] {e['content']}" for e in attributed_evidence
    )
    user_message = (
        f"Topic: {topic}\n\n"
        f"Teaching statements (each labeled with its teacher):\n{evidence_block}"
    )
    try:
        client = get_anthropic_client()
        response = client.messages.create(
            model=get_generation_model(),
            max_tokens=600,
            thinking={"type": "disabled"},
            system=[
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": get_guardrails_text(), "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        raise PositionGenerationFailed(str(exc)) from exc


def generate_position_text_stream(teacher_name: str, topic: str, evidence: List[Dict]):
    """Streaming sibling of generate_position_text() -- identical source-blind
    signature, prompt selection, and cache_control shape, but yields text
    deltas as they arrive instead of blocking for the full ~500-token
    response. Exists for the live cold-generate path (PLAN.md #48 step 4): a
    waiting user sees tokens as they're written rather than after the whole
    call completes. The blocking generate_position_text() is unchanged and
    stays the one used by the offline/batch path
    (generate_teacher_positions.py, prove_serving_path.py) -- this is
    additive, never a replacement.

    Yields str chunks (never SSE-framed -- this module has no HTTP/transport
    dependency; a caller like a future backend/app/services/position_layer.py
    is responsible for any SSE framing, same separation position_papers.py's
    own streaming function keeps from chat.py). Raises
    PositionGenerationFailed on any call error, exactly like the blocking
    sibling -- a failed call is never indistinguishable from a legitimate
    result."""
    system_prompt, _ = _prompt_and_version_for_topic(topic)
    evidence_block = "\n".join(f"- {e['content']}" for e in evidence)
    user_message = f"Teacher: {teacher_name}\n\nTopic: {topic}\n\nTeaching statements:\n{evidence_block}"
    try:
        client = get_anthropic_client()
        stream = client.messages.create(
            model=get_generation_model(),
            max_tokens=500,
            thinking={"type": "disabled"},
            system=[
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": get_guardrails_text(), "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": user_message}],
            stream=True,
        )
        for event in stream:
            if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                text = event.delta.text
                if text:
                    yield text
    except Exception as exc:
        raise PositionGenerationFailed(str(exc)) from exc


def generate_corpus_position_text_stream(topic: str, attributed_evidence: List[Dict]):
    """Streaming sibling of generate_corpus_position_text() -- see
    generate_position_text_stream()'s docstring; same relationship to its
    blocking counterpart (additive, source-blind, cache_control preserved,
    plain str chunks, no SSE framing here)."""
    system_prompt, _ = _prompt_and_version(topic, "corpus")
    evidence_block = "\n".join(
        f"- [{e['teacher']}] {e['content']}" for e in attributed_evidence
    )
    user_message = (
        f"Topic: {topic}\n\n"
        f"Teaching statements (each labeled with its teacher):\n{evidence_block}"
    )
    try:
        client = get_anthropic_client()
        stream = client.messages.create(
            model=get_generation_model(),
            max_tokens=600,
            thinking={"type": "disabled"},
            system=[
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": get_guardrails_text(), "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": user_message}],
            stream=True,
        )
        for event in stream:
            if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                text = event.delta.text
                if text:
                    yield text
    except Exception as exc:
        raise PositionGenerationFailed(str(exc)) from exc


# --------------------------------------------------------------------------
# Application-level scope lock (pairs with migration 076's DB CHECK)
# --------------------------------------------------------------------------
_PERMITTED_SCOPES = ("teacher", "corpus")

# Sentinel distinguishing "caller did not pass requested_teacher_id" (default
# it to source_id -- a teacher-EXPLICIT question) from an explicit None (a
# teacher position reached via a TOPIC question, whose lineage lookup key must
# stay NULL so it can later widen to corpus).
_UNSET = object()


def _assert_permitted_scope(kind: str) -> None:
    """Application-level half of the two-scope lock; the DB's
    CHECK (kind IN ('teacher','corpus')) constraint (migration 076) is the
    other half. Corpus-wide was unbanned on Alex's explicit 2026-08-01
    decision (PLAN.md #48). Widening to a THIRD scope requires deliberately
    changing BOTH this and the DB CHECK, never a runtime flag."""
    if kind not in _PERMITTED_SCOPES:
        raise ValueError(
            f"kind={kind!r} is not a permitted position scope -- must be one "
            f"of {_PERMITTED_SCOPES}. This application check pairs with the "
            "DB's CHECK (kind IN ('teacher','corpus')) constraint (migration "
            "076); widening to a third scope requires changing BOTH."
        )


def _insert_position_version(
    params: dict,
    *,
    kind: str,
    source_id: Optional[str],
    requested_teacher_id: Optional[str],
    topic: str,
    content: str,
    evidence: List[Dict],
    prompt_version: str,
    prompt_fingerprint: str,
    model: str,
    supersedes: Optional[Dict] = None,
) -> Dict:
    """Writes ONE position version + its position_evidence rows in a single
    transaction. Handles both a fresh lineage (supersedes=None -> version 1,
    lineage_id = the new row's own id, is_current=true) and a rebuild
    (supersedes={"id","lineage_id","version"} -> the prior version's
    is_current is flipped false and version = prior+1 is inserted with
    is_current=true, supersedes_id = prior id, same lineage_id). The prior
    version is NEVER overwritten in place -- an answer a user already saw stays
    exactly as it was, just is_current=false (PLAN.md track PL versioning
    rule). Because kind can differ between a lineage's versions, a rebuild can
    widen scope teacher->corpus without a from-scratch rewrite.

    The prior-version flip and the new insert run in the SAME transaction, so
    the partial unique index (one current version per (topic_key,
    requested_teacher)) always sees exactly one current version at commit --
    there is never a two-current window. topic_key is computed here, the one
    place, via normalize_topic_key(), so it always matches the lookup key."""
    import psycopg2
    import uuid

    topic_key = normalize_topic_key(topic)
    new_id = str(uuid.uuid4())
    if supersedes is None:
        lineage_id = new_id
        version = 1
        supersedes_id = None
    else:
        lineage_id = supersedes["lineage_id"]
        version = supersedes["version"] + 1
        supersedes_id = supersedes["id"]

    conn = psycopg2.connect(**params)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        if supersedes is not None:
            cur.execute(
                "UPDATE positions SET is_current = false, updated_at = now() "
                "WHERE id = %s AND is_current = true",
                (supersedes["id"],),
            )
        cur.execute(
            """
            INSERT INTO positions
              (id, kind, source_id, requested_teacher_id, topic, topic_key,
               content, status, prompt_version, prompt_fingerprint, model,
               lineage_id, version, is_current, supersedes_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s, true, %s)
            RETURNING id::text, created_at, version
            """,
            (new_id, kind, source_id, requested_teacher_id, topic, topic_key,
             content, prompt_version, prompt_fingerprint, model,
             lineage_id, version, supersedes_id),
        )
        position_id, created_at, written_version = cur.fetchone()
        for e in evidence:
            cur.execute(
                "INSERT INTO position_evidence (position_id, proposition_id) VALUES (%s, %s)",
                (position_id, e["id"]),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return {
        "position_id": position_id,
        "lineage_id": lineage_id,
        "version": written_version,
        "supersedes_id": supersedes_id,
        "topic_key": topic_key,
        "created_at": created_at.isoformat(),
    }


def write_position(
    params: dict,
    source_id: str,
    topic: str,
    evidence: List[Dict],
    kind: str = "teacher",
    min_evidence_count: int = MIN_EVIDENCE_COUNT,
    teacher_name: Optional[str] = None,
    requested_teacher_id=_UNSET,
    supersedes: Optional[Dict] = None,
) -> Dict:
    """Teacher-scoped writer. Enforces both structural guarantees before ever
    generating text: kind must be 'teacher' (corpus positions go through
    write_corpus_position(); the scope SET is also enforced by the DB CHECK,
    migration 076), and len(evidence) must meet min_evidence_count (the
    honest-empty floor -- no LLM call is made on a refusal). Refusal returns a
    result dict rather than raising -- refusing is the expected, correct
    outcome for thin evidence, not an error.

    requested_teacher_id: the teacher a question EXPLICITLY named. Defaults
    (via the _UNSET sentinel) to source_id -- a teacher-explicit question,
    where the requested teacher IS the attributed teacher. Pass None
    explicitly for a teacher position reached via a TOPIC question that a
    single teacher dominates: its lineage lookup key stays NULL so it can
    later widen to corpus.

    supersedes: pass a prior version dict {"id","lineage_id","version"} to
    version a rebuild -- the prior row is kept, is_current flipped false, and a
    new version inserted. None (default) starts a fresh v1 lineage. Nothing is
    ever overwritten in place.

    On success, generates the text and writes the position + its
    position_evidence rows in ONE transaction (via _insert_position_version)."""
    _assert_permitted_scope(kind)
    if kind != "teacher":
        raise ValueError(
            "write_position() handles kind='teacher' only; corpus positions "
            "use write_corpus_position(). (got kind=%r)" % (kind,)
        )

    if len(evidence) < min_evidence_count:
        return {
            "status": "refused_floor",
            "kind": "teacher",
            "topic": topic,
            "source_id": source_id,
            "evidence_count": len(evidence),
            "min_evidence_count": min_evidence_count,
        }

    if requested_teacher_id is _UNSET:
        requested_teacher_id = source_id

    if teacher_name is None:
        import psycopg2

        conn = psycopg2.connect(**params)
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sources WHERE id = %s", (source_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            raise ValueError(f"write_position: no sources row for source_id={source_id!r}")
        teacher_name = row[0]

    try:
        content = generate_position_text(teacher_name, topic, evidence)
    except PositionGenerationFailed as exc:
        return {
            "status": "errored",
            "kind": "teacher",
            "topic": topic,
            "source_id": source_id,
            "evidence_count": len(evidence),
            "error": str(exc),
        }

    # Stamp provenance from the SAME selector generate_position_text() used to
    # decide which prompt was actually sent -- never a hard-coded pair, which
    # would mislabel a tension-mode row (CLAUDE.md Invariant 10).
    prompt_text, stamped_prompt_version = _prompt_and_version(topic, "teacher")
    stamped_fingerprint = _fingerprint(prompt_text)

    ins = _insert_position_version(
        params,
        kind="teacher",
        source_id=source_id,
        requested_teacher_id=requested_teacher_id,
        topic=topic,
        content=content,
        evidence=evidence,
        prompt_version=stamped_prompt_version,
        prompt_fingerprint=stamped_fingerprint,
        model=get_generation_model(),
        supersedes=supersedes,
    )

    return {
        "status": "written",
        "kind": "teacher",
        "position_id": ins["position_id"],
        "lineage_id": ins["lineage_id"],
        "version": ins["version"],
        "supersedes_id": ins["supersedes_id"],
        "topic": topic,
        "source_id": source_id,
        "requested_teacher_id": requested_teacher_id,
        "teacher_name": teacher_name,
        "evidence_count": len(evidence),
        "evidence_ids": [e["id"] for e in evidence],
        "content": content,
        "created_at": ins["created_at"],
    }


def write_corpus_position(
    params: dict,
    topic: str,
    evidence: List[Dict],
    min_evidence_count: int = MIN_EVIDENCE_COUNT,
    requested_teacher_id: Optional[str] = None,
    supersedes: Optional[Dict] = None,
) -> Dict:
    """Corpus-scoped writer. `evidence` items must each carry "id", "content",
    "source_id", and "teacher" (i.e. gather_evidence_corpus() output). The
    stored row's source_id is NULL -- a corpus position names no single source
    (migration 076's coupling CHECK); its contributing teachers are DERIVED
    from the evidence, never stored as a single-source pointer or a taxonomy.

    Same honest-empty floor as write_position() (no LLM call on refusal) and
    the same versioning/supersede machinery. Generation is source-blind via
    generate_corpus_position_text() -- the per-statement teacher labels are
    plain names, not source text (Invariant 12).

    requested_teacher_id is normally None (a corpus position answers a topic
    question), but is accepted so a topic lineage widening teacher->corpus
    keeps the SAME lookup key it had as a teacher version (which was NULL)."""
    _assert_permitted_scope("corpus")

    if len(evidence) < min_evidence_count:
        return {
            "status": "refused_floor",
            "kind": "corpus",
            "topic": topic,
            "source_id": None,
            "evidence_count": len(evidence),
            "min_evidence_count": min_evidence_count,
        }

    attributed = [{"content": e["content"], "teacher": e["teacher"]} for e in evidence]
    try:
        content = generate_corpus_position_text(topic, attributed)
    except PositionGenerationFailed as exc:
        return {
            "status": "errored",
            "kind": "corpus",
            "topic": topic,
            "source_id": None,
            "evidence_count": len(evidence),
            "error": str(exc),
        }

    prompt_text, stamped_prompt_version = _prompt_and_version(topic, "corpus")
    stamped_fingerprint = _fingerprint(prompt_text)

    ins = _insert_position_version(
        params,
        kind="corpus",
        source_id=None,
        requested_teacher_id=requested_teacher_id,
        topic=topic,
        content=content,
        evidence=evidence,
        prompt_version=stamped_prompt_version,
        prompt_fingerprint=stamped_fingerprint,
        model=get_generation_model(),
        supersedes=supersedes,
    )

    return {
        "status": "written",
        "kind": "corpus",
        "position_id": ins["position_id"],
        "lineage_id": ins["lineage_id"],
        "version": ins["version"],
        "supersedes_id": ins["supersedes_id"],
        "topic": topic,
        "source_id": None,
        "requested_teacher_id": requested_teacher_id,
        "contributors": contributor_breakdown(evidence),
        "evidence_count": len(evidence),
        "evidence_ids": [e["id"] for e in evidence],
        "content": content,
        "created_at": ins["created_at"],
    }
