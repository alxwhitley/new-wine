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

SIMILARITY_FLOOR = 0.4 for evidence retrieval is a SEPARATE, secondary
parameter -- not the honest-empty floor itself, just the relevance cutoff
used to gather candidates before the count floor is checked. Reused as a
starting point from TEACHER_POSITION_SIMILARITY_FLOOR (study.py, = 0.3) is
deliberately NOT done here -- PLAN.md #48 already states that floor "was
tuned for the current retrieval path and does not transfer." 0.4 was chosen
fresh, empirically, for THIS retrieval shape (propositions, not chunks) --
see the report for the floor-sweep data that grounded it. Still provisional,
same caveat as MIN_EVIDENCE_COUNT above.

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
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.embeddings import embed_text  # noqa: E402
from app.services.llm_client import get_anthropic_client, get_guardrails_text  # noqa: E402

PROMPT_VERSION = "position_v1"
MODEL = "claude-sonnet-4-5"

SIMILARITY_FLOOR = 0.4
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
POSITION_PROMPT = """\
You are writing a stored position: a summary of what a named teacher teaches on one topic, for a Bible-study research tool used by curious lay believers in the Spirit-filled tradition.

You will be given the teacher's name, a topic, and a set of already-paraphrased teaching statements extracted from that teacher's own material. These statements are your ONLY source of information about this teacher's teaching on this topic. You have no other knowledge of what this teacher has said, and you must not add anything beyond what the statements say.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is stated in the teaching statements you are given. Do not add scripture references, examples, or claims that are not in them. Do not draw on general theological knowledge to fill a gap. If the statements do not cover some angle of the topic, leave it out rather than infer it.

Write ONE position: a single coherent passage, roughly 100-200 words, stating what this teacher teaches about the given topic. Synthesize the distinct points across the statements into one connected picture — do not just concatenate them one after another, and do not just restate a single statement. Name the teacher at least once, naturally. Where the statements show a specific, memorable framing or a real qualification the teacher attaches, keep it — do not flatten a distinctive position into generic Christian consensus.

Paraphrase. Do not quote the statements verbatim at length — restate them in connected prose, the same way the statements themselves already paraphrase their own source. A short (under roughly five word) precise phrase is fine only where it is genuinely how the teacher put a point in the evidence given to you.

This position represents the one named teacher only. Do not hedge as though other viewpoints exist unless the statements themselves show this teacher addressing a counter-view.

Output ONLY the position text — no preamble, no headers, no meta-commentary about the statements or the task."""


def prompt_fingerprint() -> str:
    return hashlib.sha256(POSITION_PROMPT.encode("utf-8")).hexdigest()


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
    failed call is never indistinguishable from a legitimate result."""
    evidence_block = "\n".join(f"- {e['content']}" for e in evidence)
    user_message = f"Teacher: {teacher_name}\n\nTopic: {topic}\n\nTeaching statements:\n{evidence_block}"
    try:
        client = get_anthropic_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=[
                {"type": "text", "text": POSITION_PROMPT},
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
            (kind, source_id, topic, content, PROMPT_VERSION, prompt_fingerprint(), MODEL),
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
