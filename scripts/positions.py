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
Corpus-wide positions: refused twice, not once
--------------------------------------------------------------------------
Alex's standing ruling (2026-07-28): corpus-wide positions are banned until
the propositions backfill (#49) completes -- a corpus-wide position authored
today would name whichever teachers happen to already have statements as
"the corpus" and invert the day Derek Prince's ~429 documents land. This is
enforced twice: write_position() raises ValueError before ever opening a
transaction if kind != "teacher" (this module's own gate), AND the
`positions` table's CHECK (kind = 'teacher') constraint (migration 073)
would reject the INSERT even if this module's own gate were bypassed or
forked. Widening either requires a deliberate code change / migration, not
a runtime flag.

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
defined once and referenced by both templates via f-string substitution at
module load time (never hand-duplicated separately in each), inserted as
its own paragraph between the FOUR CORNERS paragraph and the "Write ONE
position..." paragraph in both. It tells the model to name a gap plainly,
woven into the substantive teaching rather than as a meta-preamble, when
the gathered evidence complicates or contradicts an assumption built into
the question as asked -- keyed explicitly on what the gathered statements
show, never on "if the premise is false" in the abstract, to avoid making
this a leakage vector for the model's own outside knowledge (Open Decision
#20). The version bump reflects that the wording materially changed; three
pre-existing "position_v1" rows from the 2026-07-28 opening proof remain in
the table untouched -- nothing rewrites old rows -- so v2 also keeps new
rows' provenance from being conflated with those three.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.embeddings import embed_text  # noqa: E402
from app.services.llm_client import get_anthropic_client, get_guardrails_text  # noqa: E402

PROMPT_VERSION = "position_v2"
TENSION_MODE_PROMPT_VERSION = "position_tension_v2"
MODEL = "claude-sonnet-4-5"

SIMILARITY_FLOOR = 0.45
MAX_EVIDENCE = 15
MIN_EVIDENCE_COUNT = 5

# Static instruction template -- fingerprinted BEFORE any per-call
# substitution, same convention as propositions.py's prompt_fingerprint()
# (fingerprints the raw template text, not the speaker/topic-substituted
# version), so the fingerprint identifies "which wording of the
# instructions produced this row," independent of which teacher/topic a
# given call used. Sent as a system block alongside get_guardrails_text() --
# the same shared theological-guardrails text every other LLM call that
# represents a source document's or teacher's views already uses
# (chat.py's answer stream, study.py's live teacher-card synthesis) --
# reused here, not forked, so a position is held to the same guardrail
# standard as any other product surface that speaks in a teacher's voice.

# --------------------------------------------------------------------------
# Premise-correction clause (PLAN.md #48 item 4, 2026-07-30)
# --------------------------------------------------------------------------
# Shared by BOTH POSITION_PROMPT and TENSION_MODE_PROMPT -- defined once,
# referenced twice via f-string substitution at module load time, never
# hand-duplicated as separate literal text in each template (a hand-
# duplicated copy could silently drift out of sync between the two the way
# the book-name map already has -- see CLAUDE.md Landmines). Keys
# explicitly on "the gathered statements" (the evidence actually handed to
# the model), never on "if the premise is false" in the abstract -- this is
# what stops it from becoming a leakage vector: the model correcting a
# premise from its own outside knowledge rather than from what the
# evidence in front of it actually shows (the concern already on record as
# Open Decision #20). The correction must be woven into the substantive
# teaching -- Draft 7's own shape: stating the teacher's actual view, which
# happens to correct the premise, as part of the teaching itself -- never a
# meta-preamble ("this question assumes X, but ..."), which would directly
# collide with both templates' existing "no preamble, no meta-commentary"
# closing line.
PREMISE_CORRECTION_CLAUSE = (
    "If the gathered statements complicate, correct, or contradict an "
    "assumption built into the question as asked, name that gap plainly "
    "before teaching from what the statements actually say — do not "
    "silently answer the assumption as if it were true, and do not "
    "silently ignore it either."
)


POSITION_PROMPT = f"""\
You are writing a stored position: a summary of what a named teacher teaches on one topic, for a Bible-study research tool used by curious lay believers in the Spirit-filled tradition.

You will be given the teacher's name, a topic, and a set of already-paraphrased teaching statements extracted from that teacher's own material. These statements are your ONLY source of information about this teacher's teaching on this topic. You have no other knowledge of what this teacher has said, and you must not add anything beyond what the statements say.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is stated in the teaching statements you are given. Do not add scripture references, examples, or claims that are not in them. Do not draw on general theological knowledge to fill a gap. If the statements do not cover some angle of the topic, leave it out rather than infer it.

{PREMISE_CORRECTION_CLAUSE}

Write ONE position: a single coherent passage, roughly 100-200 words, stating what this teacher teaches about the given topic. Synthesize the distinct points across the statements into one connected picture — do not just concatenate them one after another, and do not just restate a single statement. Name the teacher at least once, naturally. Where the statements show a specific, memorable framing or a real qualification the teacher attaches, keep it — do not flatten a distinctive position into generic Christian consensus.

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
# Tension-mode exception (PLAN.md #48 item 3, 2026-07-30)
# --------------------------------------------------------------------------
# POSITION_PROMPT's "Write ONE position... Synthesize the distinct points...
# into one connected picture" instruction pushes toward resolution -- fine
# for most topics, but for Calvinism/predestination-adjacent topics it was
# confirmed (Draft 15, "predestination and unconditional election in the
# Calvinist sense" against Derek Prince's real evidence) to manufacture a
# one-sided resolution the teacher's own statements do not actually assert:
# "Prince resolves the tension between predestination and free will by
# appealing to..." -- stitching real statements into an over-resolved
# conclusion. TENSION_MODE_PROMPT below is identical to POSITION_PROMPT
# except that one sentence is replaced with a standing rule to present
# real tension as tension, not resolve it, unless the teacher has
# genuinely, verbatim, taken an explicit position.
TENSION_MODE_PROMPT = f"""\
You are writing a stored position: a summary of what a named teacher teaches on one topic, for a Bible-study research tool used by curious lay believers in the Spirit-filled tradition.

You will be given the teacher's name, a topic, and a set of already-paraphrased teaching statements extracted from that teacher's own material. These statements are your ONLY source of information about this teacher's teaching on this topic. You have no other knowledge of what this teacher has said, and you must not add anything beyond what the statements say.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is stated in the teaching statements you are given. Do not add scripture references, examples, or claims that are not in them. Do not draw on general theological knowledge to fill a gap. If the statements do not cover some angle of the topic, leave it out rather than infer it.

{PREMISE_CORRECTION_CLAUSE}

Write ONE position: a single coherent passage, roughly 100-200 words, stating what this teacher teaches about the given topic. Present what the teacher actually said, including any real tension between sovereignty/foreknowledge and free will, without resolving it into a side the teacher didn't take — unless the teacher has verbatim stated an explicit position, in which case state that position. Do not just restate a single statement. Name the teacher at least once, naturally. Where the statements show a specific, memorable framing or a real qualification the teacher attaches, keep it — do not flatten a distinctive position into generic Christian consensus.

Paraphrase. Do not quote the statements verbatim at length — restate them in connected prose, the same way the statements themselves already paraphrase their own source. A short (under roughly five word) precise phrase is fine only where it is genuinely how the teacher put a point in the evidence given to you.

This position represents the one named teacher only. Do not hedge as though other viewpoints exist unless the statements themselves show this teacher addressing a counter-view.

Output ONLY the position text — no preamble, no headers, no meta-commentary about the statements or the task."""


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


def gather_evidence(
    params: dict,
    source_id: str,
    topic: str,
    eligible_ids,
    floor: float = SIMILARITY_FLOOR,
    max_evidence: int = MAX_EVIDENCE,
) -> List[Dict]:
    """Embedding-similarity search over `propositions` ONLY (never
    `chunks`), restricted to this teacher's own documents and to
    `eligible_ids` (the pass-both set -- see eligible_statements.py).
    Returns up to max_evidence {"id", "content", "similarity"} dicts,
    highest similarity first, all >= floor. Read-only; opens and closes its
    own connection."""
    import psycopg2

    embedding = embed_text(topic)
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.id::text, p.content, 1 - (p.embedding <=> %s::vector) AS similarity
            FROM propositions p
            JOIN documents d ON d.id = p.document_id
            WHERE d.source_id = %s
            ORDER BY p.embedding <=> %s::vector
            LIMIT 500
            """,
            (embedding, source_id, embedding),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    out = []
    for pid, content, similarity in rows:
        if pid not in eligible_ids:
            continue
        if similarity < floor:
            continue
        out.append({"id": pid, "content": content, "similarity": float(similarity)})
        if len(out) >= max_evidence:
            break
    return out


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
            model=MODEL,
            max_tokens=500,
            system=[
                {"type": "text", "text": system_prompt},
                {"type": "text", "text": get_guardrails_text()},
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        raise PositionGenerationFailed(str(exc)) from exc


def write_position(
    params: dict,
    source_id: str,
    topic: str,
    evidence: List[Dict],
    kind: str = "teacher",
    min_evidence_count: int = MIN_EVIDENCE_COUNT,
    teacher_name: Optional[str] = None,
) -> Dict:
    """Enforces both structural guarantees before ever generating text:
    kind must be 'teacher' (also enforced by the DB CHECK constraint,
    migration 073 -- this is belt-and-suspenders, not the only gate), and
    len(evidence) must meet min_evidence_count (the honest-empty floor).
    Refusal returns a result dict rather than raising -- refusing is the
    expected, correct outcome for thin evidence, not an error.

    On success, generates the position text, then writes `positions` and
    `position_evidence` in ONE transaction (evidence rows and the position
    row must never exist independently of each other) and returns the
    written row's id."""
    if kind != "teacher":
        raise ValueError(
            f"write_position: kind={kind!r} is not permitted -- corpus-wide "
            "positions are banned per Alex's 2026-07-28 ruling (PLAN.md "
            "#48) until the propositions backfill (#49) completes. This "
            "check exists in addition to the DB's own CHECK (kind = "
            "'teacher') constraint, not instead of it."
        )

    if len(evidence) < min_evidence_count:
        return {
            "status": "refused_floor",
            "topic": topic,
            "source_id": source_id,
            "evidence_count": len(evidence),
            "min_evidence_count": min_evidence_count,
        }

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
            "topic": topic,
            "source_id": source_id,
            "evidence_count": len(evidence),
            "error": str(exc),
        }

    # Stamp provenance from the SAME selector generate_position_text() used
    # to decide which prompt was actually sent -- never the hard-coded
    # PROMPT_VERSION/prompt_fingerprint() pair, which only ever describes
    # POSITION_PROMPT and would mislabel every tension-mode row (CLAUDE.md
    # Invariant 10).
    prompt_text, stamped_prompt_version = _prompt_and_version_for_topic(topic)
    stamped_fingerprint = _fingerprint(prompt_text)

    import psycopg2

    conn = psycopg2.connect(**params)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO positions
              (kind, source_id, topic, content, status, prompt_version, prompt_fingerprint, model)
            VALUES (%s, %s, %s, %s, 'draft', %s, %s, %s)
            RETURNING id::text, created_at
            """,
            (kind, source_id, topic, content, stamped_prompt_version, stamped_fingerprint, MODEL),
        )
        position_id, created_at = cur.fetchone()
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
        "status": "written",
        "position_id": position_id,
        "topic": topic,
        "source_id": source_id,
        "teacher_name": teacher_name,
        "evidence_count": len(evidence),
        "evidence_ids": [e["id"] for e in evidence],
        "content": content,
        "created_at": created_at.isoformat(),
    }
